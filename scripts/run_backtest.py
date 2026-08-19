#!/usr/bin/env python
"""回测 CLI: 单策略或多策略回测，输出指标表格 + 交易明细。

用法:
    python scripts/run_backtest.py --symbol 600744.SH --strategy macd \\
        --start 2023-01-01 --end 2026-07-23 --capital 20000
    python scripts/run_backtest.py --symbol 600744.SH --all  # 全部策略对比

依赖: 先在 quant/.env 配置 TUSHARE_TOKEN（见 .env.example）
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 保证从项目根目录直接运行时能 import 到 src 下的包
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from quant.backtest import BacktestEngine  # noqa: E402
from quant.config import Config  # noqa: E402
from quant.data import get_feed  # noqa: E402
from quant.strategies import get_strategy  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="A股回测 CLI")
    ap.add_argument("--symbol", default="600744.SH")
    ap.add_argument("--strategy", default="macd",
                    help="sma/macd/boll/rsi/breakout")
    ap.add_argument("--all", action="store_true", help="跑全部策略对比")
    ap.add_argument("--start", default="2023-01-01")
    ap.add_argument("--end", default="2026-07-23")
    ap.add_argument("--capital", type=float, default=20_000)
    ap.add_argument("--execution", choices=["next_open", "next_close"], default="next_open")
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()

    cfg = Config.load()
    cfg.backtest.initial_capital = args.capital
    cfg.backtest.execution = args.execution
    if args.no_cache:
        cfg.data.use_cache = False

    feed = get_feed(cfg.data.provider, token=cfg.data.tushare_token,
                    cache_dir=cfg.data.cache_dir if cfg.data.use_cache else None)
    df = feed.load(args.symbol, args.start, args.end)

    engine = BacktestEngine(cfg)
    names = list(get_strategy_registry()) if args.all else [args.strategy]

    rows = []
    for name in names:
        strat = get_strategy(name)
        signal = strat.generate_signal(df)
        result = engine.run(df, signal, symbol=args.symbol)
        m = result.metrics
        rows.append({
            "策略": strat.name,
            "总收益": f"{m['total_return']*100:.2f}%",
            "年化": f"{m['annual_return']*100:.2f}%",
            "夏普": f"{m['sharpe']:.2f}",
            "卡玛": f"{m['calmar']:.2f}",
            "最大回撤": f"{m['max_drawdown']*100:.2f}%",
            "胜率": f"{m['win_rate']*100:.1f}%",
            "盈亏比": f"{m['profit_factor']:.2f}",
            "交易数": m["trade_count"],
            "年化换手": f"{m['turnover']:.1f}",
        })
        print(f"\n=== {strat.name} @ {args.symbol} ===")
        for k, v in m.items():
            if isinstance(v, float):
                print(f"  {k:<22} {v:.4f}")
            else:
                print(f"  {k:<22} {v}")

    if args.all:
        import pandas as pd
        print("\n" + pd.DataFrame(rows).to_string(index=False))


def get_strategy_registry():
    from quant.strategies import STRATEGY_REGISTRY
    return STRATEGY_REGISTRY


if __name__ == "__main__":
    main()
