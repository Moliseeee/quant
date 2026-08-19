"""Tushare 数据源实现（本地 parquet 缓存 + 增量更新 + 复权因子方案）。

复权方案（Kimi 审查 P4 修复）:
    缓存"未复权行情 + adj_factor 因子表"两个独立文件，使用时再算复权。
    原因: hfq 历史价会随新的分红送股整体重乘因子，缓存复权价做增量更新
    会拼接"旧因子版本历史 + 新因子版本增量"，除权日后全部历史价格系统性跳变。
    未复权价和 adj_factor 的历史值都不会因新分红而改变 → 增量更新永远安全。

复权公式:
    hfq = 未复权 × adj_factor
    qfq = 未复权 × adj_factor / 最新 adj_factor
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from .base import DataFeed
from .quality import normalize_columns

logger = logging.getLogger(__name__)


class TushareFeed(DataFeed):
    """从 Tushare pro 拉取日线，未复权 + adj_factor 双缓存。"""

    def __init__(self, token: str, cache_dir: Path | None = None):
        if not token:
            raise ValueError("Tushare token 未配置：请在 quant/.env 设置 TUSHARE_TOKEN")
        import tushare as ts

        ts.set_token(token)
        self._pro = ts.pro_api()
        self._cache_dir = cache_dir or (Path(__file__).resolve().parents[3] / "data" / "cache")

    # ------------------------------------------------------------------
    # 缓存路径：未复权行情 + adj_factor 因子表
    # ------------------------------------------------------------------
    def _raw_path(self, symbol: str) -> Path:
        return self._cache_dir / f"{symbol}_raw.parquet"

    def _adj_path(self, symbol: str) -> Path:
        return self._cache_dir / f"{symbol}_adjfactor.parquet"

    def _load_parquet(self, path: Path) -> pd.DataFrame | None:
        if not path.exists():
            return None
        try:
            df = pd.read_parquet(path)
            if "date" in df.columns and not isinstance(df.index, pd.DatetimeIndex):
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date")
            return df.sort_index()
        except Exception as e:  # noqa: BLE001 缓存损坏则重拉
            logger.warning("缓存读取失败，将重拉: %s", e)
            return None

    def _save_parquet(self, df: pd.DataFrame, path: Path) -> None:
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        df.rename_axis("date").reset_index().to_parquet(path, index=False)

    # ------------------------------------------------------------------
    # 增量拉取未复权行情
    # ------------------------------------------------------------------
    def _load_raw(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        start_ymd, end_ymd = start.replace("-", ""), end.replace("-", "")
        cached = self._load_parquet(self._raw_path(symbol))
        if cached is not None and not cached.empty:
            cached_max = cached.index.max().strftime("%Y%m%d")
            if cached_max >= end_ymd:
                return cached
            logger.info("未复权缓存到 %s，增量拉取 %s~%s", cached_max, cached_max, end_ymd)
            inc = self._pro.daily(ts_code=symbol, start_date=cached_max, end_date=end_ymd)
            if inc is not None and not inc.empty:
                inc = normalize_columns(inc)
                return pd.concat([cached, inc]).drop_duplicates().sort_index()
            return cached

        raw = self._pro.daily(ts_code=symbol, start_date=start_ymd, end_date=end_ymd)
        if raw is None or raw.empty:
            raise ValueError(f"未获取到 {symbol} 的数据，请检查代码和 token")
        return normalize_columns(raw)

    # ------------------------------------------------------------------
    # 增量拉取 adj_factor 因子表
    # ------------------------------------------------------------------
    def _load_adj(self, symbol: str, start: str, end: str) -> pd.Series:
        start_ymd, end_ymd = start.replace("-", ""), end.replace("-", "")
        cached = self._load_parquet(self._adj_path(symbol))
        if cached is not None and not cached.empty:
            cached_max = cached.index.max().strftime("%Y%m%d")
            if cached_max >= end_ymd:
                return cached["adj_factor"]
            logger.info("adj_factor 缓存到 %s，增量拉取", cached_max)
            inc = self._pro.adj_factor(ts_code=symbol, start_date=cached_max, end_date=end_ymd)
            if inc is not None and not inc.empty:
                inc = inc.rename(columns={"trade_date": "date"})
                inc["date"] = pd.to_datetime(inc["date"])
                inc = inc.set_index("date").sort_index()
                merged = pd.concat([cached, inc]).drop_duplicates().sort_index()
                return merged["adj_factor"]
            return cached["adj_factor"]

        af = self._pro.adj_factor(ts_code=symbol, start_date=start_ymd, end_date=end_ymd)
        if af is None or af.empty:
            raise ValueError(f"{symbol} 无 adj_factor 数据")
        af = af.rename(columns={"trade_date": "date"})
        af["date"] = pd.to_datetime(af["date"])
        return af.set_index("date")["adj_factor"].sort_index()

    # ------------------------------------------------------------------
    def load(self, symbol: str, start: str, end: str, adjust: str = "hfq") -> pd.DataFrame:
        raw = self._load_raw(symbol, start, end)
        adj = self._load_adj(symbol, start, end)

        # 对齐并复权
        df = raw.join(adj, how="left")
        if df["adj_factor"].isna().any():
            missing = int(df["adj_factor"].isna().sum())
            logger.warning("%s 有 %d 天缺 adj_factor（早期未上市/停牌），按 1.0 处理", symbol, missing)
            df["adj_factor"] = df["adj_factor"].fillna(1.0)

        if adjust == "hfq":
            factor = df["adj_factor"]
        elif adjust == "qfq":
            latest = float(df["adj_factor"].iloc[-1])
            factor = df["adj_factor"] / latest if latest > 0 else df["adj_factor"]
        elif adjust in ("", "none"):
            factor = pd.Series(1.0, index=df.index)
        else:
            raise ValueError(f"未知复权方式: {adjust}")

        for col in ["open", "high", "low", "close"]:
            df[col] = (df[col] * factor).round(2)

        # 落盘缓存（未复权原样存，不污染）
        self._save_parquet(raw, self._raw_path(symbol))
        adj_df = adj.to_frame(name="adj_factor")
        self._save_parquet(adj_df, self._adj_path(symbol))

        df = df.loc[start:end]
        if df.empty:
            raise ValueError(f"{symbol} 在 {start}~{end} 无数据")
        return df
