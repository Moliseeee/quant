"""Walk-Forward 滚动样本外验证 —— 防参数过拟合的核心工具。

原理:
    把时间轴切成 K 个连续窗口。每个窗口内:
        前 train_ratio 段 = 训练段（在这里挑参数）
        后 1-train_ratio 段 = 样本外测试段（只看这一段业绩）
    把 K 个测试段拼接成"纯样本外净值曲线"。

意义:
    如果策略只在训练段好、样本外崩掉 → 过拟合，参数被"挖"出来的。
    机构级策略必须以样本外业绩为准。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..backtest.engine import BacktestEngine


def walk_forward(
    df: pd.DataFrame,
    strategy_factory,
    engine: BacktestEngine,
    n_windows: int = 5,
    train_ratio: float = 0.6,
    param_grid: dict | None = None,
    verbose: bool = True,
) -> dict:
    """滚动样本外验证。

    Args:
        df: 规范化日线
        strategy_factory: callable(params) -> Strategy（用候选参数构造策略）
        engine: 回测引擎
        n_windows: 窗口数
        train_ratio: 每个窗口内训练段占比（0.6 = 前60%挑参，后40%测试）
        param_grid: 候选参数空间，如 {"fast": [3,5,10], "slow": [10,20,30]}
                    不传则用策略默认参数跑单次样本外

    Returns:
        {
            "out_of_sample_equity": 拼接的样本外净值曲线,
            "oas_metrics": 样本外指标,
            "windows": 每窗口详情,
            "best_params_per_window": 每窗口最优参数,
        }
    """
    dates = df.index
    n = len(dates)
    if n < n_windows * 20:
        raise ValueError("样本太短，无法做 walk-forward")

    # 窗口边界（等宽）
    edges = np.linspace(0, n, n_windows + 1, dtype=int)
    oos_parts: list[pd.Series] = []
    window_details = []
    best_params_list = []

    for w in range(n_windows):
        start, end = edges[w], edges[w + 1]
        split = start + int((end - start) * train_ratio)
        if end - split < 10:
            continue

        train_df = df.iloc[start:split]
        test_df = df.iloc[split:end]

        # ---- 训练段选参 ----
        best_params, best_score = None, -np.inf
        if param_grid:
            import itertools

            keys = list(param_grid.keys())
            for combo in itertools.product(*param_grid.values()):
                params = dict(zip(keys, combo))
                strat = strategy_factory(**params)
                sig = strat.generate_signal(train_df)
                res = engine.run(train_df, sig)
                score = res.metrics["sharpe"]
                if score > best_score:
                    best_score, best_params = score, params
        else:
            strat = strategy_factory()
            best_params = dict(getattr(strat, "params", {}))

        # ---- 测试段（样本外） ----
        strat = strategy_factory(**best_params) if best_params else strategy_factory()
        sig = strat.generate_signal(test_df)
        res = engine.run(test_df, sig)

        oos_parts.append(res.df["equity"])
        window_details.append({
            "window": w + 1,
            "train": f"{dates[start].date()}~{dates[split-1].date()}",
            "test": f"{dates[split].date()}~{dates[end-1].date()}",
            "best_params": best_params,
            "oas_sharpe": round(res.metrics["sharpe"], 3),
            "oas_return": round(res.metrics["total_return"], 4),
            "oas_max_dd": round(res.metrics["max_drawdown"], 4),
        })
        best_params_list.append(best_params)
        if verbose:
            d = window_details[-1]
            print(f"  [窗口{w+1}] train={d['train']} test={d['test']} "
                  f"params={best_params} sharpe={d['oas_sharpe']}")

    if not oos_parts:
        raise ValueError("walk-forward 无有效窗口")

    # 拼接样本外净值（相邻窗口首尾相连，缩放接续）
    oos_equity = pd.concat(oos_parts)
    # 去重（窗口边界可能重叠一个日期）并重新归一为"从1开始"
    oos_equity = oos_equity[~oos_equity.index.duplicated(keep="first")]
    oos_equity = oos_equity / oos_equity.iloc[0]

    from ..backtest.metrics import compute_metrics

    oas_metrics = compute_metrics(oos_equity)
    return {
        "out_of_sample_equity": oos_equity,
        "oas_metrics": oas_metrics,
        "windows": window_details,
        "best_params_per_window": best_params_list,
    }
