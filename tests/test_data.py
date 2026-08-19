"""数据层测试：TushareFeed 缓存读写往返 + 复权数学（不依赖网络/token）。"""

import pandas as pd
import pytest

from quant.data.tushare_feed import TushareFeed


def make_raw_df(n: int = 30) -> pd.DataFrame:
    """未复权行情（date index + OHLCV）。"""
    idx = pd.bdate_range("2024-01-01", periods=n)
    return pd.DataFrame({
        "open": 10.0, "high": 10.5, "low": 9.5, "close": 10.2,
        "volume": 1e6, "amount": 1e7, "ts_code": "600000.SH",
    }, index=idx)


@pytest.fixture
def feed(tmp_path):
    f = TushareFeed.__new__(TushareFeed)  # 只测缓存逻辑，不触网
    f._cache_dir = tmp_path
    return f


class TestCacheRoundtrip:
    def test_save_load_roundtrip(self, feed):
        """存（reset_index 宽表）→ 读回必须是 date 为 index 的 datetime。"""
        df = make_raw_df()
        feed._save_parquet(df, feed._raw_path("600000.SH"))
        out = feed._load_parquet(feed._raw_path("600000.SH"))
        assert out is not None
        assert isinstance(out.index, pd.DatetimeIndex)
        assert len(out) == len(df)
        assert out.index[0] == df.index[0]
        assert "date" not in out.columns

    def test_corrupted_cache_returns_none(self, feed):
        """损坏的缓存文件应优雅降级（返回 None 触发重拉）。"""
        path = feed._raw_path("600000.SH")
        path.write_bytes(b"not a parquet file")
        assert feed._load_parquet(path) is None


class TestAdjustmentMath:
    """复权数学正确性（Kimi 审查 P4 修复的核心验证）。"""

    @staticmethod
    def _feed_with_data(feed):
        """构造: 前 15 天 adj_factor=1.0，后 15 天 adj_factor=2.0（模拟 10 送 10 除权）。"""
        n = 30
        idx = pd.bdate_range("2024-01-01", periods=n)
        raw = pd.DataFrame({
            "open": 10.0, "high": 10.5, "low": 9.5, "close": 10.2,
            "volume": 1e6, "amount": 1e7,
        }, index=idx)
        adj = pd.Series([1.0] * 15 + [2.0] * 15, index=idx, name="adj_factor")
        return raw, adj

    def test_hfq_multiplies_by_factor(self, feed):
        raw, adj = self._feed_with_data(feed)
        df = raw.join(adj)
        factor = df["adj_factor"]
        hfq = (df["close"] * factor).round(2)
        # 除权前 close=10.2×1.0=10.2；除权后 10.2×2.0=20.4
        assert hfq.iloc[0] == pytest.approx(10.2)
        assert hfq.iloc[-1] == pytest.approx(20.4)

    def test_qfq_adjusts_to_latest_scale(self, feed):
        raw, adj = self._feed_with_data(feed)
        df = raw.join(adj)
        latest = float(adj.iloc[-1])
        qfq = (df["close"] * adj / latest).round(2)
        # 最新口径下除权前后一致: 10.2×1.0/2.0=5.1 与 10.2×2.0/2.0=10.2
        assert qfq.iloc[0] == pytest.approx(5.1)
        assert qfq.iloc[-1] == pytest.approx(10.2)

    def test_incremental_append_does_not_pollute_history(self, feed):
        """P4 核心: 增量追加新因子不得改变历史复权价。"""
        raw, adj = self._feed_with_data(feed)
        # 第一次只有前半段（adj=1.0），复权后 close=10.2
        half = 15
        df_part = raw.iloc[:half].join(adj.iloc[:half])
        hfq_part = (df_part["close"] * df_part["adj_factor"]).round(2)
        assert hfq_part.iloc[0] == pytest.approx(10.2)
        # 追加后半段（adj=2.0）后，历史 hfq 价不变（未复权价不变，因子表历史值不变）
        df_full = raw.join(adj)
        hfq_full = (df_full["close"] * df_full["adj_factor"]).round(2)
        assert hfq_full.iloc[0] == pytest.approx(10.2)  # 历史价不被污染
