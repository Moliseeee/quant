"""本地 CSV 数据源（兼容 v1/ifind_weekly 导出的周频截面数据以外的日线 CSV）。"""

from __future__ import annotations

import pandas as pd

from .base import DataFeed
from .quality import normalize_columns


class CSVFeed(DataFeed):
    """从本地 CSV 读日线。

    CSV 需包含列（中英文均可，自动识别）:
    date/trade_date 或日期、open、high、low、close、volume/vol
    """

    def __init__(self, path: str):
        self._path = path

    def load(self, symbol: str, start: str, end: str, adjust: str = "hfq") -> pd.DataFrame:
        df = pd.read_csv(self._path)
        df = normalize_columns(df)
        df = df.loc[start:end]
        if df.empty:
            raise ValueError(f"{self._path} 在 {start}~{end} 无数据")
        return df


def get_feed(provider: str, **kwargs) -> DataFeed:
    """工厂函数：按配置创建数据源。"""
    if provider == "tushare":
        from .tushare_feed import TushareFeed

        return TushareFeed(kwargs["token"], kwargs.get("cache_dir"))
    if provider == "akshare":
        from .akshare_feed import AkShareFeed

        return AkShareFeed(kwargs.get("cache_dir"))
    if provider == "csv":
        return CSVFeed(kwargs["path"])
    raise ValueError(f"未知数据源: {provider}")
