#!/usr/bin/env python
"""Kimi 核验脚本：周频组合回测指标口径核查。

发现：metrics.py 硬编码 TRADING_DAYS=252（日频假设），但组合引擎喂的是
周频 equity（182 行/3.5 年），导致：
  - 年化收益指数放大 (1+total)^(252/n)
  - 年化波动放大 sqrt(252/52)≈2.2x
  - 换手分母 n_years=len/252≈0.72 年（实际 3.5 年）→ 放大 ~4.85x
本脚本复现 4 组配置并按 52 周/年重算正确口径。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402

from quant.config import Config  # noqa: E402
from quant.portfolio import PortfolioEngine  # noqa: E402
from quant.portfolio.scoring import build_weight_series, jaccard_similarity  # noqa: E402
from run_factor_portfolio import (  # noqa: E402
    PANEL_DIR, WEIGHTS_FIVE, WEIGHTS_THREE, load_panels, load_universe,
)

panels = load_panels(PANEL_DIR)
universe = load_universe()
prices = panels["close"].astype(float) * panels["adj_factor"].astype(float)
n_weeks = len(prices)
years = n_weeks / 52.0
print(f"截面数 {n_weeks} 周 ≈ {years:.2f} 年\n")

hdr = (f"{'配置':<22} {'总收益':>8} {'年化(252口径)':>12} {'年化(52周正确)':>14} "
       f"{'夏普(252)':>9} {'夏普(52)':>8} {'回撤':>7} {'换手(252)':>9} {'换手(52)':>8}")
print(hdr)
for label, weights, cap in [("五因子 无上限", WEIGHTS_FIVE, None),
                            ("三因子 无上限", WEIGHTS_THREE, None),
                            ("五因子 行业≤3", WEIGHTS_FIVE, 3),
                            ("三因子 行业≤3", WEIGHTS_THREE, 3)]:
    w = build_weight_series(panels, universe, weights, 8, max_per_industry=cap)
    r = PortfolioEngine(Config()).run(prices, prices, w,
                                      initial_capital=20000, cash_buffer=0.05)
    m = r.metrics
    eq = r.equity
    total = m["total_return"]
    cagr = (1 + total) ** (52.0 / n_weeks) - 1
    vol52 = float(eq.pct_change().dropna().std(ddof=1) * np.sqrt(52))
    sharpe52 = cagr / vol52 if vol52 > 1e-10 else 0.0
    traded = sum(abs(t.net_amount) for t in r.trades)
    turn52 = traded / float(eq.mean()) / years
    print(f"{label:<22} {total*100:>+7.2f}% {m['annual_return']*100:>+11.2f}% "
          f"{cagr*100:>+13.2f}% {m['sharpe']:>9.2f} {sharpe52:>8.2f} "
          f"{m['max_drawdown']*100:>6.1f}% {m['turnover']:>9.1f} {turn52:>8.1f}")

# Jaccard 复核（cap=3）
from quant.portfolio.scoring import jaccard_similarity  # noqa: E402
w5 = build_weight_series(panels, universe, WEIGHTS_FIVE, 8, max_per_industry=3)
w3 = build_weight_series(panels, universe, WEIGHTS_THREE, 8, max_per_industry=3)
jac = []
for d in w5.index.intersection(w3.index):
    s5 = set(w5.loc[d][w5.loc[d] > 0].index)
    s3 = set(w3.loc[d][w3.loc[d] > 0].index)
    jac.append(jaccard_similarity(s5, s3))
print(f"\n行业≤3 下 Jaccard: 均值 {np.mean(jac):.2f} 中位 {np.median(jac):.2f}")
