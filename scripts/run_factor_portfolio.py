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
from quant.portfolio import (  # noqa: E402
    PortfolioEngine,
    composite_score,
    jaccard_similarity,
    top_n_weights_industry_capped,
)

PANEL_DIR = Path(__file__).resolve().parents[1] / "data" / "cache" / "factor_panels"
STOCK_BASIC = Path(__file__).resolve().parents[1] / "data" / "cache" / "stock_basic.parquet"

# 两套权重（Kimi 定稿表）
WEIGHTS_FIVE = {"low_turnover": 0.40, "low_pb": 0.20, "high_dividend": 0.15,
                "ep": 0.10, "low_ps": 0.10}
WEIGHTS_THREE = {"low_turnover": 0.50, "low_pb": 0.30, "high_dividend": 0.20}


def load_panels(panel_dir: Path) -> dict[str, pd.DataFrame]:
    files = sorted(panel_dir.glob("*.parquet"))
    frames = {f.stem: pd.read_parquet(f).set_index("ts_code") for f in files}
    dates = sorted(frames.keys())
    all_codes = sorted(set().union(*[set(frames[d].index) for d in dates]))
    cols = ["close", "pe_ttm", "pb", "ps_ttm", "total_mv", "turnover_rate", "dv_ttm", "adj_factor"]
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


def load_universe() -> pd.DataFrame:
    """股票池: 当前上市 + 行业映射 + ST 标记。"""
    sb = pd.read_parquet(STOCK_BASIC)
    sb["is_st"] = sb["name"].astype(str).str.contains("ST|退", na=False)
    return sb.set_index("ts_code")


def build_weights_series(panels, universe, weights: dict, top_n: int,
                         max_per_industry: int | None = None) -> pd.DataFrame:
    """每周截面: 打分 → Top N 等权权重向量（date × stock）。

    max_per_industry: 行业上限（None=不限；Kimi 审查 3.1：防组合变行业 β 策略）。
    """
    rows = {}
    for date in panels["close"].index:
        cross = pd.DataFrame({
            "low_turnover": panels["turnover_rate"].loc[date],
            "low_pb": panels["pb"].loc[date],
            "high_dividend": panels["dv_ttm"].loc[date],
            "ep": panels["pe_ttm"].loc[date],
            "low_ps": panels["ps_ttm"].loc[date],
            "close": panels["close"].loc[date],   # 停牌过滤用
        })
        # 过滤 ST / 停牌（close 缺失）/ 北交所
        cross = cross[~cross.index.map(universe["is_st"]).fillna(True)]
        cross = cross[~cross.index.str.endswith(".BJ")]
        cross = cross.dropna(subset=["close"])
        if len(cross) < top_n * 3:
            continue
        score = composite_score(cross, weights, universe["industry"])
        if max_per_industry:
            w_row = top_n_weights_industry_capped(
                score, top_n, universe["industry"], max_per_industry)
        else:
            top = score.nlargest(top_n)
            w_row = pd.Series(0.0, index=score.index)
            w_row[top.index] = 1.0 / top_n
        w = pd.Series(0.0, index=panels["close"].columns)
        w[w_row.index] = w_row
        rows[date] = w
    return pd.DataFrame(rows).T


def jaccard_similarity(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def main() -> None:
    ap = argparse.ArgumentParser(description="因子选股组合回测（五因子 vs 三因子）")
    ap.add_argument("--top-n", type=int, default=8, help="持仓只数（实盘约束 5-8）")
    ap.add_argument("--capital", type=float, default=20_000.0)
    ap.add_argument("--max-per-industry", type=int, default=None,
                    help="行业上限（None=不限；建议 3，防组合变行业 β 策略）")
    args = ap.parse_args()

    panels = load_panels(PANEL_DIR)
    universe = load_universe()
    # 复权价（分红计入）作为组合价格 —— v3 口径
    prices = panels["close"].astype(float) * panels["adj_factor"].astype(float)

    print(f"=== 因子选股组合回测 Top {args.top_n} ===")
    results = {}
    overlap_series = pd.Series(index=prices.index, dtype=float)

    for label, weights in [("五因子", WEIGHTS_FIVE), ("三因子", WEIGHTS_THREE)]:
        w = build_weights_series(panels, universe, weights, args.top_n,
                                 args.max_per_industry)
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
    w5 = build_weights_series(panels, universe, WEIGHTS_FIVE, args.top_n, args.max_per_industry)
    w3 = build_weights_series(panels, universe, WEIGHTS_THREE, args.top_n, args.max_per_industry)
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
