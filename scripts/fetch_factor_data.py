#!/usr/bin/env python
"""全市场因子截面抓取（Tushare daily_basic，2120 积分可用）。

用法:
    python scripts/fetch_factor_data.py --start 20230101 --end 20260723
    python scripts/fetch_factor_data.py --freq weekly --limit 5   # 测试只拉 5 个截面

输出: data/cache/factor_panels/<trade_date>.parquet（每个截面一个文件，date×stock 宽表）
字段: ts_code, close, pe, pb, ps, total_mv, circ_mv, turnover_rate, dv_ttm
数据用途: factors/ic.py 的 RankIC/ICIR/分层检验（因子有效性验证）
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from quant.config import Config  # noqa: E402


def get_trade_dates(pro, start: str, end: str, freq: str) -> list[str]:
    """从交易日历取交易日（freq=weekly 时取每周最后一个交易日）。"""
    import pandas as pd

    cal = pro.trade_cal(exchange="SSE", start_date=start, end_date=end, is_open="1")
    if cal is None or cal.empty:
        raise ValueError("交易日历获取失败")
    dates = pd.to_datetime(cal["cal_date"]).sort_values()
    if freq == "weekly":
        # 按 ISO 周分组取每周最后一天
        week = dates.dt.isocalendar().year.astype(str) + "-W" + dates.dt.isocalendar().week.astype(str)
        dates = dates.groupby(week.values).max()
    return [d.strftime("%Y%m%d") for d in dates]


def main() -> None:
    ap = argparse.ArgumentParser(description="全市场因子截面抓取")
    ap.add_argument("--start", default="20230101")
    ap.add_argument("--end", default="20260723")
    ap.add_argument("--freq", choices=["daily", "weekly"], default="weekly",
                    help="截面频率（weekly 省 API 额度）")
    ap.add_argument("--limit", type=int, default=0, help="只拉前 N 个截面（测试用，0=全部）")
    args = ap.parse_args()

    cfg = Config.load()
    if not cfg.data.tushare_token:
        raise SystemExit("TUSHARE_TOKEN 未配置，请在 quant/.env 设置")

    import tushare as ts

    ts.set_token(cfg.data.tushare_token)
    pro = ts.pro_api()

    dates = get_trade_dates(pro, args.start, args.end, args.freq)
    if args.limit:
        dates = dates[: args.limit]
    print(f"共 {len(dates)} 个截面（{args.freq}），范围 {dates[0]} ~ {dates[-1]}")

    out_dir = Path(__file__).resolve().parents[1] / "data" / "cache" / "factor_panels"
    out_dir.mkdir(parents=True, exist_ok=True)

    fields = "ts_code,trade_date,close,pe,pb,ps,total_mv,circ_mv,turnover_rate,dv_ttm"
    ok, fail = 0, 0
    for i, d in enumerate(dates, 1):
        fpath = out_dir / f"{d}.parquet"
        if fpath.exists():
            print(f"[{i}/{len(dates)}] {d} 已存在，跳过")
            ok += 1
            continue
        try:
            df = pro.daily_basic(trade_date=d, fields=fields)
            if df is None or df.empty:
                print(f"[{i}/{len(dates)}] {d} 空数据（非交易日）")
                continue
            df.to_parquet(fpath, index=False)
            print(f"[{i}/{len(dates)}] {d} → {len(df)} 只股票")
            ok += 1
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(dates)}] {d} 失败: {e}")
            fail += 1

    print(f"\n完成: 成功 {ok}，失败 {fail}。输出目录: {out_dir}")


if __name__ == "__main__":
    main()
