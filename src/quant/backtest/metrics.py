"""绩效指标套件。

覆盖: 收益/风险/回撤/交易质量/超额收益 五个维度。
所有年化比率由 periods_per_year 参数化（Kimi 审查 P6 修复）:
    - 日频数据: 252（默认，单标的回测）
    - 周频数据: 52（组合回测）
    - 月频数据: 12
硬编码 252 会把周频 equity 的年化指标放大 ~4.85×（K3 2026-08 实测抓出）。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def _to_returns(equity: pd.Series) -> pd.Series:
    return equity.pct_change().dropna()


def infer_periods_per_year(index: pd.DatetimeIndex) -> int:
    """从日期索引推断年化频率：相邻日期间距的众数。

    ~1 天 → 252（日频）；~7 天 → 52（周频）；~30 天 → 12（月频）。
    无法判断时回退 252（日频假设）。
    """
    if index is None or len(index) < 2:
        return TRADING_DAYS
    diffs = pd.Series(index).diff().dropna().dt.days
    if diffs.empty:
        return TRADING_DAYS
    mode_vals = diffs.mode()
    mode_days = int(mode_vals.iloc[0]) if not mode_vals.empty else int(diffs.mean())
    if mode_days >= 25:
        return 12
    if mode_days >= 5:
        return 52
    return TRADING_DAYS


def annualized_return(equity: pd.Series, periods_per_year: int = TRADING_DAYS) -> float:
    """年化收益（几何）。"""
    n = len(equity)
    if n == 0:
        return 0.0
    total = equity.iloc[-1] / equity.iloc[0] - 1 if equity.iloc[0] > 0 else 0.0
    if total <= -1:
        return -1.0
    return (1 + total) ** (periods_per_year / n) - 1


def annualized_volatility(equity: pd.Series, periods_per_year: int = TRADING_DAYS) -> float:
    """年化波动率。"""
    r = _to_returns(equity)
    if r.empty:
        return 0.0
    return float(r.std(ddof=1) * np.sqrt(periods_per_year))


def sharpe_ratio(equity: pd.Series, rf: float = 0.0,
                 periods_per_year: int = TRADING_DAYS) -> float:
    """夏普比率: (年化收益 - 无风险利率) / 年化波动。

    波动率低于 1e-10 视为 0（纯浮点噪声），返回 0 表示无风险收益。
    """
    vol = annualized_volatility(equity, periods_per_year)
    if vol < 1e-10:
        return 0.0
    return (annualized_return(equity, periods_per_year) - rf) / vol


def downside_volatility(equity: pd.Series, periods_per_year: int = TRADING_DAYS) -> float:
    """下行波动率（仅负收益）。"""
    r = _to_returns(equity)
    if r.empty:
        return 0.0
    downside = r[r < 0]
    if len(downside) < 2:
        return 0.0
    return float(downside.std(ddof=1) * np.sqrt(periods_per_year))


def sortino_ratio(equity: pd.Series, rf: float = 0.0,
                  periods_per_year: int = TRADING_DAYS) -> float:
    """索提诺比率: 用下行波动替代总波动。"""
    dv = downside_volatility(equity, periods_per_year)
    if dv == 0:
        return 0.0
    return (annualized_return(equity, periods_per_year) - rf) / dv


def max_drawdown(equity: pd.Series) -> float:
    """最大回撤（正数表示回撤幅度，如 0.25 = -25%）。"""
    if len(equity) < 2:
        return 0.0
    running_max = equity.cummax()
    dd = (equity - running_max) / running_max
    return float(-dd.min())


def max_drawdown_duration(equity: pd.Series) -> int:
    """最长回撤持续时间（期数，日频为交易日数）。"""
    if len(equity) < 2:
        return 0
    running_max = equity.cummax()
    underwater = equity < running_max
    if not underwater.any():
        return 0
    max_len = cur = 0
    for flag in underwater:
        if flag:
            cur += 1
            max_len = max(max_len, cur)
        else:
            cur = 0
    return max_len


def calmar_ratio(equity: pd.Series, periods_per_year: int = TRADING_DAYS) -> float:
    """卡玛比率: 年化收益 / 最大回撤。"""
    mdd = max_drawdown(equity)
    if mdd == 0:
        return 0.0
    return annualized_return(equity, periods_per_year) / mdd


def skewness(equity: pd.Series) -> float:
    """收益偏度（负偏 = 尾部风险大）。"""
    r = _to_returns(equity)
    if len(r) < 3 or r.std(ddof=1) == 0:
        return 0.0
    return float(r.skew())


def kurtosis(equity: pd.Series) -> float:
    """收益超额峰度（>0 厚尾）。"""
    r = _to_returns(equity)
    if len(r) < 3:
        return 0.0
    return float(r.kurt())


def turnover_rate(equity: pd.Series, trades: list,
                  periods_per_year: int = TRADING_DAYS) -> float:
    """年化换手率: 年成交金额 / 平均资金规模。"""
    if not trades:
        return 0.0
    traded_amount = sum(abs(t.net_amount) for t in trades)
    avg_equity = float(equity.mean())
    if avg_equity == 0:
        return 0.0
    n_years = len(equity) / periods_per_year
    if n_years == 0:
        return 0.0
    return traded_amount / avg_equity / n_years


def win_rate(trades: list) -> float:
    """胜率: 盈利平仓次数 / 平仓总次数。"""
    closed = [t for t in trades if t.action == "SELL"]
    if not closed:
        return 0.0
    wins = sum(1 for t in closed if t.pnl and t.pnl > 0)
    return wins / len(closed)


def profit_factor(trades: list) -> float:
    """盈亏比（总盈利/总亏损），无亏损时返回 inf 表示完美。"""
    closed = [t for t in trades if t.action == "SELL" and t.pnl is not None]
    gross_win = sum(t.pnl for t in closed if t.pnl > 0)
    gross_loss = -sum(t.pnl for t in closed if t.pnl < 0)
    if gross_loss == 0:
        return float("inf") if gross_win > 0 else 0.0
    return gross_win / gross_loss


def avg_trade_pnl(trades: list) -> float:
    """平均每笔平仓盈亏（元）。"""
    closed = [t for t in trades if t.action == "SELL" and t.pnl is not None]
    if not closed:
        return 0.0
    return float(np.mean([t.pnl for t in closed]))


def alpha_beta_ir(
    equity: pd.Series, benchmark: pd.Series, rf: float = 0.0,
    periods_per_year: int = TRADING_DAYS,
) -> dict:
    """相对基准的超额指标: alpha(年化)、beta、信息比率 IR。

    benchmark 需与 equity 对齐（同一日期索引）。
    """
    if benchmark is None or len(benchmark) == 0:
        return {"alpha": 0.0, "beta": 0.0, "ir": 0.0}
    r = _to_returns(equity)
    rb = _to_returns(benchmark)
    joined = pd.concat([r, rb], axis=1, join="inner").dropna()
    if len(joined) < 20:
        return {"alpha": 0.0, "beta": 0.0, "ir": 0.0}
    rs, rbs = joined.iloc[:, 0], joined.iloc[:, 1]
    var_b = rbs.var(ddof=1)
    beta = float(rs.cov(rbs) / var_b) if var_b > 0 else 0.0
    alpha_daily = float(rs.mean() - rf / periods_per_year - beta * rbs.mean())
    alpha = alpha_daily * periods_per_year
    te = float((rs - rbs).std(ddof=1))
    ir = float((rs - rbs).mean() / te * np.sqrt(periods_per_year)) if te > 0 else 0.0
    return {"alpha": alpha, "beta": beta, "ir": ir}


def compute_metrics(
    equity: pd.Series,
    trades: list | None = None,
    benchmark: pd.Series | None = None,
    rf: float = 0.0,
    periods_per_year: int | None = None,
) -> dict:
    """完整指标套件。equity 为资金曲线（索引为日期）。

    periods_per_year: 年化频率（None = 从索引自动推断：日频 252 / 周频 52 / 月频 12）。
    """
    if periods_per_year is None:
        periods_per_year = infer_periods_per_year(equity.index)
    trades = trades or []
    m: dict = {
        "total_return": float(equity.iloc[-1] / equity.iloc[0] - 1) if len(equity) > 1 else 0.0,
        "annual_return": annualized_return(equity, periods_per_year),
        "annual_volatility": annualized_volatility(equity, periods_per_year),
        "sharpe": sharpe_ratio(equity, rf, periods_per_year),
        "sortino": sortino_ratio(equity, rf, periods_per_year),
        "calmar": calmar_ratio(equity, periods_per_year),
        "max_drawdown": max_drawdown(equity),
        "max_drawdown_duration": max_drawdown_duration(equity),
        "skewness": skewness(equity),
        "kurtosis": kurtosis(equity),
        "turnover": turnover_rate(equity, trades, periods_per_year),
        "win_rate": win_rate(trades),
        "profit_factor": profit_factor(trades),
        "avg_trade_pnl": avg_trade_pnl(trades),
        "trade_count": len([t for t in trades if t.action == "SELL"]),
        "periods_per_year": periods_per_year,
    }
    if benchmark is not None:
        m.update(alpha_beta_ir(equity, benchmark, rf, periods_per_year))
    return {k: (round(v, 6) if isinstance(v, float) else v) for k, v in m.items()}
