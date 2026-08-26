"""财务面板测试：ts_code 转换、无前视对齐（公告日 T+1 才可用）、多期取最近。"""

import pandas as pd
import pytest

from quant.data.financial import align_financial_to_weekly, to_ts_code


class TestToTsCode:
    def test_main_boards(self):
        assert to_ts_code("600000") == "600000.SH"
        assert to_ts_code("688837") == "688837.SH"
        assert to_ts_code("000001") == "000001.SZ"
        assert to_ts_code("300750") == "300750.SZ"

    def test_bj_and_b_share_rejected(self):
        assert to_ts_code("830799") == "830799.BJ"
        assert to_ts_code("900901") is None   # 沪B
        assert to_ts_code("200011") is None   # 深B


class TestAlignNoLookahead:
    """无前视铁律：财报公告日次日才可被截面使用。"""

    def _snap(self):
        return pd.DataFrame({
            "ts_code": ["600000.SH", "600000.SH"],
            "ann_date": pd.to_datetime(["2023-08-30", "2024-04-20"]),
            "roe": [10.0, 12.0],
            "report_date": ["20230630", "20231231"],
        })

    def test_before_announcement_is_nan(self):
        snap = self._snap()
        # 公告日 2023-08-30，次日 2023-08-31 才可用；08-25 截面必须 NaN
        out = align_financial_to_weekly(snap, ["20230825"], universe=["600000.SH"])
        row = out["20230825"].iloc[0]
        assert pd.isna(row["roe"]), "公告日前截面必须无财务数据（前视！）"

    def test_after_announcement_is_available(self):
        snap = self._snap()
        out = align_financial_to_weekly(snap, ["20230901"], universe=["600000.SH"])
        row = out["20230901"].iloc[0]
        assert row["roe"] == pytest.approx(10.0)

    def test_latest_report_wins(self):
        """多报告期时取公告日 ≤ 截面的最近一期。"""
        snap = self._snap()
        out = align_financial_to_weekly(snap, ["20240510"], universe=["600000.SH"])
        row = out["20240510"].iloc[0]
        assert row["roe"] == pytest.approx(12.0)
        assert row["report_date"] == "20231231"

    def test_universe_filter(self):
        """股票池外的股票不出现在输出。"""
        snap = self._snap()
        out = align_financial_to_weekly(snap, ["20230901"], universe=["000001.SZ"])
        assert len(out["20230901"]) == 1
        assert out["20230901"].iloc[0]["ts_code"] == "000001.SZ"
        assert pd.isna(out["20230901"].iloc[0]["roe"])

    def test_same_ann_date_dedup_keeps_latest_report(self):
        """年报+一季报同日公告（如 4-30）：去重保留最新报告期，merge_asof 不崩。"""
        snap = pd.DataFrame({
            "ts_code": ["600000.SH", "600000.SH"],
            "ann_date": pd.to_datetime(["2024-04-30", "2024-04-30"]),
            "roe": [10.0, 11.0],
            "report_date": ["20231231", "20240331"],
        })
        out = align_financial_to_weekly(snap, ["20240510"], universe=["600000.SH"])
        row = out["20240510"].iloc[0]
        assert row["roe"] == pytest.approx(11.0)
        assert row["report_date"] == "20240331"

    def test_multi_stock_mixed_dates(self):
        """多股票日期交错（全局非单调）：merge_asof 带 by 必须按 on 全局排序。"""
        snap = pd.DataFrame({
            "ts_code": ["600000.SH", "600000.SH", "000001.SZ"],
            "ann_date": pd.to_datetime(["2023-08-30", "2024-04-20", "2023-06-15"]),
            "roe": [10.0, 12.0, 20.0],
            "report_date": ["20230630", "20231231", "20230331"],
        })
        out = align_financial_to_weekly(snap, ["20230901"], universe=["600000.SH", "000001.SZ"])
        d = out["20230901"].set_index("ts_code")
        assert d.loc["600000.SH", "roe"] == pytest.approx(10.0)
        assert d.loc["000001.SZ", "roe"] == pytest.approx(20.0)
