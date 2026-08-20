"""面板加载测试（quant/data/panels.py）。"""

import pandas as pd
import pytest

from quant.data import load_panels, load_universe


def make_panel_files(tmp_path, n_dates: int = 3, n_stocks: int = 5):
    """写 n_dates 个截面 parquet 到 tmp_path。"""
    stocks = [f"S{i:02d}" for i in range(n_stocks)]
    dates = pd.bdate_range("2024-01-01", periods=n_dates)
    for d in dates:
        df = pd.DataFrame({
            "ts_code": stocks,
            "close": [10.0] * n_stocks,
            "turnover_rate": [2.0] * n_stocks,
            "adj_factor": [1.0] * n_stocks,
        })
        (tmp_path / f"{d.strftime('%Y%m%d')}.parquet").write_bytes(
            df.to_parquet(index=False))
    return stocks


class TestLoadPanels:
    def test_panel_shape(self, tmp_path):
        stocks = make_panel_files(tmp_path)
        panels = load_panels(tmp_path)
        assert set(panels.keys()) >= {"close", "turnover_rate", "adj_factor"}
        df = panels["close"]
        assert len(df) == 3  # 3 个截面
        assert set(df.columns) == set(stocks)
        assert isinstance(df.index, pd.DatetimeIndex)

    def test_column_filter(self, tmp_path):
        make_panel_files(tmp_path)
        panels = load_panels(tmp_path, columns=["close"])
        assert list(panels.keys()) == ["close"]

    def test_missing_dir_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_panels(tmp_path / "empty")


class TestLoadUniverse:
    def test_st_marking(self, tmp_path):
        sb = pd.DataFrame({
            "ts_code": ["A", "B", "C"],
            "name": ["平安银行", "*ST节能", "茅台"],
            "industry": ["银行", "环保", "食品饮料"],
        })
        p = tmp_path / "stock_basic.parquet"
        p.write_bytes(sb.to_parquet(index=False))
        universe = load_universe(p)
        assert bool(universe.loc["B", "is_st"]) is True  # np.True_ 需转 bool
        assert bool(universe.loc["A", "is_st"]) is False
        assert universe.index.name == "ts_code"
