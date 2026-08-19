"""Tushare 数据源实现（带本地 parquet 缓存 + 增量更新）。"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from .base import DataFeed
from .quality import normalize_columns

logger = logging.getLogger(__name__)


class TushareFeed(DataFeed):
    """从 Tushare pro.daily 拉取日线，parquet 缓存到本地。

    - 首次拉取全量并落盘缓存
    - 再次运行若缓存覆盖请求区间则直接读缓存（快、省 API 额度）
    - 缓存过期（请求了更新的日期）时自动增量补拉
    """

    def __init__(self, token: str, cache_dir: Path | None = None):
        if not token:
            raise ValueError("Tushare token 未配置：请在 quant/.env 设置 TUSHARE_TOKEN")
        import tushare as ts

        ts.set_token(token)
        self._pro = ts.pro_api()
        self._cache_dir = cache_dir or (Path(__file__).resolve().parents[3] / "data" / "cache")

    def _cache_path(self, symbol: str, adjust: str) -> Path:
        return self._cache_dir / f"{symbol}_{adjust}.parquet"

    def _load_cache(self, symbol: str, adjust: str) -> pd.DataFrame | None:
        path = self._cache_path(symbol, adjust)
        if path.exists():
            try:
                df = pd.read_parquet(path)
                # parquet 存的是 reset_index 的宽表，读回后统一恢复 date index
                if "date" in df.columns:
                    df["date"] = pd.to_datetime(df["date"])
                    df = df.set_index("date")
                elif not isinstance(df.index, pd.DatetimeIndex):
                    raise ValueError("缓存缺少 date 列")
                df = df.sort_index()
                logger.info("命中本地缓存: %s (%d 行)", path.name, len(df))
                return df
            except Exception as e:  # noqa: BLE001 缓存损坏则重拉
                logger.warning("缓存读取失败，将重拉: %s", e)
        return None

    def _save_cache(self, df: pd.DataFrame, symbol: str, adjust: str) -> None:
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        # rename_axis 统一 index 名，保证读回时能恢复为 date 列
        df.rename_axis("date").reset_index().to_parquet(
            self._cache_path(symbol, adjust), index=False
        )

    def load(self, symbol: str, start: str, end: str, adjust: str = "hfq") -> pd.DataFrame:
        cached = self._load_cache(symbol, adjust)
        if cached is not None and not cached.empty:
            # 缓存覆盖检查：取缓存最大日期，若小于请求 end 则增量补拉
            cached_max = cached.index.max().strftime("%Y%m%d")
            end_ymd = end.replace("-", "")
            if cached_max >= end_ymd:
                df = cached
            else:
                logger.info("缓存到 %s，增量拉取 %s ~ %s", cached_max, cached_max, end_ymd)
                inc = self._pro.daily(
                    ts_code=symbol, start_date=cached_max, end_date=end_ymd, adj=adjust
                )
                if inc is not None and not inc.empty:
                    inc = normalize_columns(inc)
                    df = pd.concat([cached, inc]).drop_duplicates().sort_index()
                else:
                    df = cached
        else:
            df_raw = self._pro.daily(
                ts_code=symbol,
                start_date=start.replace("-", ""),
                end_date=end.replace("-", ""),
                adj=adjust,
            )
            if df_raw is None or df_raw.empty:
                raise ValueError(f"未获取到 {symbol} 的数据，请检查代码和 token")
            df = normalize_columns(df_raw)

        # 截取请求区间并落盘
        df = df.loc[start:end]
        self._save_cache(df, symbol, adjust)
        if df.empty:
            raise ValueError(f"{symbol} 在 {start}~{end} 无数据")
        return df
