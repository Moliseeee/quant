"""akshare 财务面板：业绩报表抓取 + 按公告日无前视对齐到周频截面。

数据源: akshare stock_yjbb_em（东财业绩报表，按报告期全市场一次拉取）
字段: roe(净资产收益率)/gross_margin(销售毛利率)/rev_yoy(营收同比)/profit_yoy(净利同比)
无前视纪律: 财报公告日 T 的次日（T+1）起才可用——merge_asof 的 date_key = ann_date + 1天。

输出: data/cache/financial_panels/<trade_date>.parquet（date×stock，与 factor_panels 同构）
"""

from __future__ import annotations

import pandas as pd
from pathlib import Path

# 东财业绩报表列 → 内部字段名（原列名含"-"且有重复前缀，必须精确映射）
YJBB_COL_MAP = {
    "股票代码": "raw_code",
    "营业总收入-同比增长": "rev_yoy",
    "净利润-同比增长": "profit_yoy",
    "净资产收益率": "roe",
    "销售毛利率": "gross_margin",
    "最新公告日期": "ann_date",
}

REPORT_DATES = [
    "20221231", "20230331", "20230630", "20230930", "20231231",
    "20240331", "20240630", "20240930", "20241231",
    "20250331", "20250630", "20250930", "20251231",
    "20260331", "20260630",
]


def to_ts_code(raw: str) -> str | None:
    """东财 6 位代码 → ts_code；B 股/非标代码返回 None。"""
    c = str(raw).zfill(6)
    if c.startswith(("60", "68")):
        return f"{c}.SH"
    if c.startswith(("00", "30")):
        return f"{c}.SZ"
    if c.startswith(("43", "83", "87", "92")):
        return f"{c}.BJ"
    return None  # B股(90/20)、其他


def fetch_yjbb_snapshot(report_date: str) -> pd.DataFrame:
    """拉单个报告期的全市场业绩快照（网络调用）。"""
    import akshare as ak

    df = ak.stock_yjbb_em(date=report_date)
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.rename(columns=YJBB_COL_MAP)
    keep = list(YJBB_COL_MAP.values()) + ["净利润-净利润"]
    out = out[[c for c in keep if c in out.columns]].copy()
    out["report_date"] = report_date
    out["ts_code"] = out["raw_code"].map(to_ts_code)
    out = out[out["ts_code"].notna()].drop(columns=["raw_code"])
    # 数值列清洗：百分比字符串 → float（东财返回已是数值或 '--'）
    for col in ["rev_yoy", "profit_yoy", "roe", "gross_margin"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    out["ann_date"] = pd.to_datetime(out["ann_date"], errors="coerce")
    return out.dropna(subset=["ann_date"])


def build_snapshots(report_dates: list[str] | None = None,
                    cache_dir: Path | None = None) -> pd.DataFrame:
    """抓取全部报告期并堆叠为长表（ts_code × report_date × 公告日）。"""
    dates = report_dates or REPORT_DATES
    cache_dir = cache_dir or Path(__file__).resolve().parents[2] / "data" / "cache" / "financial_raw"
    cache_dir.mkdir(parents=True, exist_ok=True)

    frames = []
    for rd in dates:
        fpath = cache_dir / f"yjbb_{rd}.parquet"
        if fpath.exists():
            df = pd.read_parquet(fpath)
        else:
            df = fetch_yjbb_snapshot(rd)
            if not df.empty:
                df.to_parquet(fpath, index=False)
            import time
            time.sleep(0.5)  # 东财接口频率礼貌
        if not df.empty:
            frames.append(df)
        print(f"[{rd}] {len(df)} 只")
    if not frames:
        raise RuntimeError("全部报告期抓取失败")
    return pd.concat(frames, ignore_index=True)


def align_financial_to_weekly(snapshots: pd.DataFrame,
                              weekly_dates: list[str],
                              universe: pd.Series | None = None) -> dict[str, pd.DataFrame]:
    """按公告日无前视对齐到每个周频截面（T+1 可用）。

    Args:
        snapshots: build_snapshots 输出（含 ts_code/ann_date/因子列/report_date）
        weekly_dates: 周频截面日期（YYYYMMDD）
        universe: 股票池 ts_code（None = 用快照全部股票）

    Returns:
        {date: DataFrame(ts_code, 因子列, report_date, ann_date)}
    """
    snap = snapshots.copy()
    snap["date_key"] = pd.to_datetime(snap["ann_date"]) + pd.Timedelta(days=1)  # 公告次日才可用（T+1）
    # 同一公告日可能多报告期（如年报+一季报同日公告）→ 去重保留最新报告期
    snap = snap.sort_values(["ts_code", "date_key", "report_date"])
    snap = snap.drop_duplicates(subset=["ts_code", "date_key"], keep="last")
    # ⚠️ merge_asof 带 by 时 right 必须按 on 全局排序（仅组内排序会报 "right keys must be sorted"）
    snap = snap.sort_values("date_key")

    if universe is not None:
        # load_universe 返回 DataFrame(index=ts_code)；Series 则直接取值
        codes = list(universe.index) if isinstance(universe, pd.DataFrame) else list(universe)
    else:
        codes = sorted(snap["ts_code"].unique())

    factor_cols = [c for c in ["roe", "gross_margin", "rev_yoy", "profit_yoy"] if c in snap.columns]
    keep = ["ts_code", "date_key"] + factor_cols + ["report_date", "ann_date"]

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
        aligned["date"] = d
        out[d] = aligned
    return out


def save_financial_panels(aligned: dict[str, pd.DataFrame], out_dir: Path) -> None:
    """按截面落盘 data/cache/financial_panels/<date>.parquet。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    for d, df in aligned.items():
        df.to_parquet(out_dir / f"{d}.parquet", index=False)
