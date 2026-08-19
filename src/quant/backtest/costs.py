"""A股交易成本模型。

买入成本 = 佣金(rate, 最低 min) + 过户费 + 滑点
卖出成本 = 佣金(rate, 最低 min) + 印花税(单边) + 过户费 + 滑点

2023-08-28 起印花税减半至 0.05%（卖出单边）。
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import CostConfig


@dataclass
class TradeCost:
    """单笔交易的成本明细。"""

    commission: float
    stamp_tax: float
    transfer_fee: float
    slippage_cost: float

    @property
    def total(self) -> float:
        return self.commission + self.stamp_tax + self.transfer_fee + self.slippage_cost

    def as_dict(self) -> dict:
        return {
            "commission": round(self.commission, 2),
            "stamp_tax": round(self.stamp_tax, 2),
            "transfer_fee": round(self.transfer_fee, 2),
            "slippage": round(self.slippage_cost, 2),
            "total": round(self.total, 2),
        }


class CostModel:
    """依据 CostConfig 计算买卖成本。"""

    def __init__(self, cfg: CostConfig):
        self.cfg = cfg

    def _commission(self, amount: float) -> float:
        fee = amount * self.cfg.commission_rate
        return max(fee, self.cfg.commission_min)

    def buy_cost(self, price: float, shares: int) -> TradeCost:
        amount = price * shares
        return TradeCost(
            commission=self._commission(amount),
            stamp_tax=0.0,
            transfer_fee=amount * self.cfg.transfer_fee,
            slippage_cost=shares * self.cfg.slippage,
        )

    def sell_cost(self, price: float, shares: int) -> TradeCost:
        amount = price * shares
        return TradeCost(
            commission=self._commission(amount),
            stamp_tax=amount * self.cfg.stamp_tax,
            transfer_fee=amount * self.cfg.transfer_fee,
            slippage_cost=shares * self.cfg.slippage,
        )
