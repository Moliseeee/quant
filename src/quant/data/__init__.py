"""data 子包：数据源抽象 + 质量控制。"""

from .akshare_feed import AkShareFeed
from .base import DataFeed
from .csv_feed import CSVFeed, get_feed
from .quality import (
    TUSHARE_COL_MAP,
    compute_limit_prices,
    detect_suspensions,
    normalize_columns,
    run_quality_report,
)
from .tushare_feed import TushareFeed

__all__ = [
    "DataFeed",
    "CSVFeed",
    "TushareFeed",
    "AkShareFeed",
    "get_feed",
    "normalize_columns",
    "run_quality_report",
    "compute_limit_prices",
    "detect_suspensions",
    "TUSHARE_COL_MAP",
]
