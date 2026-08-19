"""AKShare 数据源（免费、无 token，数据来自东方财富/新浪等公开接口）。

这是 iFinD/Tushare 付费额度之外的主力免费数据源：
- 日线: stock_zh_a_hist（支持前/后复权）
- 全市场实时快照: stock_zh_a_spot_em（PE/PB/市值/换手，用于选股）

注意: akshare 接口依赖上游网页结构，偶发失效属正常；失效时换 Tushare/CSV。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pandas as pd

from .base import DataFeed

logger = logging.getLogger(__name__)

# 国内数据站域名：走直连，不走系统代理（代理是给墙外站用的，连东财会失败）
_CN_DATA_DOMAINS = (
    "push2his.eastmoney.com,push2.eastmoney.com,quote.eastmoney.com,"
    "datacenter-web.eastmoney.com,emweb.securities.eastmoney.com,"
    "hq.sinajs.cn,finance.sina.com.cn,qt.gtimg.cn,web.ifzq.gtimg.cn,"
    "proxy.finance.qq.com,www.cninfo.com.cn"
)


def _ensure_cn_no_proxy() -> None:
    """把国内数据域名追加进 NO_PROXY（进程级，幂等）。"""
    current = os.environ.get("NO_PROXY", "") + os.environ.get("no_proxy", "")
    for domain in _CN_DATA_DOMAINS.split(","):
        if domain not in current:
            current = f"{current},{domain}" if current else domain
    os.environ["NO_PROXY"] = current

# 日线接口中文列 → 规范化列名
HIST_COL_MAP = {
    "日期": "date",
    "开盘": "open",
    "收盘": "close",
    "最高": "high",
    "最低": "low",
    "成交量": "volume",
    "成交额": "amount",
}

# 全市场快照中文列 → 规范化列名（选股用）
SPOT_COL_MAP = {
    "代码": "ts_code",
    "名称": "name",
    "最新价": "close",
    "涨跌幅": "pct_chg",
    "换手率": "turnover_rate",
    "市盈率-动态": "pe",
    "市净率": "pb",
    "总市值": "total_mv",
    "流通市值": "circ_mv",
    "成交额": "amount",
}


class AkShareFeed(DataFeed):
    """从 akshare 拉取日线，parquet 缓存（与 TushareFeed 同模式）。"""

    def __init__(self, cache_dir: Path | None = None):
        import akshare as ak

        _ensure_cn_no_proxy()  # 国内数据站直连，绕过用户代理
        self._ak = ak
        self._cache_dir = cache_dir or (Path(__file__).resolve().parents[3] / "data" / "cache")

    # ------------------------------------------------------------------
    def _cache_path(self, symbol: str, adjust: str) -> Path:
        return self._cache_dir / f"{symbol}_{adjust}_ak.parquet"

    def _load_cache(self, symbol: str, adjust: str) -> pd.DataFrame | None:
        path = self._cache_path(symbol, adjust)
        if path.exists():
            try:
                df = pd.read_parquet(path)
                if "date" in df.columns:
                    df["date"] = pd.to_datetime(df["date"])
                    df = df.set_index("date")
                df = df.sort_index()
                return df
            except Exception as e:  # noqa: BLE001
                logger.warning("akshare 缓存读取失败，重拉: %s", e)
        return None

    def _save_cache(self, df: pd.DataFrame, symbol: str, adjust: str) -> None:
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        df.rename_axis("date").reset_index().to_parquet(
            self._cache_path(symbol, adjust), index=False
        )

    # ------------------------------------------------------------------
    def load(self, symbol: str, start: str, end: str, adjust: str = "hfq") -> pd.DataFrame:
        cached = self._load_cache(symbol, adjust)
        if cached is not None and not cached.empty:
            cached_max = cached.index.max().strftime("%Y%m%d")
            end_ymd = end.replace("-", "")
            if cached_max >= end_ymd:
                df = cached
            else:
                logger.info("akshare 缓存到 %s，增量拉取 %s~%s", cached_max, cached_max, end_ymd)
                inc_raw = self._ak.stock_zh_a_hist(
                    symbol=symbol.split(".")[0], period="daily",
                    start_date=cached_max, end_date=end_ymd, adjust=adjust,
                )
                inc = self._normalize(inc_raw)
                df = pd.concat([cached, inc]).drop_duplicates().sort_index()
        else:
            raw = self._ak.stock_zh_a_hist(
                symbol=symbol.split(".")[0], period="daily",
                start_date=start.replace("-", ""), end_date=end.replace("-", ""),
                adjust=adjust,
            )
            if raw is None or raw.empty:
                raise ValueError(f"akshare 未获取到 {symbol} 的数据")
            df = self._normalize(raw)

        df = df.loc[start:end]
        self._save_cache(df, symbol, adjust)
        if df.empty:
            raise ValueError(f"{symbol} 在 {start}~{end} 无数据")
        return df

    # ------------------------------------------------------------------
    @staticmethod
    def _normalize(raw: pd.DataFrame) -> pd.DataFrame:
        """中文列 → 规范化列（date index）。"""
        df = raw.rename(columns=HIST_COL_MAP)
        if "date" not in df.columns:
            raise ValueError(f"akshare 返回列缺失: {list(raw.columns)}")
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        keep = [c for c in ["open", "high", "low", "close", "volume", "amount"] if c in df.columns]
        return df[keep].astype(float)

    # ------------------------------------------------------------------
    def fetch_market_snapshot(self) -> pd.DataFrame:
        """全市场实时快照（选股用）：PE/PB/市值/换手率。返回规范化列。"""
        raw = self._ak.stock_zh_a_spot_em()
        df = raw.rename(columns=SPOT_COL_MAP)
        keep = [c for c in SPOT_COL_MAP.values() if c in df.columns]
        df = df[keep].copy()
        # 总市值单位：元 → 亿
        for col in ["total_mv", "circ_mv"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce") / 1e8
        return df
