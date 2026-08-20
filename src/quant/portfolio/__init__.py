"""portfolio 子包：组合回测引擎 + 因子合成打分。"""

from .engine import PortfolioEngine, PortfolioResult
from .scoring import (
    FACTOR_BUILDERS,
    FINANCIAL_INDUSTRIES,
    composite_score,
    jaccard_similarity,
    top_n_weights,
    top_n_weights_industry_capped,
)

__all__ = [
    "PortfolioEngine",
    "PortfolioResult",
    "composite_score",
    "top_n_weights",
    "top_n_weights_industry_capped",
    "jaccard_similarity",
    "FACTOR_BUILDERS",
    "FINANCIAL_INDUSTRIES",
]
