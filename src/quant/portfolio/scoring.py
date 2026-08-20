"""因子合成打分与重合度（组合选股核心逻辑，可测试）。"""

from __future__ import annotations

import pandas as pd

from ..factors.processing import ep_transform, winsorize, zscore

# 金融行业：PS 口径对金融股怪异（净资产/收入结构特殊），置中性分（Kimi 定稿前提）
FINANCIAL_INDUSTRIES = {"银行", "证券", "保险", "多元金融", "非银金融"}

# 因子构造器：输入原始列 → 方向标准化因子（越大越好）
FACTOR_BUILDERS = {
    "low_turnover": lambda f: f * -1.0,       # 低换手
    "low_pb": lambda f: f * -1.0,             # 低PB
    "high_dividend": lambda f: f * 1.0,       # 高股息
    "ep": lambda f: ep_transform(f),          # E/P（pe>0 过滤，亏损股置缺失）
    "low_ps": lambda f: f * -1.0,             # 低PS
}


def composite_score(
    cross: pd.DataFrame,
    weights: dict[str, float],
    industry_map: pd.Series | None = None,
    financial_industries: set[str] | None = None,
) -> pd.Series:
    """单截面因子合成得分（越大越好）。

    Args:
        cross: ts_code × 因子原始值（列名须为 FACTOR_BUILDERS 的键）
        weights: 因子名 → 权重（和不必为 1，最终只有相对排序有意义）
        industry_map: ts_code → 行业（金融股 PS 置中性需要）
        financial_industries: 金融行业集合

    处理流水线: 方向标准化 → winsorize(MAD) → zscore → 金融股PS中性 → 加权求和。
    """
    fins = financial_industries or FINANCIAL_INDUSTRIES
    score = pd.Series(0.0, index=cross.index)
    for fname, w in weights.items():
        if fname not in cross.columns:
            continue
        f = FACTOR_BUILDERS[fname](cross[fname])
        f = zscore(winsorize(f))
        if fname == "low_ps" and industry_map is not None:
            ind = cross.index.map(industry_map)
            f = f.where(~ind.isin(fins), 0.0)
        score = score + w * f
    return score


def jaccard_similarity(a: set, b: set) -> float:
    """两股票集合的 Jaccard 重合度（0-1）。"""
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def top_n_weights(scores: pd.Series, top_n: int,
                  universe: pd.Series | None = None) -> pd.Series:
    """按得分取 Top N 等权权重向量（index 为股票，未入选为 0）。

    universe: 允许的股票集合（None = 全部）；得分 NaN 的股票自动排除。
    """
    s = scores.dropna()
    if universe is not None:
        s = s[s.index.isin(universe)]
    if len(s) < top_n:
        top_n = len(s)
    if top_n == 0:
        return pd.Series(dtype=float)
    top = s.nlargest(top_n)
    w = pd.Series(0.0, index=s.index)
    w[top.index] = 1.0 / top_n
    return w


def build_weight_series(
    panels: dict[str, pd.DataFrame],
    universe: pd.DataFrame,
    weights: dict[str, float],
    top_n: int,
    max_per_industry: int | None = None,
) -> pd.DataFrame:
    """从周频因子面板构造每周 Top-N 等权权重序列（date × stock）。

    Args:
        panels: {列名: date×stock DataFrame}，须含 turnover_rate/pb/dv_ttm/pe_ttm/ps_ttm/close
        universe: stock_basic DataFrame（index=ts_code，含 industry/is_st 列）
        weights: 因子权重（FACTOR_BUILDERS 的键）
        top_n: 持仓只数
        max_per_industry: 行业上限（None=不限；防组合变行业 β 策略）

    流程（无前视）: 每周截面 → 过滤 ST/北交所/停牌 → 合成打分 → Top N → 等权。
    """
    rows = {}
    for date in panels["close"].index:
        cross = pd.DataFrame({
            "low_turnover": panels["turnover_rate"].loc[date],
            "low_pb": panels["pb"].loc[date],
            "high_dividend": panels["dv_ttm"].loc[date],
            "ep": panels["pe_ttm"].loc[date],
            "low_ps": panels["ps_ttm"].loc[date],
            "close": panels["close"].loc[date],  # 停牌过滤用
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
            w_row = top_n_weights(score, top_n)
        w = pd.Series(0.0, index=panels["close"].columns)
        w[w_row.index] = w_row
        rows[date] = w
    return pd.DataFrame(rows).T


def top_n_weights_industry_capped(
    scores: pd.Series,
    top_n: int,
    industry_map: pd.Series,
    max_per_industry: int,
) -> pd.Series:
    """行业上限约束的 Top N 选股（Kimi 审查 3.1 修复）。

    防"多因子同向指向单一行业（如银行）→ 组合变成行业 β 策略"。
    按得分从高到低遍历，同一行业最多取 max_per_industry 只。
    """
    s = scores.dropna()
    if len(s) < top_n:
        top_n = len(s)
    if top_n == 0:
        return pd.Series(dtype=float)
    ind_map = industry_map.to_dict()
    picked: list = []
    counts: dict = {}
    for stock in s.sort_values(ascending=False).index:
        if len(picked) >= top_n:
            break
        i = ind_map.get(stock)
        if i is None or (isinstance(i, float) and pd.isna(i)):
            picked.append(stock)  # 未知行业不占名额限制（保守放行）
            continue
        if counts.get(i, 0) < max_per_industry:
            picked.append(stock)
            counts[i] = counts.get(i, 0) + 1
    w = pd.Series(0.0, index=s.index)
    if picked:
        w[picked] = 1.0 / len(picked)
    return w
