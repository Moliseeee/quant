#!/usr/bin/env python
"""因子有效性独立验证 v2（胜率验证核心，含中性化与分年稳定性）。

输入:
    data/cache/factor_panels/*.parquet   （fetch_factor_data.py 产物，含 pe_ttm/ps_ttm）
    data/cache/stock_basic.parquet       （fetch_stock_basic.py 产物，行业映射）

验证: RankIC / ICIR / t值 / 正占比 / 分层检验 / 行业市值中性化 / 分年稳定性
方向统一为"越大越好"。对照 Kimi 4 因子模型（|ICIR| 0.36-0.44）。

用法:
    python scripts/validate_factors.py [--report data/output/factor_report.md]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from quant.factors.ic import ic_summary, quantile_analysis, rank_ic  # noqa: E402
from quant.factors.processing import neutralize  # noqa: E402

PANEL_DIR = Path(__file__).resolve().parents[1] / "data" / "cache" / "factor_panels"
STOCK_BASIC = Path(__file__).resolve().parents[1] / "data" / "cache" / "stock_basic.parquet"

# 因子方向: value>0 表示"越大越好"
FACTOR_DIRECTIONS = {
    "low_turnover": ("turnover_rate", -1.0),
    "low_pe_ttm": ("pe_ttm", -1.0),
    "low_pe": ("pe", -1.0),          # 动态 PE（对照口径）
    "low_pb": ("pb", -1.0),
    "low_ps_ttm": ("ps_ttm", -1.0),
    "high_dividend": ("dv_ttm", 1.0),
    "small_mv": ("total_mv", -1.0),
}

MIN_STOCKS = 200


def load_panels(panel_dir: Path) -> dict[str, pd.DataFrame]:
    files = sorted(panel_dir.glob("*.parquet"))
    if not files:
        raise SystemExit(f"未找到截面数据: {panel_dir}")
    print(f"加载 {len(files)} 个截面...")

    frames = {f.stem: pd.read_parquet(f).set_index("ts_code") for f in files}
    dates = sorted(frames.keys())
    all_codes = sorted(set().union(*[set(frames[d].index) for d in dates]))

    cols = ["close", "pe", "pe_ttm", "pb", "ps", "ps_ttm",
            "total_mv", "turnover_rate", "dv_ttm"]
    panels: dict[str, pd.DataFrame] = {}
    for col in cols:
        m = pd.DataFrame(index=pd.DatetimeIndex(pd.to_datetime(dates), name="date"),
                         columns=all_codes, dtype=float)
        for d in dates:
            s = frames[d].get(col)
            if s is not None:
                m.loc[pd.Timestamp(d), s.index] = s
        panels[col] = m
    return panels


def load_industry_map() -> pd.Series:
    if not STOCK_BASIC.exists():
        print("⚠️ 无行业映射（先跑 fetch_stock_basic.py），跳过中性化")
        return pd.Series(dtype=object)
    sb = pd.read_parquet(STOCK_BASIC)
    return sb.set_index("ts_code")["industry"]


def neutralize_panel(f: pd.DataFrame, mv: pd.DataFrame,
                     industry_map: pd.Series) -> pd.DataFrame:
    """逐截面做行业 + 市值中性化（回归残差）。"""
    out = pd.DataFrame(index=f.index, columns=f.columns, dtype=float)
    for date in f.index:
        cross = pd.DataFrame({"factor": f.loc[date], "total_mv": mv.loc[date]})
        cross["industry"] = cross.index.map(industry_map)
        cross = cross.dropna(subset=["factor"])
        if len(cross) < MIN_STOCKS:
            continue
        res = neutralize(cross, "factor")
        out.loc[date, res.index] = res
    return out


def yearly_ic_summary(ic: pd.Series) -> str:
    """分年 IC 稳定性：每年 mean_IC / ICIR。"""
    if ic.empty:
        return "—"
    parts = []
    for year, sub in ic.groupby(ic.index.year):
        s = ic_summary(sub)
        parts.append(f"{year}: {s['mean_ic']:+.3f}/{s['icir']:+.2f}")
    return "  ".join(parts)


def main() -> None:
    ap = argparse.ArgumentParser(description="因子有效性独立验证 v2")
    ap.add_argument("--report", type=str, default=str(
        Path(__file__).resolve().parents[1] / "data" / "output" / "factor_report.md"))
    args = ap.parse_args()

    panels = load_panels(PANEL_DIR)
    industry_map = load_industry_map()
    fwd = panels["close"].astype(float).shift(-1) / panels["close"].astype(float) - 1

    lines = ["# 因子有效性验证报告 v2（独立复现 + 中性化 + 分年）", "",
             f"- 数据源: Tushare daily_basic（含 TTM 口径），{len(fwd)} 个周频截面",
             f"- 方法: RankIC → ICIR/t值；行业市值中性化；未来 1 周收益；方向越大越好", "",
             "| 因子 | mean_IC | ICIR | t值 | 正占比 | 中性化ICIR | 分年ICIR（年: IC/ICIR） | 判定 |",
             "|---|---|---|---|---|---|---|---|"]

    print(f"{'因子':<16} {'原始ICIR':>9} {'中性ICIR':>9}  判定")
    for name, (col, direction) in FACTOR_DIRECTIONS.items():
        f_raw = panels[col].astype(float) * direction
        ic = rank_ic(f_raw, fwd, min_obs=MIN_STOCKS)
        s = ic_summary(ic)

        # 中性化
        neutral_note = "—"
        if not industry_map.empty:
            f_neu = neutralize_panel(f_raw, panels["total_mv"], industry_map)
            ic_n = rank_ic(f_neu, fwd, min_obs=MIN_STOCKS)
            sn = ic_summary(ic_n)
            neutral_note = f"{sn['icir']:+.3f}"
            if sn["icir"] >= 0.3 and s["icir"] < 0.3:
                neutral_note += " ⬆翻案"
        else:
            sn = s

        verdict = "✅ 有效" if sn["icir"] >= 0.3 and abs(sn["mean_ic"]) >= 0.02 else "❌ 无效"
        years = yearly_ic_summary(ic)
        print(f"{name:16s} {s['icir']:+7.3f} {neutral_note:>9}  {verdict}")
        lines.append(
            f"| {name} | {s['mean_ic']:+.4f} | {s['icir']:+.3f} | {s['t_stat']:+.2f} "
            f"| {s['positive_ratio']:.0%} | {neutral_note} | {years} | {verdict} |")

    lines += ["", "## 判读标准",
              "- ICIR ≥ 0.3 且 |mean_IC| ≥ 0.02：统计意义达标",
              "- 中性化 ICIR 显著提升 = 因子暴露中行业/市值成分占比高（翻案场景）",
              "- 分年 ICIR 正负交替 = 因子不稳定，谨慎", "",
              "## 对照 Kimi 结论",
              "Kimi: 低换手0.35/低PB0.30/低PE0.20/高股息0.15，23期验证 |ICIR| 0.36-0.44",
              "*验证工具: quant/factors/ic.py + processing.py ｜ 独立复现*"]
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text("\n".join(lines), encoding="utf-8")
    print(f"\n报告已保存: {args.report}")


if __name__ == "__main__":
    main()
