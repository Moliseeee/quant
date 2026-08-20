#!/usr/bin/env python
"""策略失效归因：分段因子 IC 对比（2023 vs 2024 vs 2025-2026）。

walk-forward 显示三因子策略 2025-2026 亏损 → 需要定位是哪个因子失效。
对比各因子在三个分段的 ICIR，找出衰减来源。

用法:
    python scripts/factor_attribution.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from quant.factors.ic import ic_summary, rank_ic  # noqa: E402
from quant.factors.processing import (  # noqa: E402
    adjusted_forward_return,
    ep_transform,
    neutralize,
)

PANEL_DIR = Path(__file__).resolve().parents[1] / "data" / "cache" / "factor_panels"
STOCK_BASIC = Path(__file__).resolve().parents[1] / "data" / "cache" / "stock_basic.parquet"

FACTOR_DIRECTIONS = {
    "low_turnover": ("turnover_rate", -1.0),
    "low_pb": ("pb", -1.0),
    "high_dividend": ("dv_ttm", 1.0),
    "ep": ("pe_ttm", "ep"),
    "small_mv": ("total_mv", -1.0),
}

SEGMENTS = [
    ("2023", "2023-01-01", "2023-12-31"),
    ("2024", "2024-01-01", "2024-12-31"),
    ("2025-2026H1", "2025-01-01", "2026-07-31"),
]


def load_panels(panel_dir: Path) -> dict[str, pd.DataFrame]:
    files = sorted(panel_dir.glob("*.parquet"))
    frames = {f.stem: pd.read_parquet(f).set_index("ts_code") for f in files}
    dates = sorted(frames.keys())
    all_codes = sorted(set().union(*[set(frames[d].index) for d in dates]))
    cols = ["close", "pe_ttm", "pb", "total_mv", "turnover_rate", "dv_ttm", "adj_factor"]
    panels = {}
    for col in cols:
        m = pd.DataFrame(index=pd.DatetimeIndex(pd.to_datetime(dates), name="date"),
                         columns=all_codes, dtype=float)
        for d in dates:
            s = frames[d].get(col)
            if s is not None:
                m.loc[pd.Timestamp(d), s.index] = s
        panels[col] = m
    return panels


def build_factors(panels: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    factors = {}
    for name, (col, direction) in FACTOR_DIRECTIONS.items():
        f = panels[col].astype(float)
        factors[name] = ep_transform(f) if direction == "ep" else f * direction
    return factors


def load_industry_map() -> pd.Series:
    sb = pd.read_parquet(STOCK_BASIC)
    return sb.set_index("ts_code")["industry"]


def neutralize_panel(f: pd.DataFrame, mv: pd.DataFrame,
                     industry_map: pd.Series) -> pd.DataFrame:
    out = pd.DataFrame(index=f.index, columns=f.columns, dtype=float)
    for date in f.index:
        cross = pd.DataFrame({"factor": f.loc[date], "total_mv": mv.loc[date]})
        cross["industry"] = cross.index.map(industry_map)
        cross = cross.dropna(subset=["factor"])
        if len(cross) < 200:
            continue
        res = neutralize(cross, "factor")
        out.loc[date, res.index] = res
    return out


def main() -> None:
    panels = load_panels(PANEL_DIR)
    factors = build_factors(panels)
    industry_map = load_industry_map()
    fwd_full = adjusted_forward_return(panels["close"], panels["adj_factor"])

    print(f"{'因子':<16} {'分段':<12} {'原始ICIR':>9} {'中性ICIR':>9}  {'趋势'}")
    print("-" * 62)
    trend_rows: dict[str, list] = {name: [] for name in factors}
    for seg_name, start, end in SEGMENTS:
        seg_fwd = fwd_full.loc[start:end]
        for name, f in factors.items():
            seg_f = f.loc[start:end]
            ic = rank_ic(seg_f, seg_fwd, min_obs=200)
            s = ic_summary(ic)
            neu = "—"
            if name != "small_mv":
                sn = ic_summary(rank_ic(
                    neutralize_panel(seg_f, panels["total_mv"].loc[start:end], industry_map),
                    seg_fwd, min_obs=200))
                neu = f"{sn['icir']:+.3f}"
            else:
                sn = s
            trend_rows[name].append(s["icir"])
            print(f"{name:<16} {seg_name:<12} {s['icir']:+8.3f} {neu:>9}")

    print("\nICIR 趋势（原始口径，>0 有效，衰减=策略失效来源）:")
    for name, vals in trend_rows.items():
        arrow = "→".join(f"{v:+.2f}" for v in vals)
        decay = vals[-1] < vals[0] and vals[-1] < 0.1
        flag = "⚠️ 衰减/失效" if decay else "✅ 稳定"
        print(f"  {name:<16} {arrow}  {flag}")


if __name__ == "__main__":
    main()
