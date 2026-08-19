"""数据层测试：TushareFeed 缓存读写往返（不依赖网络/token）。"""

import pandas as pd
import pytest

from quant.data.tushare_feed import TushareFeed


def make_bar_df(n: int = 30) -> pd.DataFrame:
    idx = pd.bdate_range("2024-01-01", periods=n)
    return pd.DataFrame({
        "open": 10.0, "high": 10.5, "low": 9.5, "close": 10.2,
        "volume": 1e6, "amount": 1e7, "ts_code": "600000.SH",
    }, index=idx)


@pytest.fixture
def feed(tmp_path):
    # 只测缓存逻辑：token 传空串即可（_save_cache/_load_cache 不碰网络）
    f = TushareFeed.__new__(TushareFeed)
    f._cache_dir = tmp_path
    return f


class TestCacheRoundtrip:
    def test_save_load_roundtrip(self, feed):
        """存（reset_index 宽表）→ 读回必须是 date 为 index 的 datetime。"""
        df = make_bar_df()
        feed._save_cache(df, "600000.SH", "hfq")
        out = feed._load_cache("600000.SH", "hfq")
        assert out is not None
        assert isinstance(out.index, pd.DatetimeIndex)
        assert len(out) == len(df)
        assert out.index[0] == df.index[0]
        assert "date" not in out.columns  # date 应作为 index 而非列

    def test_legacy_wide_format(self, feed):
        """兼容旧格式：date 是普通列 + RangeIndex（早期版本存的）。"""
        df = make_bar_df()
        wide = df.reset_index().rename(columns={"index": "date"})
        wide.to_parquet(feed._cache_dir / "600000.SH_hfq.parquet", index=False)
        out = feed._load_cache("600000.SH", "hfq")
        assert out is not None
        assert isinstance(out.index, pd.DatetimeIndex)
        assert len(out) == len(df)

    def test_corrupted_cache_returns_none(self, feed):
        """损坏的缓存文件应优雅降级（返回 None 触发重拉），而非抛异常。"""
        path = feed._cache_dir / "600000.SH_hfq.parquet"
        path.write_bytes(b"not a parquet file")
        assert feed._load_cache("600000.SH", "hfq") is None
