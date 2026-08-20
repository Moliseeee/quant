#!/usr/bin/env python
"""Kimi 独立归因核验 v2。

两大疑问：
  1. Hermes 称"全市场等权 2025-26H1 +29.14%"，面板逐周复利仅 +6.91% —— 口径分歧定位
  2. IC 为正 vs 组合巨亏的矛盾：低换手/三因子十分组形态（极尾塌陷 or 因子失效）
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from quant.data.panels import load_panels  # noqa: E402
from quant.factors.processing import adjusted_forward_return, winsorize, zscore  # noqa: E402

PANEL_DIR = Path(__file__).resolve().parents[1] / "data" / "cache" / "factor_panels"

panels = load_panels(PANEL_DIR)
prices = panels["close"].astype(float) * panels["adj_factor"].astype(float)
fwd = adjusted_forward_return(panels["close"], panels["adj_factor"])

SEGMENTS = {"2023": ("2023-01-01", "2023-12-31"), "2025-26H1": ("2025-01-01", "2026-07-31")}

print("=== 1. 全市场收益：四种口径对照 ===")
weekly_ret = prices.pct_change()
for name, (s, e) in SEGMENTS.items():
    seg_w = weekly_ret.loc[s:e]
    # 口径A：逐周等权复利（周频再平衡等权组合）
    a = (1 + seg_w.mean(axis=1, skipna=True).dropna()).prod() - 1
    # 口径B：买入持有等权（期初在场股票，个股全程总收益的均值）
    pseg = prices.loc[s:e]
    tot = []
    for c in pseg.columns:
        p1 = pseg[c].dropna()
        if len(p1) > 1 and p1.iloc[0] > 0:
            tot.append(p1.iloc[-1] / p1.iloc[0] - 1)
    b = np.mean(tot)
    # 口径C：同B但用未复权价（分红丢失，检验口径敏感性）
    praw = panels["close"].astype(float).loc[s:e]
    tot_r = []
    for c in praw.columns:
        p1 = praw[c].dropna()
        if len(p1) > 1 and p1.iloc[0] > 0:
            tot_r.append(p1.iloc[-1] / p1.iloc[0] - 1)
    cc = np.mean(tot_r)
    # 口径D：逐周等权复利但用"当周在场股票"（dropna 后当周横截面均值，与A同义但含新上市）
    print(f"  {name}: A周频等权复利 {a*100:+.2f}% ｜ B买入持有等权 {b*100:+.2f}% ｜ C未复权买入持有 {cc*100:+.2f}%")

print("\n=== 2. 十分组形态（组内等权平均远期周收益，bps；Q1=因子值最小）===")


def decile_profile(factor_fn, seg_start: str, seg_end: str) -> pd.Series:
    outs = []
    for date in fwd.loc[seg_start:seg_end].index:
        f = factor_fn(date).dropna()
        r = fwd.loc[date]
        common = f.index.intersection(r.dropna().index)
        if len(common) < 300:
            continue
        q = pd.qcut(f.loc[common].rank(method="first"), 10, labels=False)
        outs.append(pd.DataFrame({"q": q, "r": r.loc[common]}).groupby("q")["r"].mean())
    m = pd.DataFrame(outs).mean()
    m.index = [f"Q{i+1}" for i in m.index]
    return m * 1e4


def turnover_at(date):
    return panels["turnover_rate"].loc[date].astype(float)


def score3_at(date):
    cross = pd.DataFrame({
        "t": panels["turnover_rate"].loc[date].astype(float),
        "pb": panels["pb"].loc[date].astype(float),
        "dv": panels["dv_ttm"].loc[date].astype(float),
    })
    return (-0.5 * zscore(winsorize(cross["t"]))
            - 0.3 * zscore(winsorize(cross["pb"]))
            + 0.2 * zscore(winsorize(cross["dv"])))


for seg_name, (s, e) in SEGMENTS.items():
    mkt = fwd.loc[s:e].mean().mean() * 1e4
    print(f"\n--- {seg_name}（全市场均值 {mkt:+.1f} bps/周）---")
    prof_t = decile_profile(turnover_at, s, e)
    print(f"  低换手十分组 Q1(最低换手)→Q10: {[round(v,1) for v in prof_t]}")
    print(f"    Q1 vs 市场: {prof_t.iloc[0]-mkt:+.1f} bps ｜ 单调性(Q1>Q10): {prof_t.iloc[0] > prof_t.iloc[-1]}")
    prof_s = decile_profile(score3_at, s, e)
    print(f"  三因子得分十分组 Q1→Q10(最高分): {[round(v,1) for v in prof_s]}")
    print(f"    Q10 vs 市场: {prof_s.iloc[-1]-mkt:+.1f} bps ｜ 单调性(Q10>Q1): {prof_s.iloc[-1] > prof_s.iloc[0]}")
