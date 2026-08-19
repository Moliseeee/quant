"""截断不变量测试（Kimi 审查 Q4 建议，第 39 个测试）。

核心不变量: 把输入序列在 T 日截断，holding/equity 的 [:T+1] 段必须与全长回测完全一致。
任何前视偏差（决策用到了 T 日之后的信息）都会破坏这个不变量。
"""

import numpy as np
import pandas as pd
import pytest

from quant.backtest.engine import BacktestEngine
from quant.config import Config


def make_df(n: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2024-01-01", periods=n)
    close = 10 + 0.01 * np.arange(n) + rng.normal(0, 0.1, n)
    close = np.maximum(close, 1.0)
    return pd.DataFrame({
        "open": close * 0.99, "high": close * 1.02,
        "low": close * 0.98, "close": close, "volume": 1e6,
    }, index=idx)


def make_signal(df: pd.DataFrame, seed: int) -> pd.Series:
    rng = np.random.default_rng(seed)
    return pd.Series(rng.integers(0, 2, len(df)).astype(float), index=df.index)


def _assert_invariant(full: pd.DataFrame, sub: pd.DataFrame, T: int) -> None:
    """截断到 T 日（sub 含 0..T-1 共 T 行），前 T 个元素的 holding/equity 必须一致。

    即: 任何未来数据（T 日之后）都不得影响 [0, T) 区间的任何决策与净值。
    """
    pd.testing.assert_series_equal(
        full["holding"].iloc[:T], sub["holding"].iloc[:T],
        check_names=False,
    )
    pd.testing.assert_series_equal(
        full["equity"].iloc[:T], sub["equity"].iloc[:T],
        check_names=False,
    )


def test_truncation_invariance_no_risk():
    df = make_df(90, seed=3)
    sig = make_signal(df, seed=7)
    full = BacktestEngine(Config()).run(df, sig).df
    for T in [20, 35, 55, 75]:
        sub = BacktestEngine(Config()).run(df.iloc[:T], sig.iloc[:T]).df
        _assert_invariant(full, sub, T)


def test_truncation_invariance_full_risk():
    """全风控开启（止损/止盈/熔断/仓位）下不变量依然成立。"""
    df = make_df(120, seed=11)
    sig = make_signal(df, seed=13)
    cfg = Config()
    cfg.risk.stop_loss_pct = 0.08
    cfg.risk.trailing_stop_pct = 0.12
    cfg.risk.daily_loss_limit = 0.03
    cfg.risk.drawdown_limit = 0.15
    cfg.risk.max_position_pct = 0.8
    full = BacktestEngine(cfg).run(df, sig).df
    for T in [30, 45, 65, 90, 105]:
        sub = BacktestEngine(cfg).run(df.iloc[:T], sig.iloc[:T]).df
        _assert_invariant(full, sub, T)
