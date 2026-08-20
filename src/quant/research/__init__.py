"""research 子包：样本外验证、失效归因等研究工具。"""

from .attribution import (
    FACTOR_DIRECTIONS,
    build_factors,
    icir_trend,
    neutralize_panel,
    segment_factor_ic,
)
from .walk_forward import walk_forward

__all__ = [
    "walk_forward",
    "segment_factor_ic",
    "build_factors",
    "neutralize_panel",
    "icir_trend",
    "FACTOR_DIRECTIONS",
]
