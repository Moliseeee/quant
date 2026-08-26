"""情绪因子构造：融资余额变化率 + 龙虎榜上榜次数（取反，越大越好）。

数据源: data/cache/sentiment_panels/<date>.parquet（akshare 两融 + 龙虎榜，T+1 对齐）
因子:
- neg_margin_chg_4w: -(融资余额 / 4周前 - 1)——融资减仓/平稳 = 好（散户杠杆反向指标）
- neg_lhb_count_4w: -4周龙虎榜上榜次数——少上榜 = 好（题材炒作反向指标）

方向约定（越大越好，供 composite_score 直接使用，无需 FACTOR_BUILDERS 变换）。
"""

from __future__ import annotations

import pandas as pd
from pathlib import Path

PANEL_COLUMNS = ["margin_balance", "lhb_net", "lhb_count"]


def load_sentiment_panels(sentiment_dir: Path) -> dict[str, pd.DataFrame]:
    """读 sentiment_panels 为 date×stock 宽表（每因子一个面板）。"""
    dates = sorted(p.name.replace(".parquet", "") for p in sentiment_dir.glob("*.parquet"))
    if not dates:
        raise FileNotFoundError(f"无情绪截面: {sentiment_dir}")
    panels: dict[str, pd.DataFrame] = {}
    for col in PANEL_COLUMNS:
        m = {pd.Timestamp(d): pd.read_parquet(sentiment_dir / f"{d}.parquet").set_index("ts_code")[col]
             for d in dates}
        panels[col] = pd.concat(m, axis=1).T
        panels[col].index.name = "date"
    return panels


def build_emotion_factors(sentiment_dir: Path) -> dict[str, pd.DataFrame]:
    """构造情绪因子面板（越大越好方向）。

    Returns:
        {"neg_margin_chg_4w": date×stock, "neg_lhb_count_4w": date×stock}
    """
    p = load_sentiment_panels(sentiment_dir)

    margin_chg_4w = p["margin_balance"] / p["margin_balance"].shift(4) - 1
    # 未上榜股票（NaN）= 中性 0（不参与"上榜次数"信号）
    lhb_count_4w = p["lhb_count"].fillna(0.0).rolling(4, min_periods=2).sum()

    return {
        "neg_margin_chg_4w": -margin_chg_4w,
        "neg_lhb_count_4w": -lhb_count_4w,
    }
