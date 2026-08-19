"""数据源抽象：所有数据源实现同一接口，回测引擎不关心数据从哪来。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import pandas as pd


@dataclass
class Bar:
    """单日行情（规范字段）。"""

    date: pd.Timestamp
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float | None = None


class DataFeed(ABC):
    """行情数据源接口。"""

    @abstractmethod
    def load(
        self,
        symbol: str,
        start: str,
        end: str,
        adjust: str = "hfq",
    ) -> pd.DataFrame:
        """加载日线行情，返回规范化 DataFrame（date 为 index，含 open/high/low/close/volume/amount）。"""
        raise NotImplementedError
