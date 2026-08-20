"""P5 幸存者偏差检查：Tushare daily_basic 历史截面是否含已退市股。

若 2023 年截面不含"2024-2026 期间退市"的股票 → daily_basic 有幸存者偏差，
因子 IC 被系统性抬高（低PB/小市值等因子会持有退市票）。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from quant.config import Config  # noqa: E402


def main() -> None:
    cfg = Config.load()
    if not cfg.data.tushare_token:
        raise SystemExit("TUSHARE_TOKEN 未配置")

    import tushare as ts
    import pandas as pd

    ts.set_token(cfg.data.tushare_token)
    pro = ts.pro_api()

    # 已退市股票名单（含退市日期）
    delisted = pro.stock_basic(exchange="", list_status="D",
                               fields="ts_code,name,list_date,delist_date")
    print(f"退市名单: {len(delisted)} 只")
    if delisted.empty:
        print("⚠️ 退市名单为空（接口或权限问题）")
        return

    # 2023-2026 期间退市的（即 2023 年截面应有它们的席位）
    delisted["delist_date"] = pd.to_datetime(delisted["delist_date"], errors="coerce")
    recent = delisted[delisted["delist_date"].between("2023-01-01", "2026-07-31")]
    print(f"2023-2026 期间退市: {len(recent)} 只")

    # 抽查 3 个历史截面的股票集合
    for d in ["20230106", "20240308", "20250613"]:
        panel = pd.read_parquet(f"data/cache/factor_panels/{d}.parquet")
        panel_codes = set(panel["ts_code"])
        hit = recent[recent["ts_code"].isin(panel_codes)]
        print(f"{d}: 截面 {len(panel_codes)} 只，含期间退市股 {len(hit)} 只"
              f"（{len(hit)}/{len(recent)}）")
        if len(hit) < 5:
            print("  样本:", hit[["ts_code", "name"]].head(5).to_string(index=False))


if __name__ == "__main__":
    main()
