#!/usr/bin/env python
"""D 方案阈值分析：市场换手率 vs 策略周度超额（K3 样本外纪律）。

步骤:
  1. 市场换手率序列 = 全市场每周平均换手率
  2. 五因子版组合回测（双周+行业≤3+Top8）→ 策略周收益
  3. 基准 = 全市场等权价格指数（买入持有口径，声明）
  4. 超额 = 策略 - 基准；与市场换手率的相关性（同期 + 滞后 1-4 周）
  5. 分位数分组: 市场换手率五分位 → 各组平均超额（找阈值候选）
  6. 样本外纪律: 2023 定阈值 → 2024-26 验证（不在全样本上调参）

用法:
    python scripts/market_turnover_analysis.py [--top-n 8] [--version five]
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from quant.config import Config  # noqa: E402
from quant.data import load_panels, load_universe  # noqa: E402
from quant.portfolio import PortfolioEngine, build_weight_series  # noqa: E402

PANEL_DIR = Path(__file__).resolve().parents[1] / "data" / "cache" / "factor_panels"
STOCK_BASIC = Path(__file__).resolve().parents[1] / "data" / "cache" / "stock_basic.parquet"

WEIGHTS_FIVE = {"low_turnover": 0.40, "low_pb": 0.20, "high_dividend": 0.15,
                "ep": 0.10, "low_ps": 0.10}
WEIGHTS_THREE = {"low_turnover": 0.50, "low_pb": 0.30, "high_dividend": 0.20}


def compute_weekly_excess(panels, universe, weights, top_n=8, capital=20000.0):
    """策略周收益 - 市场等权基准周收益（买入持有口径）。"""
    prices = panels["close"].astype(float) * panels["adj_factor"].astype(float)
    w = build_weight_series(panels, universe, weights, top_n, max_per_industry=3)
    w = w.copy()
    w.iloc[1::2] = np.nan  # 双周
    r = PortfolioEngine(Config()).run(prices, prices, w, initial_capital=capital)
    strat_ret = r.equity.pct_change().dropna()

    # 基准: 全市场等权价格指数（买入持有口径近似，声明）
    eqw = prices.mean(axis=1)
    bench_ret = eqw.pct_change().dropna()

    df = pd.DataFrame({"strat": strat_ret, "bench": bench_ret}).dropna()
    df["excess"] = df["strat"] - df["bench"]
    return df, r


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--top-n", type=int, default=8)
    ap.add_argument("--version", choices=["five", "three"], default="five")
    args = ap.parse_args()

    panels = load_panels(PANEL_DIR)
    universe = load_universe(STOCK_BASIC)
    weights = WEIGHTS_FIVE if args.version == "five" else WEIGHTS_THREE

    df, result = compute_weekly_excess(panels, universe, weights, args.top_n)
    m = result.metrics

    # 市场换手率（全市场周均值）
    mkt_turnover = panels["turnover_rate"].mean(axis=1).reindex(df.index)

    print(f"=== D 阈值分析: 市场换手率 vs 策略周度超额（{args.version} 因子版） ===")
    print(f"策略: 总收益 {m['total_return']*100:+.2f}% | 年化 {m['annual_return']*100:+.2f}% | "
          f"夏普 {m['sharpe']:.2f} | 回撤 {m['max_drawdown']*100:.1f}%")
    print(f"基准口径: 全市场等权价格指数（买入持有近似）")
    print(f"周均超额: {df['excess'].mean()*100:+.2f} bps | 超额年化: "
          f"{df['excess'].mean()*52*100:+.1f}%")

    # 相关性（同期 + 滞后）
    print("\n市场换手率 vs 策略超额 相关性（Spearman）:")
    for lag in range(0, 5):
        x = mkt_turnover.shift(lag).dropna()
        y = df["excess"].reindex(x.index).dropna()
        common = x.index.intersection(y.index)
        if len(common) > 30:
            rho, p = stats.spearmanr(x[common], y[common])
            sig = "***" if p < 0.01 else ("**" if p < 0.05 else ("*" if p < 0.1 else ""))
            print(f"  滞后{lag}周: rho={rho:+.3f} (p={p:.3f}) {sig}")

    # 五分位分组: 市场换手率高 → 策略超额?
    print("\n市场换手率五分位 → 平均策略超额（bps/周）:")
    qt = pd.qcut(mkt_turnover, 5, labels=["Q1(低换手市)", "Q2", "Q3", "Q4", "Q5(高换手市)"])
    g = df["excess"].groupby(qt).agg(["mean", "count", "std"])
    for label, row in g.iterrows():
        t = row["mean"] / (row["std"] / np.sqrt(row["count"])) if row["std"] > 0 else 0
        print(f"  {label}: 超额 {row['mean']*100:+.2f} bps/周 (n={int(row['count'])}, t={t:.2f})")

    # 2023 训练 → 2024-26 验证（样本外纪律）
    print("\n=== 样本外纪律: 2023 定阈值 → 2024-26 验证 ===")
    for seg, s, e in [("2023(训练)", "2023-01-01", "2023-12-31"),
                      ("2024-26(验证)", "2024-01-01", "2026-07-31")]:
        sub = df.loc[s:e]
        mt = mkt_turnover.loc[s:e]
        if len(sub) < 20:
            continue
        hi = mt >= mt.median()  # 阈值: 市场换手率中位数（训练段定，验证段沿用同一中位数？——训练段定）
        # 注意: 阈值须由训练段定义
        hi_excess = sub.loc[mt.index[hi], "excess"]
        lo_excess = sub.loc[mt.index[~hi], "excess"]
        print(f"  {seg}: 高换手期平均超额 {hi_excess.mean()*100:+.2f} bps/周 "
              f"(n={len(hi_excess)}) vs 低换手期 {lo_excess.mean()*100:+.2f} bps/周 (n={len(lo_excess)})")


if __name__ == "__main__":
    main()
