"""情绪因子构造测试：变化率/取反/未上榜填0/滚动窗口。"""

import pandas as pd
import pytest

from quant.factors.emotion import build_emotion_factors, load_sentiment_panels


class TestEmotionFactors:
    def _write_panels(self, tmp_path):
        """构造 6 周 × 2 只股票的情绪截面。"""
        dates = ["20230106", "20230113", "20230120", "20230203", "20230210", "20230217"]
        margin = {"600000.SH": [100, 110, 105, 120, 115, 118],
                  "000001.SZ": [200, 210, 220, 230, 240, 250]}
        lhb_cnt = {"600000.SH": [1, 0, 2, 0, 1, 0],
                   "000001.SZ": [0, 0, 0, 1, 0, 0]}
        for i, d in enumerate(dates):
            df = pd.DataFrame({
                "ts_code": ["600000.SH", "000001.SZ"],
                "margin_balance": [margin["600000.SH"][i], margin["000001.SZ"][i]],
                "lhb_net": [10.0, 5.0],
                "lhb_count": [lhb_cnt["600000.SH"][i], lhb_cnt["000001.SZ"][i]],
            })
            df.to_parquet(tmp_path / f"{d}.parquet", index=False)

    def test_margin_chg_4w_sign_and_value(self, tmp_path):
        self._write_panels(tmp_path)
        f = build_emotion_factors(tmp_path)
        panel = f["neg_margin_chg_4w"]
        # 600000.SH: 第6周(118) vs 第2周(110): 变化率 118/110-1=0.0727 → 取反 -0.0727
        # 第5周(115) vs 第1周(100): 115/100-1=0.15 → 取反 -0.15
        assert panel.loc["20230217", "600000.SH"] == pytest.approx(-(118 / 110 - 1))
        assert panel.loc["20230210", "600000.SH"] == pytest.approx(-(115 / 100 - 1))
        # 前 4 周无足够历史 → NaN
        assert pd.isna(panel.loc["20230120", "600000.SH"])

    def test_neg_lhb_count_4w(self, tmp_path):
        self._write_panels(tmp_path)
        f = build_emotion_factors(tmp_path)
        panel = f["neg_lhb_count_4w"]
        # 600000.SH 前4周 [1,0,2,0] → sum=3 → 取反 -3；后4周 [0,2,0,1] → -3
        assert panel.loc["20230203", "600000.SH"] == pytest.approx(-3.0)
        # 000001.SZ 前4周 [0,0,0,1] → -1
        assert panel.loc["20230203", "000001.SZ"] == pytest.approx(-1.0)
        # 未上榜周 = 0（NaN 填 0 后求和），整列无 NaN（min_periods=2 已过）
        assert panel.loc["20230217"].notna().all()

    def test_direction_is_larger_better(self, tmp_path):
        """取反后语义：融资减仓/少上榜的股票得分更高。"""
        self._write_panels(tmp_path)
        f = build_emotion_factors(tmp_path)
        # 000001.SZ 融资持续增长（200→250）→ neg 更负；600000 波动 → neg 相对更高
        last = "20230217"
        assert f["neg_margin_chg_4w"].loc[last, "600000.SH"] > f["neg_margin_chg_4w"].loc[last, "000001.SZ"]
        # 600000 上榜 3 次 vs 000001 上榜 1 次 → neg_lhb 600000 更负
        assert f["neg_lhb_count_4w"].loc[last, "600000.SH"] < f["neg_lhb_count_4w"].loc[last, "000001.SZ"]
