#!/usr/bin/env python
"""D 方案条件化实验：高换手市关闭低换手因子（K3 样本外纪律）。

阈值定义: 2023 训练段市场换手率中位数（不在全样本上调参）。
对照:
  A. 无条件五因子（参考配置）
  B. 条件化: 市场换手率 > 阈值 → 去低换手权重（剩余因子归一化）；否则五因子
输出: 全程 + walk-forward 分段（2023 训练/2024-26 验证）。

用法:
    python scripts/run_regime_portfolio.py [--top-n 8]
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from quant.config import Config  # noqa: E402
from quant.data import load_panels, load_universe  # noqa: E402
from quant.portfolio import PortfolioEngine, build_weight_series  # noqa: E402

PANEL_DIR = Path(__file__).resolve().parents[1] / "data" / "cache" / "factor_panels"
STOCK_BASIC = Path(__file__).resolve().parents[1] / "data" / "cache" / "stock_basic.parquet"

WEIGHTS_FIVE = {"low_turnover": 0.40, "low_pb": 0.20, "high_dividend": 0.15,
                "ep": 0.10, "low_ps": 0.10}
# 去低换手（归一化，和=1）
WEIGHTS_NO_TURNOVER = {"low_pb": 0.20 / 0.55, "high_dividend": 0.15 / 0.55,
                       "ep": 0.10 / 0.55, "low_ps": 0.10 / 0.55}


def run_version(panels, universe, prices, regime=None, threshold=None, top_n=8):
    """跑一个版本，返回 (equity, trades, metrics)。regime=(市场换手率序列, {True:高,False:低})"""
    if regime is None:
        w = build_weight_series(panels, universe, WEIGHTS_FIVE, top_n, 3)
    else:
        mkt_turnover, regime_weights = regime
        w = build_weight_series(panels, universe, WEIGHTS_FIVE, top_n, 3,
                                market_turnover=mkt_turnover,
                                turnover_threshold=threshold,
                                regime_weights=regime_weights)
    w = w.copy()
    w.iloc[1::2] = np.nan  # 双周
    r = PortfolioEngine(Config()).run(prices, prices, w, initial_capital=20000.0)
    return r


def report(label, r):
    m = r.metrics
    print(f"  {label:<28} 总收益 {m['total_return']*100:+7.2f}%  年化 {m['annual_return']*100:+6.2f}%  "
          f"夏普 {m['sharpe']:+.2f}  回撤 {m['max_drawdown']*100:5.1f}%  换手 {m['turnover']:5.1f}  "
          f"笔数 {m['trade_count']}")


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--top-n", type=int, default=8)
    args = ap.parse_args()

    panels = load_panels(PANEL_DIR)
    universe = load_universe(STOCK_BASIC)
    prices = panels["close"].astype(float) * panels["adj_factor"].astype(float)

    # 阈值 = 2023 训练段市场换手率中位数（样本外纪律：不在全样本调参）
    mkt_turnover = panels["turnover_rate"].mean(axis=1)
    train_mt = mkt_turnover.loc["2023-01-01":"2023-12-31"].dropna()
    threshold = float(train_mt.median())
    print(f"市场换手率阈值（2023 训练段中位数）: {threshold:.3f} | "
          f"全程中位数 {mkt_turnover.median():.3f}（样本外不动）")
    regime = (mkt_turnover, {True: WEIGHTS_NO_TURNOVER, False: WEIGHTS_FIVE})

    print(f"\n=== 全程（Top{args.top_n}, 双周+行业≤3） ===")
    r_a = run_version(panels, universe, prices, top_n=args.top_n)
    r_b = run_version(panels, universe, prices, regime=regime, threshold=threshold,
                      top_n=args.top_n)
    report("A. 无条件五因子", r_a)
    report("B. 条件化(高换手去低换手)", r_b)

    print(f"\n=== walk-forward 分段（阈值由训练段固定，验证段沿用） ===")
    for seg, s, e in [("2023(训练)", "2023-01-01", "2023-12-31"),
                      ("2024(验证)", "2024-01-01", "2024-12-31"),
                      ("2025-26H1(验证)", "2025-01-01", "2026-07-31")]:
        sub_panels = {col: df.loc[s:e] for col, df in panels.items()}
        sub_prices = prices.loc[s:e]
        sub_mt = mkt_turnover.loc[s:e]
        regime_sub = (sub_mt, {True: WEIGHTS_NO_TURNOVER, False: WEIGHTS_FIVE})
        print(f"\n  [{seg}]")
        report("  A. 无条件", run_version(sub_panels, universe, sub_prices, top_n=args.top_n))
        report("  B. 条件化", run_version(sub_panels, universe, sub_prices,
                                         regime=regime_sub, threshold=threshold,
                                         top_n=args.top_n))


if __name__ == "__main__":
    main()
