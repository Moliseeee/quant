"""风控模块测试：止损/止盈/仓位上限/当日亏损熔断/回撤熔断。"""

import numpy as np
import pandas as pd
import pytest

from quant.backtest.engine import BacktestEngine
from quant.config import Config


def make_prices(close_list: list[float]) -> pd.DataFrame:
    """构造精确价格序列（open=close，high/low 微偏离），便于手算验证。"""
    close = np.array(close_list, dtype=float)
    idx = pd.bdate_range("2024-01-01", periods=len(close))
    return pd.DataFrame({
        "open": close.copy(),
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
        "volume": 1e6,
    }, index=idx)


def hold_signal(df: pd.DataFrame, hold_from: int = 0, hold_to: int | None = None) -> pd.Series:
    """从 hold_from 开始持有到 hold_to（None=一直持有）。"""
    sig = pd.Series(0.0, index=df.index)
    sig.iloc[hold_from:] = 1.0
    if hold_to is not None:
        sig.iloc[hold_to:] = 0.0
    return sig


def config_with(**risk_kwargs) -> Config:
    cfg = Config()
    for k, v in risk_kwargs.items():
        setattr(cfg.risk, k, v)
    return cfg


class TestStopLoss:
    def test_stop_loss_triggers_next_day(self):
        """涨后连续阴跌：收盘跌破成本-8% → 次日止损卖出。"""
        df = make_prices([10, 10.5, 11, 11.5, 11, 10, 9.5, 9, 8.5, 8])
        cfg = config_with(stop_loss_pct=0.08)
        result = BacktestEngine(cfg).run(df, hold_signal(df))
        buys = [t for t in result.trades if t.action == "BUY"]
        sells = [t for t in result.trades if t.action == "SELL"]
        assert len(buys) == 1 and len(sells) == 1
        # 买入在 index1（T+1），止损在触发次日（index6 收盘 9.5 ≤ 10.52×0.92 → index7 卖）
        assert buys[0].date == df.index[1]
        assert sells[0].date == df.index[7]
        # 止损卖出价显著低于买入价（承认亏损，而不是放任深套）
        assert sells[0].price < buys[0].price
        # 止损后不再交易（信号仍为 1 但已离场后无新买入——信号一直持有，不会重复买）
        assert len(result.trades) == 2

    def test_no_stop_loss_when_price_stays_above(self):
        df = make_prices([10, 10.5, 11, 11.5, 12, 12.5])
        cfg = config_with(stop_loss_pct=0.08)
        result = BacktestEngine(cfg).run(df, hold_signal(df))
        assert all(t.action == "BUY" for t in result.trades)  # 无卖出


class TestStopoutDeadlock:
    """Kimi 审查 P1 回归：止损触发恰逢信号 1→0 当天时，0→1 沿不得被永久错过。

    复现场景（Kimi 模糊测试 1% 分岔组）:
        信号:  1 1 1 0 1 1 1 1   (bar3 止损，恰好是信号 1→0 当天)
        buggy: [BUY@1, SELL@4]            ← 死锁：止损后再无成交
        fixed: [BUY@1, SELL@4, BUY@5]     ← 正常：bar5 按新沿重新进场
    """

    def test_reenry_after_stopout_uses_new_edge(self):
        # bar3 (index3) 收盘 9.5 ≤ 成本 10.52×0.92=9.678 → 止损触发
        df = make_prices([10, 10.5, 11, 9.5, 9, 9.5, 10, 10.5])
        sig = pd.Series(0.0, index=df.index)
        sig.iloc[:3] = 1.0   # bar0-2 持有
        sig.iloc[4:] = 1.0   # bar4 起重新想持有（0→1 沿在 bar4）
        cfg = config_with(stop_loss_pct=0.08)
        result = BacktestEngine(cfg).run(df, sig)
        actions = [(t.action, t.date) for t in result.trades]
        assert actions == [
            ("BUY", df.index[1]),
            ("SELL", df.index[4]),
            ("BUY", df.index[5]),   # 新沿后重新进场（修复前此处死锁）
        ]

    def test_no_reenry_without_new_edge(self):
        """信号持续为 1（无 0→1 沿）时，止损后不应自动买回。"""
        df = make_prices([10, 10.5, 11, 9.5, 9, 9.5, 10, 10.5])
        sig = pd.Series(1.0, index=df.index)  # 一直持有，无沿
        cfg = config_with(stop_loss_pct=0.08)
        result = BacktestEngine(cfg).run(df, sig)
        buys = [t for t in result.trades if t.action == "BUY"]
        sells = [t for t in result.trades if t.action == "SELL"]
        assert len(buys) == 1 and len(sells) == 1  # 止损后不再进场


