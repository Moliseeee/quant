"""factors 子包：因子预处理 + 有效性检验。"""

from .ic import forward_returns, ic_summary, quantile_analysis, rank_ic
from .processing import (
    adjusted_forward_return,
    ep_transform,
    neutralize,
    standard_factor_pipeline,
    winsorize,
    zscore,
)

__all__ = [
    "winsorize",
    "zscore",
    "neutralize",
    "standard_factor_pipeline",
    "ep_transform",
    "adjusted_forward_return",
    "forward_returns",
    "rank_ic",
    "ic_summary",
    "quantile_analysis",
]
