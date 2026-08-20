#!/usr/bin/env python
"""因子选股组合回测：五因子版 vs 三因子版（Kimi 定稿裁决）。

流程（无前视）:
    每周截面 T 收盘:  因子打分（winsorize→中性化→zscore→加权合成）→ 选 Top N 等权
    T+1 截面:         用 T+1 复权价执行调仓（决策在 T 收盘，T+1 成交）
    中间周:           持仓不动

对比: ① 扣费后净收益/指标 ② Top-N 重合度
裁决规则（Kimi）: 简化版业绩在五因子版噪声范围内 → 实盘(2万/5-8只)用简化版，
研究组合(20只)用五因子版。

用法:
    python scripts/run_factor_portfolio.py --top-n 8
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from quant.config import Config  # noqa: E402
from quant.data import load_panels, load_universe  # noqa: E402
from quant.portfolio import (  # noqa: E402
    PortfolioEngine,
    build_weight_series,
    composite_score,
    jaccard_similarity,
)

PANEL_DIR = Path(__file__).resolve().parents[1] / "data" / "cache" / "factor_panels"
STOCK_BASIC = Path(__file__).resolve().parents[1] / "data" / "cache" / "stock_basic.parquet"

# 两套权重（Kimi 定稿表）
WEIGHTS_FIVE = {"low_turnover": 0.40, "low_pb": 0.20, "high_dividend": 0.15,
                "ep": 0.10, "low_ps": 0.10}
WEIGHTS_THREE = {"low_turnover": 0.50, "low_pb": 0.30, "high_dividend": 0.20}


def main() -> None:
    ap = argparse.ArgumentParser(description="因子选股组合回测（五因子 vs 三因子）")
    ap.add_argument("--top-n", type=int, default=8, help="持仓只数（实盘约束 5-8）")
    ap.add_argument("--capital", type=float, default=20_000.0)
    ap.add_argument("--max-per-industry", type=int, default=None,
                    help="行业上限（None=不限；建议 3，防组合变行业 β 策略）")
    ap.add_argument("--rebalance", choices=["weekly", "biweekly"], default="weekly",
                    help="调仓频率（biweekly = 隔周调仓，降摩擦）")
    ap.add_argument("--start", type=str, default=None, help="起始日期 YYYY-MM-DD（分段验证用）")
    ap.add_argument("--end", type=str, default=None, help="截止日期 YYYY-MM-DD")
    args = ap.parse_args()

    panels = load_panels(PANEL_DIR)
    if args.start or args.end:
        for col in panels:
            panels[col] = panels[col].loc[args.start or "2000-01-01": args.end or "2999-12-31"]
    universe = load_universe(STOCK_BASIC)
    # 复权价（分红计入）作为组合价格 —— v3 口径
    prices = panels["close"].astype(float) * panels["adj_factor"].astype(float)

    print(f"=== 因子选股组合回测 Top {args.top_n} [{args.rebalance}] ===")
    results = {}
    overlap_series = pd.Series(index=prices.index, dtype=float)

    for label, weights in [("五因子", WEIGHTS_FIVE), ("三因子", WEIGHTS_THREE)]:
        w = build_weight_series(panels, universe, weights, args.top_n,
                                args.max_per_industry)
        if args.rebalance == "biweekly":
            w = w.copy()
            w.iloc[1::2] = np.nan  # 隔周不调仓（NaN 行 = 无决策）
        r = PortfolioEngine(Config()).run(prices, prices, w,
                                          initial_capital=args.capital, cash_buffer=0.05)
        results[label] = r
        m = r.metrics
        print(f"\n--- {label}版 (Top {args.top_n}) ---")
        print(f"  总收益 {m['total_return']*100:+.2f}%  年化 {m['annual_return']*100:+.2f}%  "
              f"夏普 {m['sharpe']:.2f}  最大回撤 {m['max_drawdown']*100:.1f}%  "
              f"换手 {m['turnover']:.1f}  交易 {m['trade_count']} 笔  "
              f"持仓数 {m.get('final_position_count', '?')}")

    # Top-N 重合度（每周两版选出股票集合的 Jaccard）
    w5 = build_weight_series(panels, universe, WEIGHTS_FIVE, args.top_n, args.max_per_industry)
    w3 = build_weight_series(panels, universe, WEIGHTS_THREE, args.top_n, args.max_per_industry)
    for date in w5.index.intersection(w3.index):
        s5 = set(w5.loc[date][w5.loc[date] > 0].index)
        s3 = set(w3.loc[date][w3.loc[date] > 0].index)
        overlap_series.loc[date] = jaccard_similarity(s5, s3)
    print(f"\nTop-N 重合度（Jaccard）: 均值 {overlap_series.mean():.2f}  "
          f"中位 {overlap_series.median():.2f}")

    # 报告落盘
    report = [f"# 因子选股组合回测报告（Top {args.top_n}）", "",
              f"- 方法: 周频截面打分（winsorize→中性化→zscore→加权）→ Top{args.top_n} 等权，T+1 复权价执行",
              f"- 五因子: 低换手0.40/低PB0.20/高股息0.15/E/P0.10/低PS0.10",
              f"- 三因子: 低换手0.50/低PB0.30/高股息0.20", "",
              "| 版本 | 总收益 | 年化 | 夏普 | 最大回撤 | 换手 | 交易笔数 |", "|---|---|---|---|---|---|---|"]
    for label in ["五因子", "三因子"]:
        m = results[label].metrics
        report.append(f"| {label} | {m['total_return']*100:+.2f}% | {m['annual_return']*100:+.2f}% "
                      f"| {m['sharpe']:.2f} | {m['max_drawdown']*100:.1f}% | {m['turnover']:.1f} "
                      f"| {m['trade_count']} |")
    report += ["", f"Top-N 重合度（Jaccard 均值）: {overlap_series.mean():.2f}", "",
               "*工具: quant/portfolio/engine.py + factors/ ｜ 复权价、含完整成本*"]
    out = Path(__file__).resolve().parents[1] / "data" / "output" / "portfolio_report.md"
    out.write_text("\n".join(report), encoding="utf-8")
    print(f"\n报告已保存: {out}")


if __name__ == "__main__":
    main()
