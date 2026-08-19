"""数据质量检测：复权一致性、涨跌停、停牌、异常值。

机构级回测的前提是数据可信。这些检查在回测前必须跑一遍。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# 规范化后的列名约定
REQUIRED_COLS = ["open", "high", "low", "close", "volume"]
# Tushare 原始列名 -> 规范化列名
TUSHARE_COL_MAP = {
    "trade_date": "date",
    "vol": "volume",
    "amount": "amount",
}


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """把常见数据源列名统一成规范名（date/open/high/low/close/volume）。"""
    df = df.rename(columns=TUSHARE_COL_MAP)
    # 日期列转 datetime，并设为 index
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
    for col in REQUIRED_COLS:
        if col not in df.columns:
            raise ValueError(f"数据缺少必需列: {col}")
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def check_duplicates(df: pd.DataFrame) -> list[str]:
    """检查重复日期。"""
    dups = df.index[df.index.duplicated(keep=False)]
    return [d.strftime("%Y-%m-%d") for d in dups.unique()]


def check_missing(df: pd.DataFrame) -> list[str]:
    """检查 OHLC 缺失值。"""
    bad = df[df[["open", "high", "low", "close"]].isna().any(axis=1)]
    return [d.strftime("%Y-%m-%d") for d in bad.index]


def check_prices(df: pd.DataFrame) -> list[str]:
    """检查价格合理性: 负价、high<low、high<max(open,close) 等。"""
    bad = []
    for d, row in df.iterrows():
        o, h, l, c = row["open"], row["high"], row["low"], row["close"]
        if min(o, h, l, c) <= 0:
            bad.append(d.strftime("%Y-%m-%d"))
        elif h < l or h < max(o, c) or l > min(o, c):
            bad.append(d.strftime("%Y-%m-%d"))
    return bad


def detect_suspensions(df: pd.DataFrame, min_volume: float = 0.0) -> list[str]:
    """停牌检测：成交量为 0 或缺失视为停牌。"""
    vol = df["volume"].fillna(0)
    return [d.strftime("%Y-%m-%d") for d in df.index[vol <= min_volume]]


def compute_limit_prices(df: pd.DataFrame, limit_pct: float = 0.10) -> pd.DataFrame:
    """计算每日涨停价/跌停价（基于前一交易日收盘价，四舍五入到分）。

    A股规则: 涨跌停价 = 前收 × (1 ± limit_pct)，四舍五入保留两位。
    """
    prev_close = df["close"].shift(1)
    df = df.copy()
    df["limit_up"] = (prev_close * (1 + limit_pct)).round(2)
    df["limit_down"] = (prev_close * (1 - limit_pct)).round(2)
    return df


def run_quality_report(df: pd.DataFrame, symbol: str, limit_pct: float = 0.10) -> dict:
    """数据质量总报告。返回 {问题类型: 日期列表}，空 dict 表示数据干净。"""
    report: dict[str, list[str]] = {}
    dup = check_duplicates(df)
    if dup:
        report["duplicate_dates"] = dup
    miss = check_missing(df)
    if miss:
        report["missing_prices"] = miss
    bad = check_prices(df)
    if bad:
        report["bad_prices"] = bad
    susp = detect_suspensions(df)
    if susp:
        report["suspended"] = susp
    return report
