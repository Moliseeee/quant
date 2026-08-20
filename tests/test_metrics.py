"""绩效指标数值正确性测试（合成数据 + 手算验证）。"""

import numpy as np
import pandas as pd
import pytest

from quant.backtest.metrics import (
    annualized_return,
    annualized_volatility,
    calmar_ratio,
    compute_metrics,
    infer_periods_per_year,
    max_drawdown,
    max_drawdown_duration,
    sharpe_ratio,
    sortino_ratio,
    win_rate,
    profit_factor,
)


def make_equity(values: list[float]) -> pd.Series:
    idx = pd.date_range("2024-01-01", periods=len(values), freq="B")
    return pd.Series(values, index=idx, name="equity")


class TestMaxDrawdown:
    def test_simple_peak_to_trough(self):
        eq = make_equity([100, 120, 110, 130, 90, 100])
        # 最高点 130 -> 最低 90 => 回撤 30.77%（正数表示幅度）
        assert max_drawdown(eq) == pytest.approx(1 - 90 / 130, abs=1e-9) == pytest.approx(0.3077, abs=1e-3)

    def test_monotonic_up_no_drawdown(self):
        eq = make_equity([100, 101, 102, 103])
        assert max_drawdown(eq) == 0.0

    def test_monotonic_down(self):
        eq = make_equity([100, 90, 80])
        assert max_drawdown(eq) == pytest.approx(0.2)


class TestDrawdownDuration:
    def test_single_underwater_period(self):
        eq = make_equity([100, 110, 105, 100, 95, 112])
        # 从 110 跌到 95 再创新高，水下 3 天
        assert max_drawdown_duration(eq) == 3

    def test_no_drawdown(self):
        assert max_drawdown_duration(make_equity([1, 2, 3])) == 0


class TestSharpe:
    def test_zero_vol(self):
        eq = make_equity([100] * 10)
        assert sharpe_ratio(eq) == 0.0

    def test_constant_growth(self):
        # 每日 +1%，无波动 -> 年化收益 = 1.01^252 - 1，波动率≈0
        eq = pd.Series(100 * 1.01 ** np.arange(252))
        assert sharpe_ratio(eq) == 0.0  # 分母为 0 -> 0


class TestPeriodsPerYear:
    """P6 年化口径回归（Kimi 审查：周频 equity 曾走日频 252，年化放大 ~4.85×）。"""

    def test_infer_daily(self):
        idx = pd.bdate_range("2024-01-01", periods=10)
        assert infer_periods_per_year(idx) == 252

    def test_infer_weekly(self):
        idx = pd.date_range("2024-01-01", periods=10, freq="W-FRI")
        assert infer_periods_per_year(idx) == 52

    def test_infer_monthly(self):
        idx = pd.date_range("2024-01-01", periods=10, freq="ME")
        assert infer_periods_per_year(idx) == 12

    def test_weekly_annualized_return(self):
        """182 行周频 equity（3.5 年）: 年化 = (1+total)^(52/182) - 1。"""
        idx = pd.date_range("2023-01-06", periods=182, freq="W-FRI")
        equity = pd.Series(100 * 1.001 ** np.arange(182), index=idx)
        total = equity.iloc[-1] / equity.iloc[0] - 1
        expected = (1 + total) ** (52 / 182) - 1
        assert annualized_return(equity, 52) == pytest.approx(expected)

    def test_compute_metrics_infers_weekly(self):
        """compute_metrics 对周频数据自动推断 ppy=52（不再默认 252）。"""
        idx = pd.date_range("2023-01-06", periods=52, freq="W-FRI")
        equity = pd.Series(100 * 1.002 ** np.arange(52), index=idx)
        m = compute_metrics(equity)
        assert m["periods_per_year"] == 52
        total = equity.iloc[-1] / equity.iloc[0] - 1
        assert m["annual_return"] == pytest.approx(total, abs=1e-5)  # round(6) 容差

    def test_weekly_sharpe_lower_than_daily_claim(self):
        """同一净值路径，周频夏普应显著低于日频口径（P6 核心断言）。"""
        idx_w = pd.date_range("2023-01-06", periods=182, freq="W-FRI")
        equity = pd.Series(np.cumprod(1 + np.random.default_rng(0).normal(0.002, 0.03, 182)),
                           index=idx_w)
        sharpe_wrong = sharpe_ratio(equity, periods_per_year=252)  # 旧口径（bug）
        sharpe_right = sharpe_ratio(equity, periods_per_year=52)   # 正确口径
        assert sharpe_right < sharpe_wrong


class TestWinRateAndProfitFactor:
    def _trade(self, action, pnl=None):
        from quant.backtest.engine import Trade
        from quant.backtest.costs import TradeCost
        cost = TradeCost(0, 0, 0, 0)
        return Trade(pd.Timestamp("2024-01-01"), action, 10.0, 100, 1000.0, cost, 1000.0, pnl)

    def test_win_rate(self):
        trades = [self._trade("BUY"), self._trade("SELL", pnl=100), self._trade("BUY"), self._trade("SELL", pnl=-50), self._trade("SELL", pnl=30)]
        assert win_rate(trades) == pytest.approx(2 / 3)

    def test_profit_factor(self):
        trades = [self._trade("SELL", pnl=100), self._trade("SELL", pnl=-40), self._trade("SELL", pnl=60)]
        assert profit_factor(trades) == pytest.approx(160 / 40)
