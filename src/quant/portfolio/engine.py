"""组合回测引擎：多标的、周频再平衡、权重分配、完整 A股成本。

时序模型（无前视）:
    调仓日 T 收盘:  按当日收盘总资产 × 目标权重 = 各标的目标市值
    T+1 日开盘:     执行调仓（开盘价成交，先卖后买）
    中间日:         持仓不动，仅按收盘价计值

输入约定:
    close:        date × stock 收盘价（计值 + 调仓日算目标股数）
    open_prices:  date × stock 开盘价（调仓执行价）
    weights:      date × stock 目标权重（仅调仓日有值，其余 NaN；权重 0/NaN = 清仓）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..backtest.costs import CostModel, TradeCost
from ..backtest.engine import Trade
from ..backtest.metrics import compute_metrics
from ..config import Config

logger = logging.getLogger(__name__)


@dataclass
class PortfolioResult:
    """组合回测结果。"""

    equity: pd.Series
    holdings: pd.DataFrame
    trades: list[Trade]
    metrics: dict

    def trades_to_frame(self) -> pd.DataFrame:
        return pd.DataFrame([t.to_dict() for t in self.trades])


class PortfolioEngine:
    """多标的组合回测引擎。"""

    def __init__(self, config: Config):
        self.config = config
        self.costs = CostModel(config.costs)

    def run(
        self,
        close: pd.DataFrame,
        open_prices: pd.DataFrame,
        weights: pd.DataFrame,
        initial_capital: float | None = None,
        cash_buffer: float = 0.05,
    ) -> PortfolioResult:
        """运行组合回测。

        Args:
            close: date × stock 收盘价
            open_prices: date × stock 开盘价（与 close 同索引）
            weights: date × stock 目标权重（调仓日有值）
            initial_capital: 初始资金（默认取 config）
            cash_buffer: 预留现金比例（0-1），防调仓时资金不足
        """
        bt = self.config.backtest
        capital = initial_capital or bt.initial_capital
        lot = bt.lot_size
        rate_total = (
            self.config.costs.commission_rate + self.config.costs.transfer_fee
        )
        slip = self.config.costs.slippage

        # 对齐输入
        close = close.sort_index()
        open_prices = open_prices.reindex(close.index)
        weights = weights.reindex(close.index).fillna(0.0)

        shares: dict[str, int] = {}   # stock -> 股数
        cash = capital
        pending: dict[str, int] | None = None  # 昨日收盘决定的明日目标股数

        equity_vals = np.zeros(len(close))
        holdings_rows: list[dict] = []
        trades: list[Trade] = []
        all_stocks = list(close.columns)

        for i, date in enumerate(close.index):
            # ========== 1. 执行昨日调仓决定（今日开盘价，先卖后买） ==========
            if pending is not None:
                # 卖出（含权重归零的标的）
                for stock, target in pending.items():
                    cur = shares.get(stock, 0)
                    if cur > target:
                        sell_shares = cur - target
                        price = float(open_prices.loc[date, stock])
                        cost = self.costs.sell_cost(price, sell_shares)
                        proceeds = price * sell_shares - cost.total
                        cash += proceeds
                        shares[stock] = target
                        trades.append(Trade(
                            date=date, action="SELL", price=price,
                            shares=sell_shares, gross_amount=price * sell_shares,
                            cost=cost, net_amount=proceeds, symbol=stock,
                        ))
                # 买入
                for stock, target in pending.items():
                    cur = shares.get(stock, 0)
                    if target > cur:
                        buy_shares = target - cur
                        price = float(open_prices.loc[date, stock])
                        cost = self.costs.buy_cost(price, buy_shares)
                        need = price * buy_shares + cost.total
                        if cash >= need:
                            cash -= need
                            shares[stock] = target
                            trades.append(Trade(
                                date=date, action="BUY", price=price,
                                shares=buy_shares, gross_amount=price * buy_shares,
                                cost=cost, net_amount=-need, symbol=stock,
                            ))
                        else:
                            logger.warning("%s 买入 %s 资金不足(需 %.0f 有 %.0f)，跳过",
                                           date.date(), stock, need, cash)
                pending = None

            # ========== 2. 收盘计值 ==========
            eq = cash + sum(shares.get(s, 0) * float(close.loc[date, s]) for s in shares)
            equity_vals[i] = eq
            holdings_rows.append({s: shares.get(s, 0) for s in all_stocks})

            # ========== 3. 收盘后：调仓日 → 计算明日目标股数 ==========
            w_row = weights.loc[date]
            if w_row.notna().any() and float(w_row.sum()) > 0:
                budget = eq * (1 - cash_buffer)
                pending = {}
                for stock in all_stocks:
                    w = float(w_row.get(stock, 0.0) or 0.0)
                    if w <= 0:
                        pending[stock] = 0  # 清仓
                        continue
                    px = float(close.loc[date, stock])
                    if px <= 0:
                        pending[stock] = 0
                        continue
                    target_value = budget * w
                    raw = target_value / (px * (1 + rate_total) + slip)
                    pending[stock] = (int(raw) // lot) * lot

        equity = pd.Series(equity_vals, index=close.index, name="equity")
        holdings = pd.DataFrame(holdings_rows, index=close.index, columns=all_stocks)
        metrics = compute_metrics(equity, trades)
        metrics["final_position_count"] = sum(1 for v in shares.values() if v > 0)
        return PortfolioResult(equity=equity, holdings=holdings, trades=trades, metrics=metrics)
