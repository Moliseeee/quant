"""情绪因子数据层：两融 + 龙虎榜，按 T+1 无前视对齐到周频截面。

数据源（akshare）:
- stock_margin_detail_sse / stock_margin_detail_szse（融资融券明细，按交易日）
- stock_lhb_detail_em（龙虎榜，按日期区间）

无前视纪律: 数据 T 日盘后公布 → date_key = 数据日 + 1 天（T+1 起可用），
与 financial.py 同一模式；周截面日期若等于数据日则匹配到上一周数据（自动 T+1）。

输出: data/cache/sentiment_panels/<trade_date>.parquet
字段: ts_code, margin_balance(融资余额), lhb_net(龙虎榜净买额), lhb_count(上榜次数)
因子（在验证层构造）: margin_chg_4w = margin_balance 4周变化率; lhb_net_4w = 4周净买额累计
"""

from __future__ import annotations

import pandas as pd
from pathlib import Path

from .financial import to_ts_code

MARGIN_COL_MAP = {
    "标的证券代码": "raw_code",  # 沪
    "证券代码": "raw_code",      # 深
    "融资余额": "margin_balance",
}
LHB_COL_MAP = {
    "代码": "raw_code",
    "龙虎榜净买额": "lhb_net",
}


def fetch_margin_daily(date: str) -> pd.DataFrame:
    """拉单交易日全市场两融（沪+深），返回 ts_code × margin_balance。"""
    import akshare as ak

    frames = []
    for fn in ["stock_margin_detail_sse", "stock_margin_detail_szse"]:
        try:
            df = getattr(ak, fn)(date=date)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        df = df.rename(columns=MARGIN_COL_MAP)
        keep = [c for c in ["raw_code", "margin_balance"] if c in df.columns]
        frames.append(df[keep])
    if not frames:
        return pd.DataFrame(columns=["ts_code", "margin_balance"])
    out = pd.concat(frames, ignore_index=True)
    out["ts_code"] = out["raw_code"].map(to_ts_code)
    out = out[out["ts_code"].notna()].drop(columns=["raw_code"])
    out["margin_balance"] = pd.to_numeric(out["margin_balance"], errors="coerce")
    return out.dropna(subset=["margin_balance"])


def fetch_lhb_range(start: str, end: str) -> pd.DataFrame:
    """拉日期区间龙虎榜，按股票聚合净买额与上榜次数。"""
    import akshare as ak

    df = ak.stock_lhb_detail_em(start_date=start, end_date=end)
    if df is None or df.empty:
        return pd.DataFrame(columns=["ts_code", "lhb_net", "lhb_count"])
    df = df.rename(columns=LHB_COL_MAP)
    df["ts_code"] = df["raw_code"].map(to_ts_code)
    df = df[df["ts_code"].notna()]
    df["lhb_net"] = pd.to_numeric(df["lhb_net"], errors="coerce").fillna(0.0)
    agg = df.groupby("ts_code").agg(lhb_net=("lhb_net", "sum"), lhb_count=("raw_code", "size"))
    return agg.reset_index()


def build_sentiment_snapshots(weekly_dates: list[str],
                              cache_dir: Path | None = None) -> pd.DataFrame:
    """抓全部周截面（每周最后交易日）的两融+龙虎榜，堆叠为长表（T+1 可用）。

    返回列: ts_code, date_key, margin_balance, lhb_net, lhb_count
    """
    cache_dir = cache_dir or Path(__file__).resolve().parents[2] / "data" / "cache" / "sentiment_raw"
    cache_dir.mkdir(parents=True, exist_ok=True)

    import datetime as dt

    frames = []
    for d in weekly_dates:
        fpath = cache_dir / f"sentiment_{d}.parquet"
        if fpath.exists():
            df = pd.read_parquet(fpath)
        else:
            d_ts = pd.Timestamp(d)
            start = (d_ts - pd.Timedelta(days=6)).strftime("%Y%m%d")  # 周一起
            m = fetch_margin_daily(d)
            l = fetch_lhb_range(start, d)
            if m.empty and l.empty:
                continue
            df = m.merge(l, on="ts_code", how="outer")
            df["date_key"] = pd.Timestamp(d) + pd.Timedelta(days=1)  # T+1 可用
            df.to_parquet(fpath, index=False)
            import time
            time.sleep(0.4)
        if not df.empty:
            frames.append(df)
        print(f"[{d}] 快照 {len(df)} 只")
    if not frames:
        raise RuntimeError("情绪数据抓取失败")
    return pd.concat(frames, ignore_index=True)


def align_sentiment_to_weekly(snapshots: pd.DataFrame,
                              weekly_dates: list[str],
                              universe: pd.Series | pd.DataFrame | None = None) -> dict[str, pd.DataFrame]:
    """按 date_key（T+1）asof 对齐到周频截面。"""
    snap = snapshots.copy()
    snap["date_key"] = pd.to_datetime(snap["date_key"])
    snap = snap.sort_values("date_key")
    snap = snap.drop_duplicates(subset=["ts_code", "date_key"], keep="last")
    # 快照日期副本（merge_asof 的 on 列输出 left 的值，匹配到的快照日期必须单独保留）
    snap["src_date"] = snap["date_key"]

    if universe is not None:
        codes = list(universe.index) if isinstance(universe, pd.DataFrame) else list(universe)
    else:
        codes = sorted(snap["ts_code"].unique())

    keep = ["ts_code", "date_key", "src_date", "margin_balance", "lhb_net", "lhb_count"]
    out: dict[str, pd.DataFrame] = {}
    for d in weekly_dates:
        d_ts = pd.to_datetime(d)
        query = pd.DataFrame({"ts_code": codes, "date_key": d_ts})
        aligned = pd.merge_asof(
            query.sort_values("date_key"),
            snap[keep],
            on="date_key",
            by="ts_code",
            direction="backward",
        )
        # ⚠️ 陈旧值清洗（Codex 审查 2026-08-26 抓出）:
        # merge_asof backward 会把"最近一次有数据"的快照携带到无数据的周——
        # 若某股票本周既非两融标的又未上榜，匹配到的 src_date 远早于截面周，
        # 旧值被 rolling 重复累计。语义修正：
        #   margin_balance: 非最近一周(6天窗口) → NaN（不在标的池，不参与）
        #   lhb_net/lhb_count: 非最近一周 → 0（未上榜 = 中性）
        recent = aligned["src_date"] >= (d_ts - pd.Timedelta(days=6))
        aligned.loc[~recent, "margin_balance"] = pd.NA
        aligned.loc[~recent, ["lhb_net", "lhb_count"]] = 0.0
        aligned["date"] = d
        out[d] = aligned
    return out


def save_sentiment_panels(aligned: dict[str, pd.DataFrame], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for d, df in aligned.items():
        df.to_parquet(out_dir / f"{d}.parquet", index=False)
