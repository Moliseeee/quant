"""策略失效归因测试（quant/research/attribution.py）。"""

import numpy as np
import pandas as pd
import pytest

from quant.research import build_factors, icir_trend, segment_factor_ic


def make_panels(n_dates: int = 12, n_stocks: int = 40, seed: int = 7):
    """合成面板：low_turnover 因子与未来收益正相关（构造有效因子）。"""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=n_dates, freq="W-FRI")
    stocks = [f"S{i:03d}" for i in range(n_stocks)]
    panels = {}
    for col in ["close", "adj_factor", "turnover_rate", "pb", "dv_ttm", "pe_ttm", "total_mv"]:
        panels[col] = pd.DataFrame(rng.uniform(1, 20, (n_dates, n_stocks)),
                                   index=dates, columns=stocks)
    # 让 low_turnover 因子（-turnover_rate）与未来收益正相关
    # 低换手股票未来涨更多 → fwd 与 turnover_rate 负相关
    panels["adj_factor"] = pd.DataFrame(1.0, index=dates, columns=stocks)
    close = panels["close"]
    for i in range(n_dates - 1):
        # 未来收益 = 常数 - 0.02 × turnover_rate（低换手 → 高收益）+ 噪声
        # （噪声打破完美相关，避免 IC 序列 std=0 使 ICIR 分母为 0）
        panels["close"].iloc[i + 1] = close.iloc[i] * (
            1.005 - 0.02 * panels["turnover_rate"].iloc[i]
            + rng.normal(0, 0.002, n_stocks))
    return panels


class TestBuildFactors:
    def test_direction(self):
        panels = make_panels()
        f = build_factors(panels)
        # 低换手 = -turnover_rate（值越小换手越高）
        assert f["low_turnover"].iloc[0, 0] == pytest.approx(-panels["turnover_rate"].iloc[0, 0])

    def test_ep_positive_only(self):
        panels = make_panels()
        panels["pe_ttm"].iloc[:, 0] = -5.0  # 亏损股
        f = build_factors(panels)
        assert np.isnan(f["ep"].iloc[:, 0]).all()  # 负 PE → NaN


class TestSegmentFactorIC:
    def test_effective_factor_positive_ic(self):
        panels = make_panels()
        df = segment_factor_ic(panels, [("全部", "2024-01-01", "2024-12-31")],
                               min_obs=20)  # 合成面板仅 40 只，min_obs 降低
        row = df[df["factor"] == "low_turnover"].iloc[0]
        assert row["raw_icir"] > 0.3  # 构造的有效因子 ICIR 显著为正

    def test_segments_rows(self):
        panels = make_panels(n_dates=24)
        segments = [("前段", "2024-01-01", "2024-06-30"), ("后段", "2024-07-01", "2024-12-31")]
        df = segment_factor_ic(panels, segments, min_obs=20)
        assert len(df) == len(FACTOR_NAMES) * 2  # 5 因子 × 2 段
        assert df["segment"].nunique() == 2


class TestIcIrTrend:
    def test_stable(self):
        df = pd.DataFrame({
            "factor": ["f"] * 3, "segment": ["a", "b", "c"],
            "raw_icir": [0.4, 0.35, 0.38],
        })
        assert "✅" in icir_trend(df)

    def test_decay(self):
        df = pd.DataFrame({
            "factor": ["f"] * 3, "segment": ["a", "b", "c"],
            "raw_icir": [0.4, 0.2, 0.05],
        })
        assert "⚠️" in icir_trend(df)


FACTOR_NAMES = ["low_turnover", "low_pb", "high_dividend", "ep", "small_mv"]
