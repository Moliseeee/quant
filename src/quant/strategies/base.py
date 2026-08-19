"""策略接口：所有策略返回 0/1 目标持仓信号（T 日收盘产生，引擎负责 T+1 执行）。"""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class Strategy(ABC):
    """策略基类。

    generate_signal 返回与 df 索引对齐的 0/1 Series:
        - 1 = 目标持仓（次日按引擎配置成交）
        - 0 = 目标空仓
    实现时严禁修改传入的 df（多策略共享数据时的副作用污染）。
    """

    name: str = "base"
    params: dict = {}

    @abstractmethod
    def generate_signal(self, df: pd.DataFrame) -> pd.Series:
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"<Strategy {self.name} params={self.params}>"
