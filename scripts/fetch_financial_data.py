#!/usr/bin/env python
"""全市场财务面板抓取（akshare 业绩报表，按公告日无前视对齐到周频截面）。

用法:
    python scripts/fetch_financial_data.py                 # 全部报告期 + 对齐到现有因子面板截面
    python scripts/fetch_financial_data.py --end 20260820  # 对齐到指定日期前的截面

输出: data/cache/financial_panels/<trade_date>.parquet（与 factor_panels 同构）
字段: ts_code, roe, gross_margin, rev_yoy, profit_yoy, report_date, ann_date
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from quant.data.financial import (  # noqa: E402
    align_financial_to_weekly,
    build_snapshots,
    save_financial_panels,
)
from quant.data.panels import load_universe  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="全市场财务面板抓取（akshare）")
    ap.add_argument("--end", default=None, help="对齐到该日期前的截面（YYYYMMDD，默认取面板最新）")
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 个报告期（测试用）")
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    panel_dir = root / "data" / "cache" / "factor_panels"
    out_dir = root / "data" / "cache" / "financial_panels"

    weekly_dates = sorted(p.name.replace(".parquet", "") for p in panel_dir.glob("*.parquet"))
    if not weekly_dates:
        raise SystemExit("未找到因子面板，先跑 fetch_factor_data.py")
    if args.end:
        weekly_dates = [d for d in weekly_dates if d <= args.end]
    print(f"对齐到 {len(weekly_dates)} 个周频截面（{weekly_dates[0]} ~ {weekly_dates[-1]}）")

    snapshots = build_snapshots(report_dates=None, cache_dir=root / "data" / "cache" / "financial_raw")
    print(f"快照总行数: {len(snapshots)}，覆盖股票: {snapshots['ts_code'].nunique()}")

    # 股票池：与因子面板一致（行业映射表），无则用快照全集
    universe = None
    sb_path = root / "data" / "cache" / "stock_basic.parquet"
    if sb_path.exists():
        universe = load_universe(sb_path)
        print(f"使用股票池: {len(universe)} 只")
    else:
        print("警告: 无 stock_basic.parquet，用快照全集对齐")

    aligned = align_financial_to_weekly(snapshots, weekly_dates, universe)
    save_financial_panels(aligned, out_dir)
    print(f"已输出 {len(aligned)} 个财务截面到 {out_dir}")


if __name__ == "__main__":
    main()
