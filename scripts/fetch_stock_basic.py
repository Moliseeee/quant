#!/usr/bin/env python
"""拉取股票基础信息（行业映射，因子中性化用），存 parquet。

输出: data/cache/stock_basic.parquet
字段: ts_code, name, industry, market, list_date
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from quant.config import Config  # noqa: E402


def main() -> None:
    cfg = Config.load()
    if not cfg.data.tushare_token:
        raise SystemExit("TUSHARE_TOKEN 未配置")

    import tushare as ts

    ts.set_token(cfg.data.tushare_token)
    pro = ts.pro_api()

    df = pro.stock_basic(
        exchange="", list_status="L",
        fields="ts_code,name,industry,market,list_date",
    )
    if df is None or df.empty:
        raise SystemExit("stock_basic 获取失败")

    out = Path(__file__).resolve().parents[1] / "data" / "cache" / "stock_basic.parquet"
    df.to_parquet(out, index=False)
    print(f"stock_basic 已保存: {out}，{len(df)} 只，行业数 {df['industry'].nunique()}")
    print("行业分布 Top10:")
    print(df["industry"].value_counts().head(10).to_string())


if __name__ == "__main__":
    main()
