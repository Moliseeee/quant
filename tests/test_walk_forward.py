"""walk-forward 样本外验证测试。"""

import numpy as np
import pandas as pd
import pytest

from quant.backtest.engine import BacktestEngine
from quant.config import Config
from quant.research.walk_forward import walk_forward
from quant.strategies import SMAStrategy


def make_df(n: int = 260, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2023-01-01", periods=n)
    close = 10 + 0.02 * np.arange(n) + rng.normal(0, 0.1, n)
    close = np.maximum(close, 1.0)
    return pd.DataFrame({
        "open": close * 0.99, "high": close * 1.02,
        "low": close * 0.98, "close": close, "volume": 1e6,
    }, index=idx)


def test_walk_forward_runs():
    df = make_df()
    engine = BacktestEngine(Config())
    result = walk_forward(
        df,
        strategy_factory=lambda **p: SMAStrategy(**p),
        engine=engine,
        n_windows=4,
        train_ratio=0.6,
        param_grid={"fast": [3, 5], "slow": [10, 20]},
        verbose=False,
    )
    assert "out_of_sample_equity" in result
    assert "oas_metrics" in result
    assert len(result["windows"]) == 4
    assert result["oas_metrics"]["total_return"] is not None
    # 样本外净值从 1 开始
    assert result["out_of_sample_equity"].iloc[0] == pytest.approx(1.0)
    # 每窗口都选出了参数
    assert all(w["best_params"] is not None for w in result["windows"])


def test_walk_forward_too_short():
    df = make_df(n=30)
    engine = BacktestEngine(Config())
    with pytest.raises(ValueError):
        walk_forward(df, lambda: SMAStrategy(), engine, n_windows=5)
