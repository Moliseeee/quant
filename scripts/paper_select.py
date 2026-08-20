#!/usr/bin/env python
"""模拟盘周度选股输出（每周五收盘后运行）。

按 模拟盘双组合并行方案.md 的启动流程:
  1. 先跑 fetch_factor_data.py --end <今天> 增量更新截面
  2. 再跑本脚本: 输出主组合 + 影子组合的最新持仓、市场换手率、区制判断

用法:
    python scripts/paper_select.py [--date 20260820] [--top-n 8] [--max-per-industry 3]
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from quant.data import load_panels, load_universe  # noqa: E402
from quant.portfolio import build_weight_series  # noqa: E402

PANEL_DIR = Path(__file__).resolve().parents[1] / "data" / "cache" / "factor_panels"
STOCK_BASIC = Path(__file__).resolve().parents[1] / "data" / "cache" / "stock_basic.parquet"

WEIGHTS_FIVE = {"low_turnover": 0.40, "low_pb": 0.20, "high_dividend": 0.15, "ep": 0.10, "low_ps": 0.10}
# 高换手市: 去低换手（K3 D 方案，剩余因子归一化）
WEIGHTS_NO_TURNOVER = {
    "low_pb": 0.20 / 0.55, "high_dividend": 0.15 / 0.55,
    "ep": 0.10 / 0.55, "low_ps": 0.10 / 0.55,
}
THRESHOLD_WINDOW, THRESHOLD_QUANTILE, THRESHOLD_MIN = 52, 0.7, 26  # K3 锁定参数


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", type=str, default=None, help="YYYYMMDD，默认取面板最新截面")
    ap.add_argument("--top-n", type=int, default=8)
    ap.add_argument("--max-per-industry", type=int, default=3)
    args = ap.parse_args()

    panels = load_panels(PANEL_DIR)
    universe = load_universe(STOCK_BASIC)
    if args.date:
        date = args.date
    else:
        date = panels["close"].index[-1].strftime("%Y%m%d")
    print(f"=== 模拟盘周度选股（截面 {date}）===\n")

    # 市场换手率 + rolling 阈值（K3 锁定 52/0.7/26）
    mkt_turnover = panels["turnover_rate"].mean(axis=1)
    threshold = mkt_turnover.rolling(THRESHOLD_WINDOW, min_periods=THRESHOLD_MIN).quantile(THRESHOLD_QUANTILE)
    mt_now = float(mkt_turnover.loc[date])
    th_now = float(threshold.loc[date]) if not np.isnan(threshold.loc[date]) else np.nan
    regime = "高换手市" if (not np.isnan(th_now) and mt_now > th_now) else "低换手市"
    print(f"市场换手率: {mt_now:.3f} | rolling 阈值(52周0.7分位): {th_now if not np.isnan(th_now) else 'n/a'} | 区制: {regime}")
    print()

    def show(tag: str, weights: dict, extra: dict | None = None) -> None:
        w = build_weight_series(
            panels, universe, weights, args.top_n, args.max_per_industry,
            extra_factors=extra,
        )
        row = w.loc[date]
        picked = row[row > 0].index.tolist()
        print(f"--- {tag}（Top{args.top_n} 等权，行业≤{args.max_per_industry}）---")
        for i, code in enumerate(picked, 1):
            ind = universe.loc[code, "industry"] if code in universe.index else "?"
            name = universe.loc[code, "name"] if code in universe.index else code
            print(f"  {i}. {code} {name}（{ind}）")
        print()

    # 主组合: 五因子（无条件）
    show("主组合（五因子）", WEIGHTS_FIVE)

    # 影子组合: rolling 条件化（高换手市 → 去低换手）
    regime_weights = {True: WEIGHTS_NO_TURNOVER, False: WEIGHTS_FIVE}
    w_shadow = build_weight_series(
        panels, universe, WEIGHTS_FIVE, args.top_n, args.max_per_industry,
        market_turnover=mkt_turnover, turnover_threshold=threshold,
        regime_weights=regime_weights,
    )
    row = w_shadow.loc[date]
    picked = row[row > 0].index.tolist()
    print(f"--- 影子组合（rolling 条件化，区制={regime}）---")
    for i, code in enumerate(picked, 1):
        ind = universe.loc[code, "industry"] if code in universe.index else "?"
        name = universe.loc[code, "name"] if code in universe.index else code
        print(f"  {i}. {code} {name}（{ind}）")
    print()

    print("记录提示: 将上表填入 模拟盘双组合并行方案.md 第二节周度记录表（含净值/等权基准/操作/备注）")


if __name__ == "__main__":
    main()
