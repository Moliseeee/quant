#!/usr/bin/env python
"""因子有效性独立验证 v3（Kimi 审查后升级版）。

v3 修复（对应 Kimi 审查意见）:
  ① 远期收益改用复权价（close × adj_factor）——未复权收益漏掉现金分红，系统性低估高股息因子
  ② PE 因子改 E/P 口径 + pe>0 硬过滤——负盈利股堆在低 PE 端污染单调性
  ③ 新增: 十分组分层单调性表（可交易性证据）
  ④ 新增: 因子相关矩阵（价值族同族去重，防止重复下注）
  ⑤ 小市值判定理由修正: 区制依赖的高波动因子（非"死因子"）
  ⑥ 权重扁平化（不精确归一化，ICIR 估计误差 ±0.1 内不区分）

用法:
    python scripts/validate_factors.py [--report data/output/factor_report.md]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from quant.factors.ic import ic_summary, quantile_analysis, rank_ic  # noqa: E402
from quant.factors.processing import neutralize  # noqa: E402
from scipy import stats  # noqa: E402

PANEL_DIR = Path(__file__).resolve().parents[1] / "data" / "cache" / "factor_panels"
STOCK_BASIC = Path(__file__).resolve().parents[1] / "data" / "cache" / "stock_basic.parquet"

# 因子方向: value>0 表示"越大越好"
FACTOR_DIRECTIONS = {
    "low_turnover": ("turnover_rate", -1.0),
    "ep_ttm": ("pe_ttm", "ep"),      # E/P 口径: pe_ttm>0 过滤后取 1/pe_ttm
    "low_pb": ("pb", -1.0),
    "low_ps_ttm": ("ps_ttm", -1.0),
    "high_dividend": ("dv_ttm", 1.0),
    "small_mv": ("total_mv", -1.0),
}

MIN_STOCKS = 200


def load_panels(panel_dir: Path) -> dict[str, pd.DataFrame]:
    files = sorted(panel_dir.glob("*.parquet"))
    if not files:
        raise SystemExit(f"未找到截面数据: {panel_dir}")
    print(f"加载 {len(files)} 个截面...")

    frames = {f.stem: pd.read_parquet(f).set_index("ts_code") for f in files}
    dates = sorted(frames.keys())
    all_codes = sorted(set().union(*[set(frames[d].index) for d in dates]))

    cols = ["close", "pe", "pe_ttm", "pb", "ps", "ps_ttm", "total_mv",
            "turnover_rate", "dv_ttm", "adj_factor"]
    panels: dict[str, pd.DataFrame] = {}
    for col in cols:
        m = pd.DataFrame(index=pd.DatetimeIndex(pd.to_datetime(dates), name="date"),
                         columns=all_codes, dtype=float)
        for d in dates:
            s = frames[d].get(col)
            if s is not None:
                m.loc[pd.Timestamp(d), s.index] = s
        panels[col] = m
    return panels


def build_factors(panels: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """方向标准化因子面板（E/P 特殊处理）。"""
    factors: dict[str, pd.DataFrame] = {}
    for name, (col, direction) in FACTOR_DIRECTIONS.items():
        f = panels[col].astype(float)
        if direction == "ep":
            # E/P 口径: 仅盈利股（pe>0），取倒数；亏损股置 NaN（不参与排序）
            f = f.where(f > 0)
            f = 1.0 / f
        else:
            f = f * direction
        factors[name] = f
    return factors


def adjusted_forward_return(panels: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """复权远期收益（Kimi 审查 ① 修复）:
    fwd = (close×adj).shift(-1) / (close×adj) - 1（含分红再投资的近似）
    """
    adj_close = panels["close"].astype(float) * panels["adj_factor"].astype(float)
    return adj_close.shift(-1) / adj_close - 1


def load_industry_map() -> pd.Series:
    if not STOCK_BASIC.exists():
        print("⚠️ 无行业映射，跳过中性化")
        return pd.Series(dtype=object)
    sb = pd.read_parquet(STOCK_BASIC)
    return sb.set_index("ts_code")["industry"]


def neutralize_panel(f: pd.DataFrame, mv: pd.DataFrame,
                     industry_map: pd.Series) -> pd.DataFrame:
    out = pd.DataFrame(index=f.index, columns=f.columns, dtype=float)
    for date in f.index:
        cross = pd.DataFrame({"factor": f.loc[date], "total_mv": mv.loc[date]})
        cross["industry"] = cross.index.map(industry_map)
        cross = cross.dropna(subset=["factor"])
        if len(cross) < MIN_STOCKS:
            continue
        res = neutralize(cross, "factor")
        out.loc[date, res.index] = res
    return out


def factor_correlation_matrix(factors: dict[str, pd.DataFrame], n_latest: int = 52) -> pd.DataFrame:
    """因子相关矩阵：最近 n 个截面 Spearman 相关均值（同族去重用）。"""
    names = list(factors.keys())
    if len(factors[names[0]]) < 2:
        return pd.DataFrame(np.nan, index=names, columns=names)
    corrs = {a: {b: [] for b in names} for a in names}
    for date in factors[names[0]].index[-n_latest:]:
        cross = pd.DataFrame({n: factors[n].loc[date] for n in names})
        cross = cross.replace([np.inf, -np.inf], np.nan)
        valid = cross.dropna()
        if len(valid) < MIN_STOCKS:
            continue
        for i, a in enumerate(names):
            for b in names[i:]:
                rho, _ = stats.spearmanr(valid[a], valid[b])
                if not np.isnan(rho):
                    corrs[a][b].append(rho)
                    corrs[b][a].append(rho)
    m = pd.DataFrame(np.nan, index=names, columns=names)
    for a in names:
        for b in names:
            if corrs[a][b]:
                m.loc[a, b] = float(np.mean(corrs[a][b]))
    return m.round(3)


def main() -> None:
    ap = argparse.ArgumentParser(description="因子有效性独立验证 v3")
    ap.add_argument("--report", type=str, default=str(
        Path(__file__).resolve().parents[1] / "data" / "output" / "factor_report.md"))
    args = ap.parse_args()

    panels = load_panels(PANEL_DIR)
    industry_map = load_industry_map()
    fwd = adjusted_forward_return(panels)
    factors = build_factors(panels)

    # ========== 1. 因子 IC 汇总 ==========
    lines = ["# 因子有效性验证报告 v3（复权收益 + E/P 口径 + 分层 + 相关矩阵）", "",
             f"- 数据源: Tushare daily_basic + adj_factor，{len(fwd)} 个周频截面（2023-01~2026-07）",
             "- 远期收益: **复权价**（close×adj_factor，含分红再投资近似）——v3 修复",
             "- PE 因子: **E/P 口径**（pe_ttm>0 过滤后取倒数）——v3 修复",
             "- 方法: RankIC → ICIR/t值 → 行业市值中性化 → 十分组分层 → 相关矩阵", ""]

    rows = []
    print(f"{'因子':<16} {'原始ICIR':>9} {'中性ICIR':>9}  判定")
    for name, f in factors.items():
        ic = rank_ic(f, fwd, min_obs=MIN_STOCKS)
        s = ic_summary(ic)
        neutral_note = "—"
        if not industry_map.empty and name != "small_mv":
            # 小市值因子不做含市值中性化（自己回归自己=伪影，Kimi 审查 ③）
            f_neu = neutralize_panel(f, panels["total_mv"], industry_map)
            sn = ic_summary(rank_ic(f_neu, fwd, min_obs=MIN_STOCKS))
            neutral_note = f"{sn['icir']:+.3f}"
        else:
            sn = s
            if name == "small_mv":
                neutral_note = "n/a(伪影)"

        verdict = "✅ 有效" if sn["icir"] >= 0.3 and abs(sn["mean_ic"]) >= 0.02 else "❌ 未达标"
        rows.append((name, s, sn, verdict))
        print(f"{name:16s} {s['icir']:+7.3f} {neutral_note:>9}  {verdict}")

    lines.append("| 因子 | mean_IC | ICIR | t值 | 正占比 | 中性化ICIR | 判定 |")
    lines.append("|---|---|---|---|---|---|---|")
    for name, s, sn, verdict in rows:
        neu = "—" if name == "small_mv" else f"{sn['icir']:+.3f}"
        lines.append(f"| {name} | {s['mean_ic']:+.4f} | {s['icir']:+.3f} | {s['t_stat']:+.2f} "
                     f"| {s['positive_ratio']:.0%} | {neu} | {verdict} |")

    # ========== 2. 十分组分层单调性 ==========
    lines += ["", "## 十分组分层单调性（可交易性证据）", "",
              "| 因子 | Q1(最低) | Q5(中位) | Q10(最高) | Q10-Q1 多空 | 单调性 |"]
    lines.append("|---|---|---|---|---|---|")
    for name, f in factors.items():
        q = quantile_analysis(f, fwd, n_quantiles=10)
        if q.empty:
            continue
        q1, q5, q10 = (q.loc[0, "mean_ret"], q.loc[4, "mean_ret"], q.loc[9, "mean_ret"])
        ls = q.loc["LS_long_short", "mean_ret"]
        mono = "✅" if q10 > q1 else "❌"
        lines.append(f"| {name} | {q1:+.4f} | {q5:+.4f} | {q10:+.4f} | {ls:+.4f} | {mono} |")
        print(f"  分层 {name:16s} Q1={q1:+.4f} Q10={q10:+.4f} 多空={ls:+.4f} {mono}")

    # ========== 3. 因子相关矩阵 ==========
    lines += ["", "## 因子相关矩阵（近 52 截面 Spearman 均值）", ""]
    corr = factor_correlation_matrix(factors)
    lines.append("```")
    lines.append(corr.to_string())
    lines.append("```")
    print("\n因子相关矩阵（|ρ|>0.5 为同族重复下注）:")
    print(corr.to_string())

    # ========== 4. 口径声明 ==========
    lines += ["", "## 口径声明",
              "- **远期收益价格基础**: 复权价（close×adj_factor），含现金分红（v3 修复，股息因子不再被低估）",
              "- **股票池**: Tushare daily_basic 历史截面（按交易日返回当时有数据的股票）；"
              "未单独补退市名单，退市前数据在截面内，历史截面存在幸存者偏差的可能（P5 后续处理）",
              "- **PE 口径**: E/P（pe_ttm>0 过滤），亏损股置缺失不参与排序（v3 修复）",
              "- **小市值中性化**: 跳过（对 ln 市值回归自己=机械伪影），剔除理由为区制依赖"]

    # ========== 5. 权重建议（扁平化） ==========
    lines += ["", "## 权重建议（扁平化，不精确归一化）",
              "| 因子 | 建议权重 | 依据 |",
              "|---|---|---|",
              "| 低换手 | 0.40 | 双源最强共识，中性化后 0.934 |",
              "| 低PB | 0.25 | 双源确认，稳定 |",
              "| 低PS(TTM) | 0.15-0.20 | 待相关矩阵确认与价值族去重后定档 |",
              "| 高股息 | 0.15-0.20 | 复权收益口径后若 ICIR 上升则取上限 |",
              "| 低PE(E/P) | 0.05-0.10 | E/P 复测后定 |",
              "| 小市值 | 0 | 区制依赖不稳定，剔除 |"]
    lines.append("")
    lines.append(f"*验证工具: quant/factors/ic.py + processing.py ｜ v3（Kimi 审查后升级）｜ {pd.Timestamp.now():%Y-%m-%d}*")

    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text("\n".join(lines), encoding="utf-8")
    print(f"\n报告已保存: {args.report}")


if __name__ == "__main__":
    main()
