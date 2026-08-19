"""因子处理与 IC 检验测试。"""

import numpy as np
import pandas as pd
import pytest

from quant.factors.ic import ic_summary, quantile_analysis, rank_ic
from quant.factors.processing import neutralize, standard_factor_pipeline, winsorize, zscore


class TestWinsorize:
    def test_mad_clips_outliers(self):
        s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 1000.0])
        out = winsorize(s)
        assert out.max() < 1000.0
        assert out.iloc[:-1].equals(pd.Series([1.0, 2.0, 3.0, 4.0, 5.0], index=range(5), dtype=float))

    def test_quantile_method(self):
        s = pd.Series(np.arange(100, dtype=float))
        out = winsorize(s, method="quantile")
        assert out.min() >= 0.99 and out.max() <= 99.01


class TestZScore:
    def test_mean_zero_std_one(self):
        s = pd.Series(np.arange(10, dtype=float) * 2 + 5)
        z = zscore(s)
        assert z.mean() == pytest.approx(0.0, abs=1e-9)
        assert z.std(ddof=0) == pytest.approx(1.0, abs=1e-9)


class TestNeutralize:
    def test_industry_effect_removed(self):
        """构造与行业强相关的因子，中性化后行业差异应消失。"""
        rng = np.random.default_rng(0)
        n = 200
        industry = np.where(np.arange(n) % 2 == 0, "A", "B")
        factor = pd.Series(np.where(industry == "A", 50.0, -50.0) + rng.normal(0, 1, n))
        mv = pd.Series(rng.uniform(10, 100, n))
        df = pd.DataFrame({"factor": factor, "industry": industry, "total_mv": mv})
        out = neutralize(df, "factor")
        resid = out.dropna()
        valid = df.loc[resid.index]
        # 中性化后 A/B 两组残差均值应接近 0（无显著行业差异）
        grp_a = resid[valid["industry"] == "A"]
        grp_b = resid[valid["industry"] == "B"]
        assert abs(grp_a.mean()) < 0.5
        assert abs(grp_b.mean()) < 0.5
        # 原始因子两组差异很大
        assert abs(factor[industry == "A"].mean() - factor[industry == "B"].mean()) > 50


class TestRankIC:
    def test_perfect_positive_factor(self):
        """因子与未来收益完全正相关 -> IC ≈ 1。"""
        rng = np.random.default_rng(1)
        dates = pd.bdate_range("2024-01-01", periods=10)
        stocks = [f"S{i}" for i in range(50)]
        factor = pd.DataFrame(rng.normal(0, 1, (10, 50)), index=dates, columns=stocks)
        fwd = factor * 0.01 + rng.normal(0, 1e-6, (10, 50))  # 近乎完美正相关
        ic = rank_ic(factor, fwd, min_obs=20)
        assert len(ic) == 10
        assert ic.mean() > 0.9

    def test_zero_factor_no_predictive_power(self):
        rng = np.random.default_rng(2)
        dates = pd.bdate_range("2024-01-01", periods=10)
        stocks = [f"S{i}" for i in range(50)]
        factor = pd.DataFrame(rng.normal(0, 1, (10, 50)), index=dates, columns=stocks)
        fwd = pd.DataFrame(rng.normal(0, 1, (10, 50)), index=dates, columns=stocks)  # 独立
        ic = rank_ic(factor, fwd, min_obs=20)
        assert abs(ic.mean()) < 0.3  # 随机因子 IC 接近 0

    def test_ic_summary_keys(self):
        ic = pd.Series(np.full(30, 0.05))
        s = ic_summary(ic)
        assert s["mean_ic"] == pytest.approx(0.05)
        assert s["positive_ratio"] == 1.0
        assert s["n_days"] == 30


class TestQuantileAnalysis:
    def test_monotonic_returns(self):
        """因子越大未来收益越高 -> 分组均值应单调递增。"""
        rng = np.random.default_rng(3)
        dates = pd.bdate_range("2024-01-01", periods=8)
        stocks = [f"S{i}" for i in range(100)]
        factor = pd.DataFrame(rng.normal(0, 1, (8, 100)), index=dates, columns=stocks)
        fwd = factor * 0.005 + rng.normal(0, 0.001, (8, 100))
        q = quantile_analysis(factor, fwd, n_quantiles=5)
        assert not q.empty
        # 最高组均值收益 > 最低组
        assert q.loc[4, "mean_ret"] > q.loc[0, "mean_ret"]
        assert q.loc["LS_long_short", "mean_ret"] > 0
