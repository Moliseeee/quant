"""情绪面板测试：T+1 无前视对齐、多股票交错、去重。"""

import pandas as pd
import pytest

from quant.data.sentiment import align_sentiment_to_weekly


class TestSentimentAlign:
    def _snap(self):
        return pd.DataFrame({
            "ts_code": ["600000.SH", "600000.SH", "000001.SZ"],
            "date_key": pd.to_datetime(["2023-08-31", "2024-05-01", "2023-06-16"]),
            "margin_balance": [100.0, 120.0, 300.0],
            "lhb_net": [5.0, 8.0, 12.0],
            "lhb_count": [1, 2, 3],
        })

    def test_before_data_is_nan(self):
        """数据 T+1 可用：截面在 date_key 之前必须 NaN。"""
        snap = self._snap()
        out = align_sentiment_to_weekly(snap, ["20230825"], universe=["600000.SH"])
        row = out["20230825"].iloc[0]
        assert pd.isna(row["margin_balance"]), "数据日前截面必须无情绪数据（前视！）"

    def test_after_data_available(self):
        snap = self._snap()
        out = align_sentiment_to_weekly(snap, ["20230901"], universe=["600000.SH"])
        assert out["20230901"].iloc[0]["margin_balance"] == pytest.approx(100.0)

    def test_same_date_uses_previous_week(self):
        """截面日期 == date_key（数据日+1）：数据 T 日盘后公布，T+1 起可用 → 截面可取。"""
        snap = self._snap()
        out = align_sentiment_to_weekly(snap, ["20230831"], universe=["600000.SH"])
        assert out["20230831"].iloc[0]["margin_balance"] == pytest.approx(100.0)

    def test_latest_wins_and_multi_stock(self):
        """最新一周快照保留（src_date 在 6 天窗口内）；更早快照=陈旧清理。"""
        snap = pd.DataFrame({
            "ts_code": ["600000.SH", "600000.SH", "000001.SZ"],
            "date_key": pd.to_datetime(["2023-08-26", "2024-05-04", "2023-06-17"]),
            "margin_balance": [100.0, 120.0, 300.0],
            "lhb_net": [5.0, 8.0, 12.0],
            "lhb_count": [1, 2, 3],
        })
        out = align_sentiment_to_weekly(snap, ["20240510"], universe=["600000.SH", "000001.SZ"])
        d = out["20240510"].set_index("ts_code")
        # 600000.SH: 最近快照 2024-05-04（6天窗口内）→ 保留最新值
        assert d.loc["600000.SH", "margin_balance"] == pytest.approx(120.0)
        assert d.loc["600000.SH", "lhb_count"] == 2
        # 000001.SZ: 仅有 2023 年旧快照 → 陈旧清理（margin NaN / lhb 0）
        assert pd.isna(d.loc["000001.SZ", "margin_balance"])
        assert d.loc["000001.SZ", "lhb_count"] == 0

    def test_stale_value_not_carried(self):
        """Codex 审查修复：未上榜/不在标的池的周，不得携带旧值（否则 rolling 重复累计）。
        股票 A 只有 2023-08-31 一次数据（date_key 2023-09-01），后续周截面必须为空/0。"""
        snap = pd.DataFrame({
            "ts_code": ["600000.SH"],
            "date_key": pd.to_datetime(["2023-09-01"]),
            "margin_balance": [100.0],
            "lhb_net": [5.0],
            "lhb_count": [1],
        })
        # 截面 20230901（数据日+1）：在 6 天窗口内 → 保留真实值
        out = align_sentiment_to_weekly(snap, ["20230901"], universe=["600000.SH"])
        assert out["20230901"].iloc[0]["margin_balance"] == pytest.approx(100.0)
        assert out["20230901"].iloc[0]["lhb_count"] == 1
        # 截面 20230908（一周后，无新数据）：margin→NaN（不在标的池），lhb→0（未上榜）
        out2 = align_sentiment_to_weekly(snap, ["20230908"], universe=["600000.SH"])
        row = out2["20230908"].iloc[0]
        assert pd.isna(row["margin_balance"]), "陈旧 margin 必须置 NaN"
        assert row["lhb_count"] == 0, "未上榜周 lhb_count 必须显式为 0（不能携带旧值）"
        assert row["lhb_net"] == 0
