"""组合回测引擎测试：再平衡执行、无前视、整手、成本、清仓。"""

import numpy as np
import pandas as pd
import pytest

from quant.config import Config
from quant.portfolio import PortfolioEngine


def make_data(n: int = 8):
    """两标的合成行情 + 两期权重（T0 建仓、T3 调仓）。"""
    dates = pd.bdate_range("2024-01-01", periods=n)
    close = pd.DataFrame({
        "A": 10 + 0.5 * np.arange(n),
        "B": 20 + 0.5 * np.arange(n),
    }, index=dates)
    open_ = close * 0.99  # 次日开盘略低于前收（简化）
    weights = pd.DataFrame(np.nan, index=dates, columns=["A", "B"])
    weights.iloc[0] = [0.5, 0.5]   # 建仓：等权
    weights.iloc[3] = [0.3, 0.7]   # 调仓：A 降 B 升
    return close, open_, weights


@pytest.fixture
def engine():
    cfg = Config()
    cfg.backtest.initial_capital = 20_000.0
    return PortfolioEngine(cfg)


class TestRebalance:
    def test_initial_buy_next_open(self, engine):
        """T0 收盘决定权重 → T1 开盘才成交（无前视）。"""
        close, open_, weights = make_data()
        r = engine.run(close, open_, weights)
        buys = [t for t in r.trades if t.action == "BUY" and t.date == close.index[1]]
        assert len(buys) == 2  # T1 建仓买入 A、B（T4 的调仓 BUY 不算）
        assert all(t.date == close.index[1] for t in buys)  # T1 执行
        assert all(t.shares % 100 == 0 for t in buys)       # 整手
        # 等权 0.5 → 两标的目标市值 ≈ 20000×0.95×0.5 = 9500
        assert all(3000 < t.gross_amount < 13000 for t in buys)
        # 权重比: B 单价是 A 两倍，B 股数应约为 A 一半
        a = [t for t in buys if t.symbol == "A"][0]
        b = [t for t in buys if t.symbol == "B"][0]
        assert b.shares < a.shares

    def test_rebalance_at_next_open(self, engine):
        """T3 调仓 → T4 执行，方向正确（A 减仓、B 加仓）。"""
        close, open_, weights = make_data()
        r = engine.run(close, open_, weights)
        t4 = [t for t in r.trades if t.date == close.index[4]]
        assert len(t4) >= 2
        a_trades = [t for t in t4 if t.symbol == "A"]
        b_trades = [t for t in t4 if t.symbol == "B"]
        assert a_trades[0].action == "SELL"   # A 权重 0.5→0.3 减仓
        assert b_trades[0].action == "BUY"    # B 权重 0.5→0.7 加仓

    def test_no_trade_on_non_rebalance_days(self, engine):
        close, open_, weights = make_data()
        r = engine.run(close, open_, weights)
        dates = [t.date for t in r.trades]
        # 交易只发生在 T1 和 T4（执行日），T0/T2/T3 无交易
        assert close.index[1] in dates and close.index[4] in dates
        assert close.index[0] not in dates
        assert close.index[2] not in dates


class TestLiquidation:
    def test_zero_weight_liquidates(self, engine):
        """权重归零的标的应全部卖出。"""
        close, open_, weights = make_data()
        weights.iloc[5] = [0.0, 1.0]  # T5 调仓：清仓 A，全仓 B
        r = engine.run(close, open_, weights)
        t6 = [t for t in r.trades if t.date == close.index[6]]
        a_sell = [t for t in t6 if t.symbol == "A"]
        assert a_sell and a_sell[0].action == "SELL"
        # A 清仓后 holdings 为 0
        assert r.holdings.loc[close.index[6], "A"] == 0


class TestCostsAndEquity:
    def test_costs_applied(self, engine):
        close, open_, weights = make_data()
        r = engine.run(close, open_, weights)
        for t in r.trades:
            assert t.cost.total > 0  # 每笔都有佣金/滑点

    def test_equity_starts_at_capital(self, engine):
        close, open_, weights = make_data()
        r = engine.run(close, open_, weights)
        assert r.equity.iloc[0] == pytest.approx(20_000.0)

    def test_metrics_present(self, engine):
        close, open_, weights = make_data()
        r = engine.run(close, open_, weights)
        for key in ["total_return", "sharpe", "max_drawdown", "win_rate"]:
            assert key in r.metrics