class TestTrailingStop:
    def test_trailing_stop_locks_profit(self):
        """涨到峰值 16 后回落 10% → 止盈卖出，且卖出价 > 买入价（锁利）。"""
        df = make_prices([10, 10.5, 12, 14, 16, 14.7, 14, 13.5, 13])
        cfg = config_with(trailing_stop_pct=0.10)
        result = BacktestEngine(cfg).run(df, hold_signal(df))
        buys = [t for t in result.trades if t.action == "BUY"]
        sells = [t for t in result.trades if t.action == "SELL"]
        assert len(sells) == 1
        # 峰值 16×1.01≈16.16，止盈线 ≈14.54；index5 close=14.7 未触发，index6 close=14 触发 → index7 卖
        assert sells[0].date == df.index[7]
        assert sells[0].price > buys[0].price  # 盈利离场
        assert sells[0].pnl is not None and sells[0].pnl > 0


class TestMaxPosition:
    def test_position_cap_limits_buy_amount(self):
        """max_position_pct=0.5 → 买入金额 ≤ 可用资金一半。"""
        df = make_prices([10.0] * 10)
        cfg = config_with(max_position_pct=0.5)
        cfg.backtest.initial_capital = 10_000.0
        result = BacktestEngine(cfg).run(df, hold_signal(df))
        buys = [t for t in result.trades if t.action == "BUY"]
        assert len(buys) == 1
        # 预算 = 10000 × 0.5 = 5000
        assert buys[0].gross_amount <= 5000 * 1.05
        assert buys[0].gross_amount > 3000  # 确实买了（不是全仓 10000）


class TestDailyLossCircuitBreaker:
    def test_no_buy_day_after_crash(self):
        """暴跌日触发熔断 → 清仓后次日不允许抄底买入，隔日恢复。"""
        # 时序: index1 买入(10.5) → index3 暴跌(11→8.5, 持仓-23%) 触发熔断
        #       index4 卖出清仓(8.5) → index5 想买回(9) 被熔断拦截 → index6 恢复买入(9.5)
        df = make_prices([10, 10.5, 11, 8.5, 8.5, 9, 9.5])
        # index0-2 持有, index3 起 0（暴跌后离场）, index4 起想买回
        sig2 = hold_signal(df, hold_from=0, hold_to=3)
        sig2.iloc[4:] = 1.0
        cfg = config_with(daily_loss_limit=0.03)
        result = BacktestEngine(cfg).run(df, sig2)
        actions = [(t.date, t.action) for t in result.trades]
        # 买入(10.5) → 卖出(8.5) → [index5 被熔断拦截] → 买入(9.5)
        assert actions[0] == (df.index[1], "BUY")
        assert actions[1] == (df.index[4], "SELL")
        assert actions[2] == (df.index[6], "BUY")  # 熔断只停一天，隔日恢复
        # 中间没有 index5 的买入
        dates = [t.date for t in result.trades]
        assert df.index[5] not in dates


class TestDrawdownCircuitBreaker:
    def test_breaker_liquidates_and_stops(self):
        """累计回撤 -15% → 清仓，之后永不买入（即使信号要求持有）。"""
        df = make_prices([10, 10.5, 12, 13, 12, 11, 10, 9, 8.5])
        cfg = config_with(drawdown_limit=0.15)
        result = BacktestEngine(cfg).run(df, hold_signal(df))
        trades = result.trades
        buys = [t for t in trades if t.action == "BUY"]
        sells = [t for t in trades if t.action == "SELL"]
        # 只有一次买入和一次清仓卖出
        assert len(buys) == 1 and len(sells) == 1
        # 峰值 13（index3），回撤线 13×0.85=11.05；index5 close=11 ≤ 11.05 触发 → index6 清仓
        assert sells[0].date == df.index[6]
        # 清仓后净值不再有新交易（index6 之后无 BUY）
        assert len(trades) == 2
        # 清仓后信号仍为 1，但熔断阻止了任何新买入 → 验证 equity 不再有 BUY 段
        assert result.df["holding"].iloc[-1] == 0.0
