#!/usr/bin/env python
"""因子面板一键验证（正式复跑链路）：IC/ICIR/分年/中性化 → 报告落盘。

用法:
    python scripts/validate_factor_panels.py --kind financial --horizons 1 4 13
    python scripts/validate_factor_panels.py --kind sentiment --horizons 1 4

输出: data/output/factor_panel_report_<kind>.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from quant.factors.processing import adjusted_forward_return  # noqa: E402
from quant.research.panel_validate import (  # noqa: E402
    build_factor_panels,
    ic_by_year,
    ic_table,
    load_context,
)


def main() -> None:
    ap = argparse.ArgumentParser(description="因子面板一键验证")
    ap.add_argument("--kind", choices=["financial", "sentiment"], required=True)
    ap.add_argument("--horizons", type=int, nargs="+", default=[1, 4],
                    help="持有期（周），默认 1 4")
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    factors = build_factor_panels(args.kind, root)
    mv, industry_map, close, adj = load_context(root)

    fwd_by_h = {h: adjusted_forward_return(close, adj, horizon=h) for h in args.horizons}

    print(f"=== {args.kind} 因子面板验证（{len(factors)} 因子 × {len(args.horizons)} 持有期）===")
    table = ic_table(factors, fwd_by_h, mv, industry_map)
    print(table.round(4).to_string(index=False))

    by_year = ic_by_year(factors, fwd_by_h[min(args.horizons)], mv, industry_map)
    print("\n=== 中性化后分年 mean_IC（最短持有期）===")
    print(by_year.round(4).to_string())

    # 报告落盘
    lines = [f"# {args.kind} 因子面板验证报告", "",
             f"- 生成: 2026-08-26 | scripts/validate_factor_panels.py --kind {args.kind}"
             f" --horizons {' '.join(map(str, args.horizons))}",
             "- 方法: 原始 RankIC → 行业+市值中性化 RankIC → ICIR/t/正占比 → 分年",
             "", "| 因子 | 持有期 | 原始IC | 中性化IC | ICIR | t | 正占比 | n |",
             "|---|---|---|---|---|---|---|---|"]
    for _, r in table.iterrows():
        lines.append(f"| {r['factor']} | {r['horizon']}周 | {r['raw_ic']:.4f} | {r['neut_ic']:.4f} "
                     f"| {r['icir']:.3f} | {r['t']:.2f} | {r['pos_ratio']:.1%} | {r['n']} |")
    lines += ["", "## 分年 mean_IC（中性化，最短持有期）", "",
              by_year.round(4).to_markdown(), "",
              "*判定标准: ICIR≥0.3 且 |mean_IC|≥0.02；t>2 为显著但弱，勿误杀*"]
    out = root / "data" / "output" / f"factor_panel_report_{args.kind}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n报告已保存: {out}")


if __name__ == "__main__":
    main()
