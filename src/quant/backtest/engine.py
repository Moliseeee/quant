"""向量化回测引擎（A股，无前视偏差）。

时序模型（关键设计，消除前视偏差）:
    T 日收盘:  策略根据 <=T 的数据产生信号 signal[T]
    T+1 日:    按 execution 模式成交（默认 next_open = 次日开盘价）
    T+1 收盘:  用 close 计市值 → equity

约束建模:
    - 涨停（exec >= limit_up）→ 买入被拒，持仓保持，次日继续尝试
    - 跌停（exec <= limit_down）→ 卖出被拒
    - 停牌（volume == 0）→ 买卖都被拒
    - 100 股整手买入；现金不足一手则不买
    - 卖出可零股（A股规则）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..config import Config
from .costs import CostModel, TradeCost
from .metrics import compute_metrics
from ..data.quality import compute_limit_prices

logger = logging.getLogger(__name__)


@dataclass
class Trade:
    """一笔已执行的交易。"""

    date: pd.Timestamp
    action: str          # "BUY" / "SELL"
    price: float         # 成交价（含滑点后）
    shares: int
    gross_amount: float  # 成交金额（不含费用）
    cost: TradeCost
    net_amount: float    # 实际资金流（买入为负，卖出为正）
    pnl: float | None = None  # 平仓盈亏（SELL 时配对计算）

    def to_dict(self) -> dict:
        d = {
            "date": self.date.strftime("%Y-%m-%d"),
            "action": self.action,
            "price": round(self.price, 3),
            "shares": self.shares,
            "gross": round(self.gross_amount, 2),
            "net": round(self.net_amount, 2),
        }
        d.update(self.cost.as_dict())
        if self.pnl is not None:
            d["pnl"] = round(self.pnl, 2)
        return d


@dataclass
class BacktestResult:
    """回测结果：净值曲线、交易明细、绩效指标。"""

    df: pd.DataFrame
    trades: list[Trade]
    metrics: dict
    symbol: str

    def trades_to_frame(self) -> pd.DataFrame:
        return pd.DataFrame([t.to_dict() for t in self.trades])


class BacktestEngine:
    """A股单标的回测引擎（0/1 全仓模型，可扩展为权重模型）。"""

    def __init__(self, config: Config):
        self.config = config
        self.costs = CostModel(config.costs)

    # ------------------------------------------------------------------
    def _effective_position(
        self, df: pd.DataFrame, signal: pd.Series
    ) -> pd.Series:
        """计算实际持仓序列：T+1 生效 + 涨跌停/停牌约束迭代修正。"""
        bt = self.config.backtest
        # T+1 生效：信号 shift 1 天
        holding = signal.astype(float).shift(1).fillna(0.0)

        if not bt.respect_price_limit:
            return holding.clip(0, 1)

        limit = compute_limit_prices(df, bt.limit_pct)
        exec_price = df["open"] if bt.execution == "next_open" else df["close"]
        suspended = df["volume"].fillna(0) <= 0

        blocked_buy = (exec_price >= limit["limit_up"]) | suspended
        blocked_sell = (exec_price <= limit["limit_down"]) | suspended

        # 迭代修正：受阻交易不改变持仓，后续交易日继续尝试
        for _ in range(20):  # 极端连板最多 20 个交易日，必收敛
            delta = holding.diff().fillna(holding.iloc[0])
            buy_blocked = (delta > 0) & blocked_buy
            sell_blocked = (delta < 0) & blocked_sell
            if not buy_blocked.any() and not sell_blocked.any():
                break
            prev = holding.shift(1).fillna(0.0)
            holding[buy_blocked | sell_blocked] = prev[buy_blocked | sell_blocked]
        return holding.clip(0, 1)

    # ------------------------------------------------------------------
    def run(
        self,
        df: pd.DataFrame,
        signal: pd.Series,
        symbol: str = "",
        benchmark: pd.Series | None = None,
    ) -> BacktestResult:
        """运行回测。

        Args:
            df: 规范化日线（date index, open/high/low/close/volume）
            signal: 0/1 持仓信号，索引与 df 对齐（T 日收盘产生）
            symbol: 标的代码（仅用于展示）
            benchmark: 基准净值序列（索引与 df 对齐），用于 alpha/beta/IR
        """
        bt = self.config.backtest
        signal = signal.reindex(df.index).fillna(0.0).astype(float).clip(0, 1)

        holding = self._effective_position(df, signal)
        exec_price = df["open"] if bt.execution == "next_open" else df["close"]

        # ---- 资金簿记（循环仅做簿记，决策已向量化完成，无前视） ----
        cash = bt.initial_capital
        shares = 0
        open_trade: Trade | None = None
        trades: list[Trade] = []
        equity_vals = np.zeros(len(df))
        lot = bt.lot_size

        for i, (date, row) in enumerate(df.iterrows()):
            target = holding.iloc[i]
            price = float(exec_price.iloc[i])
            close = float(row["close"])

            if target > 0.5 and shares == 0:
                # 买入：现金约束 + 整手约束
                # 实际成本：佣金率 + 过户费 + 滑点
                rate_total = (
                    self.config.costs.commission_rate
                    + self.config.costs.transfer_fee
                )
                max_shares = int(
                    cash * (1 - bt.min_cash_reserve) / (price * (1 + rate_total) + self.config.costs.slippage)
                )
                buy_shares = (max_shares // lot) * lot
                if buy_shares >= lot:
                    cost = self.costs.buy_cost(price, buy_shares)
                    cash -= price * buy_shares + cost.total
                    shares = buy_shares
                    open_trade = Trade(
                        date=date, action="BUY", price=price,
                        shares=buy_shares, gross_amount=price * buy_shares,
                        cost=cost, net_amount=-(price * buy_shares + cost.total),
                    )
                    trades.append(open_trade)

            elif target < 0.5 and shares > 0:
                # 卖出：全部持仓（A股卖出可零股）
                cost = self.costs.sell_cost(price, shares)
                proceeds = price * shares - cost.total
                cash += proceeds
                sell = Trade(
                    date=date, action="SELL", price=price, shares=shares,
                    gross_amount=price * shares, cost=cost,
                    net_amount=proceeds,
                )
                if open_trade is not None:
                    sell.pnl = sell.net_amount + open_trade.net_amount
                trades.append(sell)
                open_trade = None
                shares = 0

            equity_vals[i] = cash + shares * close

        equity = pd.Series(equity_vals, index=df.index, name="equity")
        result_df = df.copy()
        result_df["signal"] = signal
        result_df["holding"] = holding
        result_df["equity"] = equity
        result_df["returns"] = equity.pct_change().fillna(0)

        # 未平仓标记（最后仍持仓则没有 SELL，pnl 无法配对，属正常）
        metrics = compute_metrics(equity, trades, benchmark)
        metrics["final_position"] = shares
        metrics["symbol"] = symbol or ""
        return BacktestResult(df=result_df, trades=trades, metrics=metrics, symbol=symbol)
