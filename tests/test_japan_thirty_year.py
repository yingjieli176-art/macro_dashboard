import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import pandas as pd

from macro_platform import asia_rates as rates
from macro_platform.chart_axes import RANGE_OFFSETS
from macro_platform.echarts_axes import build_adaptive_echarts_option
from scripts import update_japan_gov_yields as updater


class JapanThirtyYearTests(unittest.TestCase):
    def tearDown(self):
        rates.load_japan_gov_yields.clear()

    def test_official_csv_admits_thirty_year_and_only_same_date_valid_spreads(self):
        csv = "title\n基準日,2年,10年,30年\nR8.10.22,1,2,3.5\nR8.10.23,1,-,3.6\nR8.10.26,1,2.2,inf\n2099-01-01,1,2,3\n"
        with patch.object(rates, "http_get", return_value=Mock(content=csv.encode("cp932"))):
            frame = rates._read_japan_csv(rates.JAPAN_CURRENT_URL)
        self.assertEqual(frame.observation_date.dt.strftime("%Y-%m-%d").tolist(),
                         ["2026-10-22", "2026-10-23", "2026-10-26"])
        self.assertEqual(frame.japan_30y.iloc[0], 3.5)
        self.assertEqual(frame.japan_30y_10y_pct.iloc[0], 1.5)
        self.assertTrue(frame.japan_30y_10y_pct.iloc[1:].isna().all())
        self.assertTrue(pd.isna(frame.japan_30y.iloc[-1]))

    def test_legacy_snapshot_keeps_old_yields_and_triggers_official_history_backfill(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "japan.json"
            path.write_text(json.dumps({"records": [
                {"observation_date": "2021-01-04", "japan_2y": .1, "japan_10y": .5},
                {"observation_date": "2026-10-22", "japan_2y": 1, "japan_10y": 2}]}))
            history = pd.DataFrame({"observation_date": pd.to_datetime(["2026-10-22"]),
                                    "japan_2y": [None], "japan_10y": [None], "japan_30y": [3.5]})
            with patch.object(rates, "JAPAN_SNAPSHOT", path), patch.object(
                rates, "_read_japan_csv", side_effect=[TimeoutError(), history]
            ) as fetch:
                frame = rates.load_japan_gov_yields()
            self.assertEqual(fetch.call_args_list[-1].args, (rates.JAPAN_HISTORY_URL,))
            self.assertEqual(frame.japan_10y.iloc[-1], 2)
            self.assertEqual(frame.japan_30y.iloc[-1], 3.5)
            self.assertEqual(frame.japan_30y_10y_pct.iloc[-1], 1.5)

    def test_thirty_year_and_spread_keep_axes_values_and_calendars_in_every_window(self):
        dates = pd.bdate_range("2021-10-01", "2026-10-30")
        frame = pd.DataFrame({"observation_date": dates, "japan_2y": 1.,
                              "japan_10y": 2., "japan_30y": 3.5,
                              "japan_30y_10y_pct": 999.})
        frame.loc[frame.index[-2], "japan_10y"] = float("nan")
        with patch.object(rates, "load_japan_gov_yields", return_value=frame):
            for window, offset in RANGE_OFFSETS.items():
                fig = rates.build_japan_rates_figure(window)
                thirty = next(t for t in fig.data if t.name == "Japan 30Y")
                spread = next(t for t in fig.data if t.name == "Japan 30Y−10Y (R1)")
                self.assertEqual(list(thirty.x), list(dates[dates >= dates.max()-offset]))
                self.assertTrue(all(y == 3.5 for y in thirty.y))
                self.assertEqual(spread.y[-1], 1.5)
                self.assertTrue(pd.isna(spread.y[-2]))
                self.assertEqual(spread.yaxis, "y2")
                option = build_adaptive_echarts_option(fig, window)
                self.assertEqual(next(s for s in option["series"] if s["name"] == "Japan 30Y")["yAxisIndex"], 0)
                self.assertEqual(next(s for s in option["series"] if s["name"] == spread.name)["yAxisIndex"], 1)

    def test_collector_backfills_and_persists_original_thirty_year_fixings(self):
        dates = pd.bdate_range(end="2026-10-30", periods=1200)
        history = pd.DataFrame({"observation_date": dates, "japan_2y": 1.,
                                "japan_10y": 2., "japan_30y": 3.5})
        previous = history.assign(japan_30y=float("nan"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "japan.json"
            with patch.object(updater, "JAPAN_SNAPSHOT", path), patch.object(
                updater, "_read_japan_snapshot", return_value=previous
            ), patch.object(updater, "_read_japan_csv", side_effect=[history.tail(1), history]) as fetch:
                updater.main()
            self.assertEqual(fetch.call_args_list[-1].args, (rates.JAPAN_HISTORY_URL,))
            rows = json.loads(path.read_text())["records"]
            self.assertEqual(len(rows), 1200)
            self.assertTrue(all(row["japan_30y"] == 3.5 for row in rows))

    def test_collector_does_not_overwrite_last_good_when_thirty_year_is_absent(self):
        dates = pd.bdate_range(end="2026-10-30", periods=1200)
        history = pd.DataFrame({"observation_date": dates, "japan_2y": 1.,
                                "japan_10y": 2., "japan_30y": float("nan")})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "japan.json"
            path.write_text("last-good")
            with patch.object(updater, "JAPAN_SNAPSHOT", path), patch.object(
                updater, "_read_japan_snapshot", return_value=history
            ), patch.object(updater, "_read_japan_csv", return_value=history):
                with self.assertRaises(ValueError):
                    updater.main()
            self.assertEqual(path.read_text(), "last-good")
