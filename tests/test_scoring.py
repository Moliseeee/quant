"""组合选股打分逻辑测试（quant/portfolio/scoring.py）。"""

import numpy as np
import pandas as pd
import pytest

from quant.portfolio.scoring import (
    FINANCIAL_INDUSTRIES,
    composite_score,
    jaccard_similarity,
    top_n_weights,
    top_n_weights_industry_capped,
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


class TestIndustryCap:
    """行业上限约束（Kimi 审查 3.1：防组合变行业 β 策略）。"""

    def test_cap_limits_per_industry(self):
        """高分股同属一行业时，同一行业最多取 max_per_industry 只。"""
        scores = pd.Series({"A": 1.0, "B": 0.9, "C": 0.8, "D": 0.7, "E": 0.6})
        industry = pd.Series({"A": "银行", "B": "银行", "C": "银行", "D": "电气", "E": "化工"})
        w = top_n_weights_industry_capped(scores, top_n=4, industry_map=industry,
                                          max_per_industry=2)
        picked = set(w[w > 0].index)
        # 银行最多 2 只；电气/化工各 1 只
        assert len(picked) == 4
        banks = picked & {"A", "B", "C"}
        assert len(banks) == 2

    def test_cap_falls_back_to_next_best(self):
        """行业满额后顺延到次优股票。"""
        scores = pd.Series({"A": 1.0, "B": 0.9, "C": 0.8, "D": 0.1})
        industry = pd.Series({"A": "银行", "B": "银行", "C": "电气", "D": "化工"})
        w = top_n_weights_industry_capped(scores, top_n=3, industry_map=industry,
                                          max_per_industry=1)
        picked = set(w[w > 0].index)
        # 银行只能取 A（1 只），B 被跳过，D 补位
        assert "A" in picked and "B" not in picked and "D" in picked

    def test_unknown_industry_pass(self):
        """未知行业不占上限名额（放行），但已知行业仍受限制。"""
        scores = pd.Series({"A": 1.0, "B": 0.9, "C": 0.8})
        industry = pd.Series({"A": "银行", "B": None, "C": "银行"})
        w = top_n_weights_industry_capped(scores, top_n=3, industry_map=industry,
                                          max_per_industry=1)
        picked = set(w[w > 0].index)
        # B 无行业放行；C 受银行名额限制（A 已占）被跳过
        assert picked == {"A", "B"}


class TestJaccard:
    def test_basic(self):
        assert jaccard_similarity({"A", "B"}, {"B", "C"}) == pytest.approx(1 / 3)

    def test_identical(self):
        assert jaccard_similarity({"A", "B"}, {"A", "B"}) == pytest.approx(1.0)

    def test_disjoint(self):
        assert jaccard_similarity({"A"}, {"B"}) == 0.0

    def test_both_empty(self):
        assert jaccard_similarity(set(), set()) == 1.0
