"""Chart 4 keeps raw integer index closes and its three independent axes."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from macro_platform import sp500_nikkei_ratio as ratio


class Sp500NikkeiRatioTests(unittest.TestCase):
    def test_chart_uses_raw_integer_levels_and_three_independent_axes(self):
        dates = pd.to_datetime(["2026-10-28", "2026-10-29", "2026-10-30"])
        frame = pd.DataFrame({
            "observation_date": dates,
            "SP500": [6800, 6810, 6820],
            "NIKKEI": [51000, 51200, 51400],
            "ratio": [6800 / 51000, 6810 / 51200, 6820 / 51400],
        })
        with patch.object(ratio, "load_sp500_nikkei_ratio", return_value=frame):
            figure = ratio.build_sp500_nikkei_ratio_figure()
        self.assertEqual(len(figure.data), 3)
        self.assertEqual([trace.yaxis for trace in figure.data], ["y", "y2", "y3"])
        self.assertEqual(list(figure.data[0].y), frame.ratio.tolist())
        self.assertEqual(list(figure.data[1].y), frame.SP500.tolist())
        self.assertEqual(list(figure.data[2].y), frame.NIKKEI.tolist())
        self.assertEqual(figure.layout.yaxis.title.text, "指数点位比值（倍）")
        self.assertEqual(figure.layout.yaxis2.title.text, "标普500（点）")
        self.assertEqual(figure.layout.yaxis3.title.text, "日经225（点）")
        self.assertNotIn("rebased", str(figure.to_plotly_json()).lower())
        self.assertNotIn("起点=100", str(figure.to_plotly_json()))

    def test_last_good_snapshots_keep_chart_available_when_live_yahoo_is_offline(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            spx = root / "us_equity_daily.json"
            nikkei = root / "nikkei225_daily.json"
            spx.write_text(json.dumps({"series": {"SPX": {"records": [
                {"date": "2026-10-28", "close": 6800.4},
                {"date": "2026-10-29", "close": 6810.6},
            ]}}}))
            nikkei.write_text(json.dumps({"records": [
                {"date": "2026-10-28", "close": 51000},
                {"date": "2026-10-30", "close": 51400},
            ]}))
            ratio.load_sp500_nikkei_ratio.clear()
            with patch.object(ratio, "US_EQUITY_SNAPSHOT", spx), patch.object(ratio, "NIKKEI_SNAPSHOT", nikkei), patch.object(ratio, "_load_index", side_effect=TimeoutError("Yahoo offline")):
                frame = ratio.load_sp500_nikkei_ratio()
            self.assertEqual(frame.observation_date.dt.strftime("%Y-%m-%d").tolist(),
                             ["2026-10-28"])
            self.assertEqual(frame.SP500.tolist(), [6800])
            self.assertEqual(frame.NIKKEI.tolist(), [51000])
            ratio.load_sp500_nikkei_ratio.clear()

    def test_history_joins_only_common_dates_and_rounds_index_points(self):
        sp500 = pd.DataFrame({
            "observation_date": pd.to_datetime(["2026-10-28", "2026-10-29", "2026-10-30"]),
            "SP500": [6800.4, 6810.6, 6820.2],
        })
        nikkei = pd.DataFrame({
            "observation_date": pd.to_datetime(["2026-10-28", "2026-10-30"]),
            "NIKKEI": [51000.4, 51400.6],
        })
        ratio.load_sp500_nikkei_ratio.clear()
        empty_sp = pd.DataFrame(columns=["observation_date", "SP500"])
        empty_nk = pd.DataFrame(columns=["observation_date", "NIKKEI"])
        with patch.object(ratio, "_load_snapshot_index", side_effect=[empty_sp, empty_nk]), \
             patch.object(ratio, "_load_index", side_effect=[sp500, nikkei]):
            frame = ratio.load_sp500_nikkei_ratio()
        self.assertEqual(frame.observation_date.dt.strftime("%Y-%m-%d").tolist(),
                         ["2026-10-28", "2026-10-30"])
        self.assertEqual(frame.SP500.tolist(), [6800, 6820])
        self.assertEqual(frame.NIKKEI.tolist(), [51000, 51401])
        self.assertEqual(frame.ratio.tolist(), [6800 / 51000, 6820 / 51401])
        ratio.load_sp500_nikkei_ratio.clear()


if __name__ == "__main__":
    unittest.main()
