"""策略失效归因：分段因子 IC 对比（策略研究常规步骤，可测试）。

用途: walk-forward 显示策略近期亏损时，定位是哪个因子失效。
方法: 按时间分段计算各因子 RankIC/ICIR（原始 + 中性化），对比衰减。
"""

from __future__ import annotations

import pandas as pd

from ..factors.ic import ic_summary, rank_ic
from ..factors.processing import adjusted_forward_return, ep_transform, neutralize

# 因子方向: value>0 表示"越大越好"
FACTOR_DIRECTIONS = {
    "low_turnover": ("turnover_rate", -1.0),
    "low_pb": ("pb", -1.0),
    "high_dividend": ("dv_ttm", 1.0),
    "ep": ("pe_ttm", "ep"),
    "small_mv": ("total_mv", -1.0),
}


def build_factors(panels: dict[str, pd.DataFrame],
                  directions: dict | None = None) -> dict[str, pd.DataFrame]:
    """方向标准化因子面板（E/P 特殊处理：pe>0 过滤取倒数）。"""
    directions = directions or FACTOR_DIRECTIONS
    factors: dict[str, pd.DataFrame] = {}
    for name, (col, direction) in directions.items():
        f = panels[col].astype(float)
        factors[name] = ep_transform(f) if direction == "ep" else f * direction
    return factors


def neutralize_panel(f: pd.DataFrame, mv: pd.DataFrame,
                     industry_map: pd.Series) -> pd.DataFrame:
    """逐截面行业+市值中性化（回归残差）。"""
    out = pd.DataFrame(index=f.index, columns=f.columns, dtype=float)
    for date in f.index:
        cross = pd.DataFrame({"factor": f.loc[date], "total_mv": mv.loc[date]})
        cross["industry"] = cross.index.map(industry_map)
        cross = cross.dropna(subset=["factor"])
        if len(cross) < 200:
            continue
        res = neutralize(cross, "factor")
        out.loc[date, res.index] = res
    return out


def segment_factor_ic(
    panels: dict[str, pd.DataFrame],
    segments: list[tuple[str, str, str]],
    industry_map: pd.Series | None = None,
    directions: dict | None = None,
    min_obs: int = 200,
) -> pd.DataFrame:
    """分段因子 ICIR 对比。

    Args:
        panels: 面板（含 close/adj_factor 及因子列）
        segments: [(段名, 开始, 结束), ...]
        industry_map: 行业映射（None = 不做中性化）
        directions: 因子方向表

    Returns:
        DataFrame: MultiIndex(因子, 分段) × [raw_icir, neutral_icir]
    """
    factors = build_factors(panels, directions)
    fwd = adjusted_forward_return(panels["close"], panels["adj_factor"])

    rows: list[dict] = []
    for seg_name, start, end in segments:
        seg_fwd = fwd.loc[start:end]
        for name, f in factors.items():
            s = ic_summary(rank_ic(f.loc[start:end], seg_fwd, min_obs=min_obs))
            row = {"factor": name, "segment": seg_name, "raw_icir": s["icir"]}
            if industry_map is not None and name != "small_mv":
                f_neu = neutralize_panel(
                    f.loc[start:end], panels["total_mv"].loc[start:end], industry_map)
                sn = ic_summary(rank_ic(f_neu, seg_fwd, min_obs=min_obs))
                row["neutral_icir"] = sn["icir"]
            else:
                row["neutral_icir"] = None
            rows.append(row)
    return pd.DataFrame(rows)


def icir_trend(df: pd.DataFrame) -> str:
    """ICIR 趋势行（如 +0.43→+0.40→+0.42 稳定/衰减）。"""
    factor = df["factor"].iloc[0]
    vals = df.sort_values("segment")["raw_icir"].tolist()
    arrow = "→".join(f"{v:+.2f}" for v in vals)
    decay = vals[-1] < vals[0] and vals[-1] < 0.1
    flag = "⚠️ 衰减/失效" if decay else "✅ 稳定"
    return f"{factor:<16} {arrow}  {flag}"
