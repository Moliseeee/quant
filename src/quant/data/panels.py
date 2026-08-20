"""周频因子面板加载（统一入口，脚本间复用 + 可测试）。

数据来源: data/cache/factor_panels/<YYYYMMDD>.parquet（fetch_factor_data.py 产物）
面板结构: {列名: date×stock DataFrame}，列为 close/pe_ttm/pb/ps_ttm/total_mv/
turnover_rate/dv_ttm/adj_factor。
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

# 面板中所有可加载的列
PANEL_COLUMNS = [
    "close", "pe", "pe_ttm", "pb", "ps", "ps_ttm", "total_mv", "circ_mv",
    "turnover_rate", "dv_ttm", "adj_factor",
]


def load_panels(panel_dir: Path, columns: list[str] | None = None) -> dict[str, pd.DataFrame]:
    """加载全部截面 parquet → {列名: date×stock 面板}。

    Args:
        panel_dir: factor_panels 目录
        columns: 需要加载的列（None = 加载全部存在的列）
    """
    files = sorted(panel_dir.glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"未找到截面数据: {panel_dir}（先运行 fetch_factor_data.py）")

    frames: dict[str, pd.DataFrame] = {}
    for f in files:
        df = pd.read_parquet(f)
        if "ts_code" in df.columns:
            df = df.set_index("ts_code")
        frames[f.stem] = df

    dates = sorted(frames.keys())
    all_codes = sorted(set().union(*[set(frames[d].index) for d in dates]))
    cols = columns or [c for c in PANEL_COLUMNS if any(c in frames[d].columns for d in dates)]

    panels: dict[str, pd.DataFrame] = {}
    for col in cols:
        m = pd.DataFrame(index=pd.DatetimeIndex(pd.to_datetime(dates), name="date"),
                         columns=all_codes, dtype=float)
        for d in dates:
            s = frames[d].get(col)
            if s is not None:
                m.loc[pd.Timestamp(d), s.index] = s
        panels[col] = m
    return panels


def load_universe(stock_basic_path: Path) -> pd.DataFrame:
    """股票池: 当前上市 + 行业映射 + ST 标记（index=ts_code）。"""
    sb = pd.read_parquet(stock_basic_path)
    sb["is_st"] = sb["name"].astype(str).str.contains("ST|退", na=False)
    return sb.set_index("ts_code")
