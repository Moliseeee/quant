#!/usr/bin/env python
"""策略失效归因：分段因子 IC 对比（CLI 壳，逻辑在 quant/research/attribution.py）。

用法:
    python scripts/factor_attribution.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from quant.data import load_panels  # noqa: E402
from quant.research import icir_trend, segment_factor_ic  # noqa: E402

PANEL_DIR = Path(__file__).resolve().parents[1] / "data" / "cache" / "factor_panels"
STOCK_BASIC = Path(__file__).resolve().parents[1] / "data" / "cache" / "stock_basic.parquet"

SEGMENTS = [
    ("2023", "2023-01-01", "2023-12-31"),
    ("2024", "2024-01-01", "2024-12-31"),
    ("2025-2026H1", "2025-01-01", "2026-07-31"),
]


def main() -> None:
    panels = load_panels(PANEL_DIR)
    industry_map = None
    if STOCK_BASIC.exists():
        import pandas as pd

        industry_map = pd.read_parquet(STOCK_BASIC).set_index("ts_code")["industry"]

    df = segment_factor_ic(panels, SEGMENTS, industry_map)
    print(f"{'因子':<16} {'分段':<12} {'原始ICIR':>9} {'中性ICIR':>9}")
    print("-" * 52)
    for _, row in df.iterrows():
        neu = "—" if row["neutral_icir"] is None else f"{row['neutral_icir']:+.3f}"
        print(f"{row['factor']:<16} {row['segment']:<12} {row['raw_icir']:+8.3f} {neu:>9}")

    print("\nICIR 趋势（原始口径，>0 有效，衰减=策略失效来源）:")
    for factor in df["factor"].unique():
        print(" ", icir_trend(df[df["factor"] == factor]))


if __name__ == "__main__":
    main()
