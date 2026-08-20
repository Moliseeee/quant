"""组合选股打分逻辑测试（quant/portfolio/scoring.py）。"""

import numpy as np
import pandas as pd
import pytest

from quant.portfolio.scoring import (
    FINANCIAL_INDUSTRIES,
    composite_score,
    jaccard_similarity,
    top_n_weights,
)

WEIGHTS = {"low_turnover": 0.50, "low_pb": 0.30, "high_dividend": 0.20}


def make_cross() -> pd.DataFrame:
    """合成截面：A 低换手低PB高股息（应高分），B 高换手高PB低股息（应低分），C 金融股。"""
    return pd.DataFrame({
        "low_turnover": [0.5, 10.0, 3.0],     # 换手率（越低越好）
        "low_pb": [1.0, 5.0, 2.0],            # PB（越低越好）
        "high_dividend": [0.05, 0.005, 0.02], # 股息率（越高越好）
        "low_ps": [1.0, 2.0, 3.0],
        "close": [10.0, 20.0, 30.0],
    }, index=["A", "B", "C"])


class TestCompositeScore:
    def test_direction_correct(self):
        cross = make_cross()
        score = composite_score(cross, WEIGHTS)
        # A（低换手/低PB/高股息）得分应最高，B 最低
        assert score["A"] > score["C"] > score["B"]

    def test_financial_ps_neutralized(self):
        """金融股 PS 因子置中性：PS 好坏不影响金融股得分。"""
        cross = make_cross()
        industry = pd.Series({"A": "电气设备", "B": "化工原料", "C": "银行"})
        # 银行 C 的 PS 应被中性化（low_ps 列不参与）
        w_ps = {"low_ps": 1.0}  # 只看 PS
        score = composite_score(cross, w_ps, industry)
        assert score["C"] == pytest.approx(0.0)  # 中性 → 0 贡献
        # 非金融股正常参与（A 的 PS 未置中性）
        assert score["A"] != 0.0

    def test_eps_included(self):
        """E/P 因子：亏损股（负 PE）不参与排序。"""
        cross = pd.DataFrame({
            "ep": [10.0, -5.0, 20.0],  # pe_ttm 原始值
        }, index=["A", "B", "C"])
        score = composite_score(cross, {"ep": 1.0})
        # A(pe=10) 比 C(pe=20) 便宜 → E/P 更高 → 得分更高
        assert score["A"] > score["C"]


class TestTopNWeights:
    def test_equal_weight_top_n(self):
        scores = pd.Series({"A": 1.0, "B": 0.5, "C": 0.2, "D": 0.1})
        w = top_n_weights(scores, top_n=2)
        assert w["A"] == pytest.approx(0.5) and w["B"] == pytest.approx(0.5)
        assert w["C"] == 0.0 and w["D"] == 0.0

    def test_nan_excluded(self):
        scores = pd.Series({"A": np.nan, "B": 1.0, "C": 0.5})
        w = top_n_weights(scores, top_n=2)
        assert "A" not in w or w["A"] == 0.0
        assert w["B"] == pytest.approx(0.5) and w["C"] == pytest.approx(0.5)

    def test_universe_filter(self):
        scores = pd.Series({"A": 1.0, "B": 0.5, "C": 0.2})
        w = top_n_weights(scores, top_n=1, universe=pd.Index(["B", "C"]))
        assert w["B"] == pytest.approx(1.0)
        assert "A" not in w  # A 被 universe 过滤，不在结果中


class TestJaccard:
    def test_basic(self):
        assert jaccard_similarity({"A", "B"}, {"B", "C"}) == pytest.approx(1 / 3)

    def test_identical(self):
        assert jaccard_similarity({"A", "B"}, {"A", "B"}) == pytest.approx(1.0)

    def test_disjoint(self):
        assert jaccard_similarity({"A"}, {"B"}) == 0.0

    def test_both_empty(self):
        assert jaccard_similarity(set(), set()) == 1.0
