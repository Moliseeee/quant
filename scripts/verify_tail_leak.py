#!/usr/bin/env python
"""Kimi 独立归因核验 v3：alpha 在排名→组合之间哪个环节漏掉。

已确认事实：
  - 三因子 Q10 十分组在 2025-26H1 仍跑赢市场均值（+4.2 bps/周）
  - 但 Top8 组合同期 -4.36%，跑输周频等权市场约 11pt
  → 矛盾只能在"Q10(约500只) → Top8(极端尾部)"之间。

本脚本：逐周截面取合成得分 Top K（K=8/20/50/100/十分组），
对比各档平均远期周收益；另测"行业≤3 约束下 Top8"（复刻实盘选股规则）。
若 Top8 极端尾部显著弱于 Q10 整体 → 问题在极端尾部选股，不在因子。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd  # noqa: E402

from quant.data.panels import load_panels  # noqa: E402
from quant.factors.processing import adjusted_forward_return, winsorize, zscore  # noqa: E402

PANEL_DIR = Path(__file__).resolve().parents[1] / "data" / "cache" / "factor_panels"
STOCK_BASIC = Path(__file__).resolve().parents[1] / "data" / "cache" / "stock_basic.parquet"

panels = load_panels(PANEL_DIR)
fwd = adjusted_forward_return(panels["close"], panels["adj_factor"])
industry = pd.read_parquet(STOCK_BASIC).set_index("ts_code")["industry"]

SEGMENTS = {"2023": ("2023-01-01", "2023-12-31"), "2025-26H1": ("2025-01-01", "2026-07-31")}


def score3_at(date):
    cross = pd.DataFrame({
        "t": panels["turnover_rate"].loc[date].astype(float),
        "pb": panels["pb"].loc[date].astype(float),
        "dv": panels["dv_ttm"].loc[date].astype(float),
    })
    return (-0.5 * zscore(winsorize(cross["t"]))
            - 0.3 * zscore(winsorize(cross["pb"]))
            + 0.2 * zscore(winsorize(cross["dv"])))


def industry_capped_top(score: pd.Series, k: int, cap: int):
    s = score.sort_values(ascending=False)
    picked, counts = [], {}
    ind_map = industry.to_dict()
    for stock in s.index:
        if len(picked) >= k:
            break
        i = ind_map.get(stock)
        if i is None or (isinstance(i, float) and pd.isna(i)):
            picked.append(stock)
            continue
        if counts.get(i, 0) < cap:
            picked.append(stock)
            counts[i] = counts.get(i, 0) + 1
    return picked


for seg_name, (s, e) in SEGMENTS.items():
    rows = {"Top8": [], "Top8_行业≤3": [], "Top20": [], "Top50": [],
            "Top100": [], "Q10整体": [], "市场均值": []}
    for date in fwd.loc[s:e].index:
        sc = score3_at(date).dropna()
        r = fwd.loc[date]
        common = sc.index.intersection(r.dropna().index)
        if len(common) < 300:
            continue
        sc, r = sc.loc[common], r.loc[common]
        ranked = sc.sort_values(ascending=False)
        rows["Top8"].append(r[ranked.index[:8]].mean())
        rows["Top8_行业≤3"].append(r[industry_capped_top(sc, 8, 3)].mean())
        rows["Top20"].append(r[ranked.index[:20]].mean())
        rows["Top50"].append(r[ranked.index[:50]].mean())
        rows["Top100"].append(r[ranked.index[:100]].mean())
        q10 = ranked.index[: len(ranked) // 10]
        rows["Q10整体"].append(r[q10].mean())
        rows["市场均值"].append(r.mean())
    print(f"\n--- {seg_name}（平均远期周收益，bps）---")
    mkt = pd.Series(rows["市场均值"]).mean() * 1e4
    for k in ["Top8", "Top8_行业≤3", "Top20", "Top50", "Top100", "Q10整体"]:
        v = pd.Series(rows[k]).mean() * 1e4
        print(f"  {k:<12} {v:+7.1f} bps ｜ vs 市场 {v-mkt:+6.1f} bps")
    print(f"  {'市场均值':<12} {mkt:+7.1f} bps")
