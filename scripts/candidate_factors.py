#!/usr/bin/env python
"""候选因子扩充验证：动量/波动率等（用现有面板即可构造，无需新数据）。

流程: 构造候选因子 → RankIC/ICIR → 中性化 → 与现有 3 因子相关矩阵 → 判定是否值得加入。
逻辑在 quant/research/attribution.py + quant/factors/ 中，本脚本为 CLI 壳。
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from quant.data import load_panels  # noqa: E402
from quant.factors.ic import ic_summary, rank_ic  # noqa: E402
from quant.factors.processing import adjusted_forward_return, winsorize, zscore  # noqa: E402
from quant.research import neutralize_panel  # noqa: E402

PANEL_DIR = Path(__file__).resolve().parents[1] / "data" / "cache" / "factor_panels"
STOCK_BASIC = Path(__file__).resolve().parents[1] / "data" / "cache" / "stock_basic.parquet"

EXISTING = ["low_turnover", "low_pb", "high_dividend"]


def build_candidates(panels: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """从 close 面板构造动量/波动率候选因子（越大越好方向）。"""
    close = panels["close"].astype(float)
    ac = close * panels["adj_factor"].astype(float)  # 复权价
    cand: dict[str, pd.DataFrame] = {}

    # 动量: 过去 4/8/26 周收益（复权），越大越好
    for n, name in [(4, "mom_1m"), (8, "mom_2m"), (26, "mom_6m")]:
        cand[name] = ac / ac.shift(n) - 1

    # 反转: 过去 1 周收益（越大越好 = 短期反转做多）
    cand["rev_1w"] = ac / ac.shift(1) - 1

    # 波动率: 过去 12 周收益标准差（越大越好方向为低波 → 取负）
    ret = ac.pct_change()
    cand["low_vol_3m"] = -ret.rolling(12).std()

    # 换手动量: 换手率 4 周均值（越大越好方向为低换手 → 取负）
    cand["low_turnover_1m"] = -panels["turnover_rate"].astype(float).rolling(4).mean()

    # 市值中性化的动量暴露（动量去掉小市值成分的干扰）
    return {k: v for k, v in cand.items()}


def main() -> None:
    panels = load_panels(PANEL_DIR)
    industry_map = None
    if STOCK_BASIC.exists():
        industry_map = pd.read_parquet(STOCK_BASIC).set_index("ts_code")["industry"]

    fwd = adjusted_forward_return(panels["close"], panels["adj_factor"])
    cand = build_candidates(panels)

    # 现有 3 因子（对照）
    existing = {}
    for name, col, d in [("low_turnover", "turnover_rate", -1.0),
                         ("low_pb", "pb", -1.0),
                         ("high_dividend", "dv_ttm", 1.0)]:
        existing[name] = panels[col].astype(float) * d

    print(f"{'因子':<18} {'原始ICIR':>9} {'中性ICIR':>9}  {'与现有最大|ρ|':>12}  判定")
    print("-" * 70)
    all_f = {**existing, **cand}
    for name in [*EXISTING, *cand.keys()]:
        f = all_f[name]
        s = ic_summary(rank_ic(f, fwd, min_obs=200))
        neu = "—"
        if industry_map is not None and "small_mv" not in name:
            sn = ic_summary(rank_ic(neutralize_panel(f, panels["total_mv"], industry_map),
                                    fwd, min_obs=200))
            neu = f"{sn['icir']:+.3f}"
        else:
            sn = s

        # 与现有 3 因子的最大相关（截面均值，近 52 期）
        max_rho = 0.0
        if name not in EXISTING:
            from scipy import stats

            rhos = []
            for date in f.index[-52:]:
                for en in EXISTING:
                    a = f.loc[date].dropna()
                    b = existing[en].loc[date].reindex(a.index).dropna()
                    common = a.index.intersection(b.index)
                    if len(common) > 100:
                        rho, _ = stats.spearmanr(a[common], b[common])
                        if not np.isnan(rho):
                            rhos.append(abs(rho))
            max_rho = float(np.mean(rhos)) if rhos else 0.0

        verdict = "✅ 候选" if sn["icir"] >= 0.3 and abs(sn["mean_ic"]) >= 0.02 and max_rho < 0.5 else "❌"
        if name in EXISTING:
            verdict = "(现有)"
        print(f"{name:<18} {s['icir']:+8.3f} {neu:>9}  {max_rho:>11.2f}  {verdict}")


if __name__ == "__main__":
    main()
