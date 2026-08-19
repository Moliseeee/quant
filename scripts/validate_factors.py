#!/usr/bin/env python
"""因子有效性独立验证（胜率验证核心）。

输入: data/cache/factor_panels/*.parquet（fetch_factor_data.py 产物）
验证: RankIC / ICIR / t值 / 正占比 / 分层检验，方向统一为"越大越好"

对照目标: Kimi 侧 4 因子模型（低换手/低PB/低PE/高股息，|ICIR| 0.36-0.44）
独立复现结论一致 → 因子可信；不一致 → 查数据口径差异。

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

PANEL_DIR = Path(__file__).resolve().parents[1] / "data" / "cache" / "factor_panels"

# 因子方向约定: value>0 表示"越大越好"，负号翻转方向
# 低换手 = -turnover_rate（换手率越低因子值越大）
# 低估值 = -pe / -pb / -ps（PE/PB/PS 越低因子值越大）
# 小市值 = -total_mv（市值越小因子值越大）
# 高股息 = +dv_ttm（股息率越高越好）
FACTOR_DIRECTIONS = {
    "low_turnover": ("turnover_rate", -1.0),
    "low_pe": ("pe", -1.0),
    "low_pb": ("pb", -1.0),
    "low_ps": ("ps", -1.0),
    "small_mv": ("total_mv", -1.0),
    "high_dividend": ("dv_ttm", 1.0),
}

MIN_STOCKS = 200  # 截面最少股票数，低于则跳过


def load_panels(panel_dir: Path) -> pd.DataFrame:
    """加载全部截面 parquet → (date × stock) 的逐因子面板 dict。"""
    files = sorted(panel_dir.glob("*.parquet"))
    if not files:
        raise SystemExit(f"未找到截面数据: {panel_dir}（先运行 fetch_factor_data.py）")
    print(f"加载 {len(files)} 个截面...")

    frames = {}
    for f in files:
        d = f.stem  # YYYYMMDD
        df = pd.read_parquet(f)
        df = df.set_index("ts_code")
        frames[d] = df

    # 按日期排序并统一 index
    dates = sorted(frames.keys())
    all_codes = sorted(set().union(*[set(frames[d].index) for d in dates]))

    panels: dict[str, pd.DataFrame] = {}
    for col in ["close", "pe", "pb", "ps", "total_mv", "turnover_rate", "dv_ttm"]:
        m = pd.DataFrame(index=pd.DatetimeIndex(pd.to_datetime(dates), name="date"),
                         columns=all_codes, dtype=float)
        for d in dates:
            s = frames[d].get(col)
            if s is not None:
                m.loc[pd.Timestamp(d), s.index] = s
        panels[col] = m
    return panels


def build_factor_and_fwd(panels: dict[str, pd.DataFrame]) -> tuple[dict, pd.DataFrame]:
    """构造方向标准化因子面板 + 未来 1 周收益面板。"""
    factors: dict[str, pd.DataFrame] = {}
    for name, (col, direction) in FACTOR_DIRECTIONS.items():
        f = panels[col].astype(float) * direction
        factors[name] = f

    # 未来 1 周收益 = 下一截面 close / 当前截面 close - 1
    close = panels["close"].astype(float)
    fwd = close.shift(-1) / close - 1
    return factors, fwd


def main() -> None:
    ap = argparse.ArgumentParser(description="因子有效性独立验证")
    ap.add_argument("--report", type=str, default=str(
        Path(__file__).resolve().parents[1] / "data" / "output" / "factor_report.md"))
    args = ap.parse_args()

    panels = load_panels(PANEL_DIR)
    factors, fwd = build_factor_and_fwd(panels)
    n_dates = len(fwd)

    rows = []
    lines = ["# 因子有效性验证报告（独立复现）", "",
             f"- 数据源: Tushare daily_basic，{n_dates} 个周频截面（{PANEL_DIR}）",
             f"- 验证方法: RankIC（逐截面 Spearman）→ ICIR/t值；未来 1 周收益",
             f"- 方向约定: 因子值越大越好（低换手/低估值/小市值/高股息均翻转）", "",
             "| 因子 | mean_IC | ICIR | t值 | 正占比 | 截面数 | 分层单调 | 多空收益 |", "|---|---|---|---|---|---|---|---|"]

    for name, f in factors.items():
        ic = rank_ic(f, fwd, min_obs=MIN_STOCKS)
        s = ic_summary(ic)
        q = quantile_analysis(f, fwd, n_quantiles=5)
        # 分层单调性：Q5 > Q1
        monotonic = ""
        ls_ret = float("nan")
        if not q.empty and 4 in q.index and 0 in q.index:
            monotonic = "✅" if q.loc[4, "mean_ret"] > q.loc[0, "mean_ret"] else "❌"
            ls_ret = q.loc["LS_long_short", "mean_ret"]

        verdict = "✅ 有效" if abs(s["mean_ic"]) >= 0.02 and s["icir"] >= 0.3 else "❌ 无效"
        rows.append((name, s, verdict, monotonic, ls_ret))
        print(f"{name:16s} IC={s['mean_ic']:+.4f}  ICIR={s['icir']:+.3f}  "
              f"t={s['t_stat']:+.2f}  正占比={s['positive_ratio']:.0%}  {verdict}")

        lines.append(
            f"| {name} | {s['mean_ic']:+.4f} | {s['icir']:+.3f} | {s['t_stat']:+.2f} "
            f"| {s['positive_ratio']:.0%} | {s['n_days']} | {monotonic} | {ls_ret:+.4f} |")

    # 汇总
    lines += ["", "## 判读标准",
              "- ICIR ≥ 0.3 且 |mean_IC| ≥ 0.02：因子有统计意义",
              "- 分层单调性 ✅：因子值越大未来收益越高（方向正确）",
              "- 多空收益 > 0：做多高因子组、做空低因子组能赚钱（学术口径）", ""]
    lines.append(f"*验证工具: quant/factors/ic.py ｜ {pd.Timestamp.now():%Y-%m-%d}*")

    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text("\n".join(lines), encoding="utf-8")
    print(f"\n报告已保存: {args.report}")

    # 对照 Kimi 结论
    print("\n===== 对照 Kimi 侧结论 =====")
    print("Kimi: 低换手0.35/低PB0.30/低PE0.20/高股息0.15，23期验证 |ICIR| 0.36-0.44")
    for name, s, verdict, *_ in rows:
        kimi_hit = name in ("low_turnover", "low_pb", "low_pe", "high_dividend") and s["icir"] >= 0.3
        print(f"  {name:16s} 我们ICIR={s['icir']:+.3f}  {'✅ 与Kimi一致' if kimi_hit else '⚠️ 与Kimi不一致或无效'}")


if __name__ == "__main__":
    main()
