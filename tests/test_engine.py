"""回测引擎测试：前视偏差、约束、配对、成本。全部用合成数据，无需 token。"""

import numpy as np
import pandas as pd
import pytest

from quant.backtest.costs import CostModel
from quant.backtest.engine import BacktestEngine
from quant.config import Config


def make_df(n: int = 60, price0: float = 10.0, step: float = 0.1,
            volume: float = 1e6, seed: int = 42) -> pd.DataFrame:
    """合成日线：平稳上涨 + 少量噪声。"""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2024-01-01", periods=n)
    close = price0 + step * np.arange(n) + rng.normal(0, 0.05, n)
    close = np.maximum(close, 1.0)
    open_ = close - rng.normal(0, 0.02, n)
    high = np.maximum(open_, close) + 0.05
    low = np.minimum(open_, close) - 0.05
    return pd.DataFrame({
        "open": open_, "high": high, "low": low, "close": close,
        "volume": volume,
    }, index=idx)


def make_signal(df: pd.DataFrame, hold_from: int = 10, hold_to: int = 50) -> pd.Series:
    sig = pd.Series(0.0, index=df.index)
    sig.iloc[hold_from:hold_to] = 1.0
    return sig


@pytest.fixture
def engine():
    return BacktestEngine(Config())


class TestExecutionTiming:
    """核心：无前视偏差 —— 信号 T 日产生，T+1 日才成交。"""

    def test_buy_happens_next_day(self, engine):
        df = make_df()
        sig = make_signal(df, hold_from=10, hold_to=50)
        result = engine.run(df, sig)
        buys = [t for t in result.trades if t.action == "BUY"]
        assert len(buys) == 1
        # 信号第 10 天为 1，成交应在第 11 天
        assert buys[0].date == df.index[11]
        assert buys[0].shares % 100 == 0  # 整手

    def test_sell_happens_next_day(self, engine):
        df = make_df()
        sig = make_signal(df, hold_from=10, hold_to=50)
        result = engine.run(df, sig)
        sells = [t for t in result.trades if t.action == "SELL"]
        assert len(sells) == 1
        # 信号第 50 天为 0（50 天时 target 变 0），第 51 天卖出
        assert sells[0].date == df.index[51]

    def test_no_signal_no_trade(self, engine):
        df = make_df()
        sig = pd.Series(0.0, index=df.index)
        result = engine.run(df, sig)
        assert result.trades == []
        assert result.metrics["total_return"] == pytest.approx(0.0)


class TestPriceLimitConstraints:
    def test_limit_up_blocks_buy(self):
        """一字涨停日买不进，次日继续尝试买入。

        时序: signal 第 14 天置 1 → T+1 第 15 天开始执行买入，
        第 15 天恰为一字涨停 → 买不进 → 推迟到第 16 天。
        """
        df = make_df(n=30, step=0.05)
        # 在第 15 天制造一字涨停：open == limit_up == 前收*1.1
        prev_close = df["close"].iloc[14]
        lim_up = round(prev_close * 1.1, 2)
        df.loc[df.index[15], ["open", "high", "low", "close"]] = lim_up
        sig = make_signal(df, hold_from=14, hold_to=28)
        engine = BacktestEngine(Config())
        result = engine.run(df, sig)
        buys = [t for t in result.trades if t.action == "BUY"]
        assert len(buys) == 1
        # 第 15 天买不进，应推迟到第 16 天
        assert buys[0].date == df.index[16]

    def test_limit_down_blocks_sell(self):
        """一字跌停日卖不出，次日继续尝试卖出。

        时序: signal 第 26 天置 0 → T+1 第 27 天开始执行卖出，
        第 27 天恰为一字跌停 → 卖不出 → 推迟到第 28 天。
        """
        df = make_df(n=40, step=0.05)
        prev_close = df["close"].iloc[26]
        lim_down = round(prev_close * 0.9, 2)
        df.loc[df.index[27], ["open", "high", "low", "close"]] = lim_down
        sig = make_signal(df, hold_from=10, hold_to=26)
        engine = BacktestEngine(Config())
        result = engine.run(df, sig)
        sells = [t for t in result.trades if t.action == "SELL"]
        assert len(sells) == 1
        assert sells[0].date == df.index[28]  # 27 卖不出 -> 28 卖出


class TestSuspension:
    def test_suspended_day_no_trade(self, engine):
        df = make_df(n=40)
        df.loc[df.index[20], "volume"] = 0.0  # 停牌
        sig = make_signal(df, hold_from=19, hold_to=35)
        result = engine.run(df, sig)
        buys = [t for t in result.trades if t.action == "BUY"]
        assert buys[0].date == df.index[21]  # 20 停牌 -> 21 成交


class TestTradeMatching:
    """胜率配对正确性：多轮买卖不能错位。"""

    def test_pnl_matching_multiple_rounds(self, engine):
        df = make_df(n=100, step=0.2)
        sig = pd.Series(0.0, index=df.index)
        sig.iloc[10:30] = 1.0
        sig.iloc[50:80] = 1.0
        result = engine.run(df, sig)
        sells = [t for t in result.trades if t.action == "SELL"]
        assert len(sells) == 2
        # 两轮盈亏都应 > 0（上涨市）
        assert all(t.pnl is not None and t.pnl > 0 for t in sells)


class TestCostModel:
    def test_commission_minimum(self):
        cfg = Config()
        cm = CostModel(cfg.costs)
        # 小额交易佣金低于 5 元 -> 按最低 5 元收
        cost = cm.buy_cost(price=5.0, shares=100)
        assert cost.commission == pytest.approx(5.0)

    def test_stamp_tax_only_on_sell(self):
        cfg = Config()
        cm = CostModel(cfg.costs)
        buy = cm.buy_cost(price=10.0, shares=1000)
        sell = cm.sell_cost(price=10.0, shares=1000)
        assert buy.stamp_tax == 0.0
        assert sell.stamp_tax == pytest.approx(1000 * 10.0 * 0.0005)

    def test_transfer_fee_both_sides(self):
        cfg = Config()
        cm = CostModel(cfg.costs)
        buy = cm.buy_cost(price=10.0, shares=1000)
        sell = cm.sell_cost(price=10.0, shares=1000)
        assert buy.transfer_fee == pytest.approx(1000 * 10.0 * 0.00001)
        assert sell.transfer_fee == buy.transfer_fee
