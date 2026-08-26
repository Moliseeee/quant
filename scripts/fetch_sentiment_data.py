#!/usr/bin/env python
"""全市场情绪面板抓取（akshare 两融 + 龙虎榜，T+1 无前视对齐到周频截面）。

用法:
    python scripts/fetch_sentiment_data.py                 # 全部周截面
    python scripts/fetch_sentiment_data.py --end 20260820  # 只到指定日期

输出: data/cache/sentiment_panels/<trade_date>.parquet
字段: ts_code, margin_balance(融资余额), lhb_net(龙虎榜净买额), lhb_count(上榜次数)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from quant.data.panels import load_universe  # noqa: E402
from quant.data.sentiment import (  # noqa: E402
    align_sentiment_to_weekly,
    build_sentiment_snapshots,
    save_sentiment_panels,
)


def main() -> None:
    ap = argparse.ArgumentParser(description="全市场情绪面板抓取（akshare）")
    ap.add_argument("--end", default=None, help="对齐到该日期前的截面（YYYYMMDD）")
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 个周截面（测试用）")
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    panel_dir = root / "data" / "cache" / "factor_panels"
    out_dir = root / "data" / "cache" / "sentiment_panels"

    weekly_dates = sorted(p.name.replace(".parquet", "") for p in panel_dir.glob("*.parquet"))
    if not weekly_dates:
        raise SystemExit("未找到因子面板，先跑 fetch_factor_data.py")
    if args.end:
        weekly_dates = [d for d in weekly_dates if d <= args.end]
    if args.limit:
        weekly_dates = weekly_dates[: args.limit]
    print(f"对齐到 {len(weekly_dates)} 个周频截面（{weekly_dates[0]} ~ {weekly_dates[-1]}）")

    snapshots = build_sentiment_snapshots(weekly_dates, root / "data" / "cache" / "sentiment_raw")
    print(f"快照总行数: {len(snapshots)}，覆盖股票: {snapshots['ts_code'].nunique()}")

    universe = None
    sb_path = root / "data" / "cache" / "stock_basic.parquet"
    if sb_path.exists():
        universe = load_universe(sb_path)
        print(f"使用股票池: {len(universe)} 只")

    aligned = align_sentiment_to_weekly(snapshots, weekly_dates, universe)
    save_sentiment_panels(aligned, out_dir)
    print(f"已输出 {len(aligned)} 个情绪截面到 {out_dir}")


if __name__ == "__main__":
    main()
