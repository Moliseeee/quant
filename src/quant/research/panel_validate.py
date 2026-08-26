"""通用因子面板验证：IC/ICIR/分年/中性化/相关矩阵（正式复跑链路）。

让财务/情绪/未来所有因子面板都有可复跑的一键验证命令（Codex 审查要求：
IC 验证不能只有临时快筛脚本）。流程与 validate_factors.py 一致：
原始 IC → 行业+市值中性化 IC → ICIR/t/正占比 → 分年 → 相关矩阵。
"""

from __future__ import annotations

import pandas as pd
from pathlib import Path

from ..factors.emotion import build_emotion_factors
from ..factors.ic import ic_summary, rank_ic
from ..factors.processing import adjusted_forward_return, neutralize


def load_wide_panels(panel_dir: Path, cols: list[str]) -> dict[str, pd.DataFrame]:
    """读截面目录为 date×stock 宽表面板。"""
    dates = sorted(p.name.replace(".parquet", "") for p in panel_dir.glob("*.parquet"))
    if not dates:
        raise FileNotFoundError(f"无截面数据: {panel_dir}")
    panels: dict[str, pd.DataFrame] = {}
    for col in cols:
        m = {pd.Timestamp(d): pd.read_parquet(panel_dir / f"{d}.parquet").set_index("ts_code")[col]
             for d in dates}
        panels[col] = pd.concat(m, axis=1).T
        panels[col].index.name = "date"
    return panels


def build_factor_panels(kind: str, root: Path) -> dict[str, pd.DataFrame]:
    """按面板类型构造因子面板（越大越好方向）。

    kind:
        financial - roe/gross_margin/rev_yoy/profit_yoy（东财业绩报表原始值）
        sentiment - neg_margin_chg_4w/neg_lhb_count_4w（情绪反向因子，emotion.py）
    """
    data_dir = root / "data" / "cache"
    if kind == "financial":
        p = load_wide_panels(data_dir / "financial_panels",
                             ["roe", "gross_margin", "rev_yoy", "profit_yoy"])
        return {name: p[name] for name in ["roe", "gross_margin", "rev_yoy", "profit_yoy"]}
    if kind == "sentiment":
        return build_emotion_factors(data_dir / "sentiment_panels")
    raise ValueError(f"未知面板类型: {kind}（支持 financial/sentiment）")


def load_context(root: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
    """市值面板 + 行业映射 + 复权收盘价/复权因子（中性化与远期收益用）。"""
    ff_dir = root / "data" / "cache" / "factor_panels"
    dates = sorted(p.name.replace(".parquet", "") for p in ff_dir.glob("*.parquet"))
    mv = {pd.Timestamp(d): pd.read_parquet(ff_dir / f"{d}.parquet").set_index("ts_code")["total_mv"]
          for d in dates}
    close = {pd.Timestamp(d): pd.read_parquet(ff_dir / f"{d}.parquet").set_index("ts_code")["close"]
             for d in dates}
    adj = {pd.Timestamp(d): pd.read_parquet(ff_dir / f"{d}.parquet").set_index("ts_code")["adj_factor"]
           for d in dates}
    mv_p = pd.concat(mv, axis=1).T
    close_p = pd.concat(close, axis=1).T
    adj_p = pd.concat(adj, axis=1).T
    for x in (mv_p, close_p, adj_p):
        x.index.name = "date"

    sb_path = root / "data" / "cache" / "stock_basic.parquet"
    if sb_path.exists():
        sb = pd.read_parquet(sb_path).set_index("ts_code")
        industry_map = sb["industry"]
    else:
        industry_map = pd.Series(dtype=object)
    return mv_p, industry_map, close_p, adj_p


def neutralize_panel(f: pd.DataFrame, mv: pd.DataFrame,
                     industry_map: pd.Series, min_stocks: int = 200) -> pd.DataFrame:
    """逐截面行业+市值中性化（残差面板）。"""
    out = pd.DataFrame(index=f.index, columns=f.columns, dtype=float)
    for date in f.index:
        cross = pd.DataFrame({"factor": f.loc[date], "total_mv": mv.loc[date]})
        cross["industry"] = cross.index.map(industry_map)
        cross = cross.dropna(subset=["factor", "total_mv"])
        cross["industry"] = cross["industry"].fillna("UNKNOWN")
        if len(cross) < min_stocks:
            continue
        res = neutralize(cross, "factor", industry_col="industry", mv_col="total_mv")
        out.loc[date, res.index] = res
    return out


def ic_table(factors: dict[str, pd.DataFrame], fwd_by_h: dict[int, pd.DataFrame],
             mv: pd.DataFrame, industry_map: pd.Series) -> pd.DataFrame:
    """逐因子 × 持有期 IC 汇总表（原始 + 中性化）。

    Args:
        factors: {因子名: date×stock 因子面板（越大越好）}
        fwd_by_h: {horizon: 复权远期收益面板}
        mv: 市值面板；industry_map: 行业映射
    """
    rows = []
    for name, panel in factors.items():
        resid = neutralize_panel(panel, mv, industry_map)
        for h, fw in fwd_by_h.items():
            ic_raw = rank_ic(panel, fw, min_obs=30)
            ic_n = rank_ic(resid, fw, min_obs=30)
            s_raw = ic_summary(ic_raw) if len(ic_raw) else {}
            s_n = ic_summary(ic_n) if len(ic_n) else {}
            rows.append({
                "factor": name, "horizon": h,
                "raw_ic": s_raw.get("mean_ic", float("nan")),
                "neut_ic": s_n.get("mean_ic", float("nan")),
                "icir": s_n.get("icir", float("nan")),
                "t": s_n.get("t_stat", float("nan")),
                "pos_ratio": s_n.get("positive_ratio", float("nan")),
                "n": len(ic_n),
            })
    return pd.DataFrame(rows)


def ic_by_year(factors: dict[str, pd.DataFrame], fwd: pd.DataFrame, mv: pd.DataFrame,
               industry_map: pd.Series, horizon: int = 1) -> pd.DataFrame:
    """中性化后分年 mean_IC 表。"""
    rows = {}
    for name, panel in factors.items():
        resid = neutralize_panel(panel, mv, industry_map)
        ic = rank_ic(resid, fwd, min_obs=30)
        rows[name] = {str(y): round(ic[ic.index.year == y].mean(), 4)
                      for y in sorted(ic.index.year.unique())}
    return pd.DataFrame(rows).T
