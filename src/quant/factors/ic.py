"""因子有效性检验：Rank IC / ICIR / 分层收益。

这是"胜率验证"的核心 —— 一个因子有没有用，不是看它选出过牛股，
而是看它在历史上对截面未来收益有没有稳定的预测力（IC）。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def forward_returns(
    close: pd.DataFrame,
    horizon: int = 20,
) -> pd.DataFrame:
    """面板未来收益：close 为 date×stock 收盘价面板，返回未来 horizon 日收益。

    fwd[t, s] = close[t+horizon, s] / close[t, s] - 1
    """
    return close.shift(-horizon) / close - 1


def rank_ic(
    factor_panel: pd.DataFrame,
    fwd_ret: pd.DataFrame,
    min_obs: int = 30,
) -> pd.Series:
    """逐期 Rank IC（Spearman 相关），返回按日期索引的 IC 序列。

    factor_panel: date×stock 因子面板（注意方向：因子越大越好，则 IC>0 有效）
    fwd_ret:      date×stock 未来收益面板
    """
    ic_list, dates = [], []
    for date in factor_panel.index:
        f = factor_panel.loc[date].dropna()
        r = fwd_ret.loc[date].reindex(f.index).dropna()
        common = f.index.intersection(r.index)
        if len(common) < min_obs:
            continue
        ic, _ = stats.spearmanr(f[common], r[common])
        if not np.isnan(ic):
            ic_list.append(ic)
            dates.append(date)
    return pd.Series(ic_list, index=pd.DatetimeIndex(dates), name="rank_ic")


def ic_summary(ic: pd.Series) -> dict:
    """IC 序列统计：均值、标准差、ICIR、t 值、正占比。

    判读标准（经验）:
        |mean IC| > 0.02 且 ICIR > 0.3 且 t > 2 → 因子有统计意义
    """
    if len(ic) == 0:
        return {"mean_ic": 0.0, "std_ic": 0.0, "icir": 0.0, "t_stat": 0.0,
                "positive_ratio": 0.0, "n_days": 0}
    mean_ic = float(ic.mean())
    std_ic = float(ic.std(ddof=1))
    n = len(ic)
    icir = mean_ic / std_ic if std_ic > 0 else 0.0
    t_stat = mean_ic / (std_ic / np.sqrt(n)) if std_ic > 0 else 0.0
    return {
        "mean_ic": round(mean_ic, 4),
        "std_ic": round(std_ic, 4),
        "icir": round(icir, 4),
        "t_stat": round(t_stat, 2),
        "positive_ratio": round(float((ic > 0).mean()), 4),
        "n_days": n,
    }


def quantile_analysis(
    factor_panel: pd.DataFrame,
    fwd_ret: pd.DataFrame,
    n_quantiles: int = 5,
) -> pd.DataFrame:
    """分层检验：按因子值分 n 组，比较各组未来收益均值。

    单调性（因子越大，未来收益越高/越低）是因子有效的重要证据。
    返回: 各组收益均值、均值差(Q_n - Q_1) 及其显著性。
    """
    rows = []
    for date in factor_panel.index:
        f = factor_panel.loc[date].dropna()
        r = fwd_ret.loc[date].reindex(f.index)
        common = f.dropna().index.intersection(r.dropna().index)
        if len(common) < n_quantiles * 20:
            continue
        q = pd.qcut(f[common], n_quantiles, labels=False, duplicates="drop")
        g = pd.DataFrame({"q": q, "ret": r[common]}).dropna()
        for qi in range(n_quantiles):
            sub = g[g["q"] == qi]["ret"]
            rows.append({"date": date, "quantile": qi, "ret": sub.mean()})
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame()
    pivot = df.pivot_table(index="date", columns="quantile", values="ret", aggfunc="mean")
    summary = pd.DataFrame({
        "mean_ret": pivot.mean(),
        "std": pivot.std(ddof=1),
        "n_days": pivot.count(),
    })
    # 多空组合收益 (Q_high - Q_low)
    if n_quantiles >= 2 and len(pivot.columns) >= 2:
        long_short = pivot[n_quantiles - 1] - pivot[0]
        summary.loc["LS_long_short"] = {
            "mean_ret": long_short.mean(),
            "std": long_short.std(ddof=1),
            "n_days": long_short.count(),
        }
    return summary
