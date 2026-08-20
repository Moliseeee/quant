"""因子预处理：极值处理、标准化、行业/市值中性化。

机构级因子研究的三大基本功：
1. winsorize   — 剔除极端值干扰（MAD 法更稳健，中位数不受极端值影响）
2. zscore      — 无量纲化
3. neutralize  — 消除行业偏好与小市值暴露（否则因子选出的股票全挤一个行业）
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def winsorize(
    s: pd.Series, method: str = "mad", n: float = 3.0, lower: float = 0.01, upper: float = 0.99
) -> pd.Series:
    """极值处理。

    - method="mad": 中位数 ± n * MAD（稳健，推荐）
    - method="quantile": 分位数截尾（默认 1%/99%）
    """
    s = s.astype(float)
    if method == "mad":
        med = s.median()
        mad = (s - med).abs().median()
        if mad == 0 or np.isnan(mad):
            return s
        lo, hi = med - n * 1.4826 * mad, med + n * 1.4826 * mad
    elif method == "quantile":
        lo, hi = s.quantile(lower), s.quantile(upper)
    else:
        raise ValueError(f"未知方法: {method}")
    return s.clip(lo, hi)


def zscore(s: pd.Series) -> pd.Series:
    """z-score 标准化（需先 winsorize）。"""
    std = s.std(ddof=0)
    if std == 0 or np.isnan(std):
        return pd.Series(0.0, index=s.index)
    return (s - s.mean()) / std


def neutralize(
    df: pd.DataFrame,
    factor: str,
    industry_col: str = "industry",
    mv_col: str | None = "total_mv",
    use_log_mv: bool = True,
) -> pd.Series:
    """行业 + 市值中性化：因子值对行业哑变量和 ln(市值) 回归，取残差。

    残差 = 剔除行业与市值影响后的纯因子暴露。
    依赖 numpy 最小二乘（无 statsmodels 也能跑）。
    """
    data = df[[factor]].copy()
    data["_const"] = 1.0

    # 行业哑变量
    if industry_col and industry_col in df.columns:
        dummies = pd.get_dummies(df[industry_col], prefix="ind", drop_first=True)
        data = pd.concat([data, dummies], axis=1)

    # 市值（对数）
    if mv_col and mv_col in df.columns:
        mv = df[mv_col].astype(float)
        data["_log_mv"] = np.log(mv.replace(0, np.nan))

    data = data.replace([np.inf, -np.inf], np.nan)
    valid = data.dropna()
    if len(valid) < 30:
        return pd.Series(np.nan, index=df.index)

    X = valid.drop(columns=[factor]).to_numpy(dtype=float)
    y = valid[factor].to_numpy(dtype=float)

    # 最小二乘: beta = (X'X)^-1 X'y
    try:
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    except np.linalg.LinAlgError:
        return pd.Series(np.nan, index=df.index)

    resid = pd.Series(y - X @ beta, index=valid.index)
    out = pd.Series(np.nan, index=df.index)
    out.loc[resid.index] = resid
    return out


def standard_factor_pipeline(
    df: pd.DataFrame,
    factor: str,
    industry_col: str = "industry",
    mv_col: str | None = "total_mv",
) -> pd.Series:
    """完整因子预处理流水线: winsorize(MAD) → 中性化 → zscore。"""
    f = winsorize(df[factor])
    tmp = df.copy()
    tmp[factor] = f
    neutral = neutralize(tmp, factor, industry_col, mv_col)
    return zscore(neutral)


def ep_transform(pe: pd.Series) -> pd.Series:
    """E/P 盈利收益率口径（Kimi 审查修复）:
    pe > 0 过滤后取倒数——亏损股（负 PE）置 NaN，不参与排序。

    低 PE 因子直接用 pe 排序时，负 PE（亏损股）会堆在"低 PE"端，
    这批恰恰是垃圾股，系统性污染单调性、压低 IC。
    E/P 越大 = 越便宜且盈利，方向统一为"越大越好"。
    """
    pe = pe.astype(float)
    return 1.0 / pe.where(pe > 0)


def adjusted_forward_return(close: pd.Series | pd.DataFrame,
                            adj_factor: pd.Series | pd.DataFrame,
                            horizon: int = 1) -> pd.Series | pd.DataFrame:
    """复权远期收益（Kimi 审查修复）:
    fwd = (close×adj).shift(-horizon) / (close×adj) - 1

    用未复权收盘价算收益会漏掉现金分红——高股息因子被系统性低估。
    复权价 = 未复权价 × adj_factor，近似含分红再投资。
    """
    adj_close = close.astype(float) * adj_factor.astype(float)
    return adj_close.shift(-horizon) / adj_close - 1
