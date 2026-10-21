import unittest
from unittest.mock import patch

import pandas as pd
import plotly.graph_objects as go

from macro_platform.asia_rates import _add_trace, build_china_rates_figure, build_japan_rates_figure
from macro_platform.chart_axes import RANGE_OFFSETS
from macro_platform.echarts_axes import build_adaptive_echarts_option


class AsiaRatesTraceTests(unittest.TestCase):
    def test_yen_index_has_independent_axis_and_original_calendar_in_all_windows(self):
        dates = pd.bdate_range("2021-10-01", "2026-10-20")
        japan = pd.DataFrame({"observation_date": dates, "japan_2y": 1.,
                              "japan_10y": 2., "japan_10y_2y_pct": 1.})
        nikkei = pd.DataFrame({"observation_date": dates, "close": 50000.})
        yen = pd.DataFrame({"observation_date": dates[::3], "jpy_neer": 69.21})
        with patch("macro_platform.asia_rates.load_japan_gov_yields", return_value=japan):
            for window, offset in RANGE_OFFSETS.items():
                fig = build_japan_rates_figure(window, nikkei, yen)
                expected = yen.loc[yen.observation_date >= dates.max() - offset]
                trace = fig.data[-1]
                self.assertEqual(trace.name, "JPY NEER · BIS (R3)")
                self.assertEqual(trace.yaxis, "y4")
                self.assertEqual(list(trace.x), list(expected.observation_date))
                self.assertEqual(list(trace.y), list(expected.jpy_neer))
                option = build_adaptive_echarts_option(fig, window)
                self.assertEqual(option["series"][-1]["yAxisIndex"], 3)
                self.assertEqual(len(option["yAxis"]), 4)
                self.assertFalse(option["yAxis"][3]["inverse"])
                self.assertIn("pts", option["yAxis"][3]["name"])

    def test_yen_feed_missing_does_not_remove_available_japan_series(self):
        index = pd.DataFrame({"observation_date": pd.to_datetime(["2026-10-20"]), "close": [50000.]})
        with patch("macro_platform.asia_rates.load_japan_gov_yields", side_effect=TimeoutError):
            fig = build_japan_rates_figure("1Y", index, pd.DataFrame())
        self.assertEqual([t.name for t in fig.data], ["Nikkei 225 (R2)"])
        self.assertIn("JPY NEER · BIS (R3)", fig.layout.meta["missing_series"])

    def test_country_overlays_keep_original_dates_values_and_units_in_all_windows(self):
        dates = pd.date_range("2021-10-01", "2026-10-09", freq="B")
        china = pd.DataFrame({"observation_date": dates, "china_2y": 1.4,
                              "china_10y": 2.0, "china_10y_2y_pct": .6})
        japan = pd.DataFrame({"observation_date": dates, "japan_2y": 1.,
                              "japan_10y": 2., "japan_10y_2y_pct": 999.})
        # Different publication calendars must not add null rows to other lines.
        real = pd.DataFrame({"observation_date": dates[::2], "DFII5": -0.4})
        nikkei = pd.DataFrame({"observation_date": dates[1::2], "close": 69030.92})
        with patch("macro_platform.asia_rates.load_china_gov_yields", return_value=china), \
             patch("macro_platform.asia_rates.load_japan_gov_yields", return_value=japan):
            for window, offset in RANGE_OFFSETS.items():
                with self.subTest(window=window):
                    china_fig = build_china_rates_figure(window, real)
                    japan_fig = build_japan_rates_figure(window, nikkei)
                    self.assertEqual(len(china_fig.data), 4)
                    self.assertEqual(len(japan_fig.data), 4)
                    self.assertFalse(any("Japan" in t.name or "Nikkei" in t.name for t in china_fig.data))
                    self.assertFalse(any("China" in t.name or "US 5Y" in t.name for t in japan_fig.data))
                    for fig, original, column, name in (
                        (china_fig, real, "DFII5", "US 5Y Real · TIPS"),
                        (japan_fig, nikkei, "close", "Nikkei 225 (R2)"),
                    ):
                        expected = original.loc[original.observation_date >= dates.max() - offset]
                        trace = next(t for t in fig.data if t.name == name)
                        self.assertEqual(list(pd.to_datetime(trace.x)), list(expected.observation_date))
                        self.assertEqual(list(trace.y), list(expected[column]))
                    self.assertEqual(japan_fig.data[-1].yaxis, "y3")
                    option = build_adaptive_echarts_option(japan_fig, window)
                    index = next(s for s in option["series"] if s["name"] == "Nikkei 225 (R2)")
                    self.assertEqual(index["yAxisIndex"], 2)
                    self.assertIn("pts", option["yAxis"][2]["name"])
                    self.assertIn("pp", option["yAxis"][1]["name"])

    def test_country_feed_failure_keeps_valid_overlay_and_does_not_fetch_other_country(self):
        real = pd.DataFrame({"observation_date": pd.to_datetime(["2026-10-08"]), "DFII5": [2.62]})
        index = real.rename(columns={"DFII5": "close"}).assign(close=69030.92)
        with patch("macro_platform.asia_rates.load_china_gov_yields", side_effect=TimeoutError), \
             patch("macro_platform.asia_rates.load_japan_gov_yields", side_effect=TimeoutError) as japan:
            fig = build_china_rates_figure("1Y", real)
            japan.assert_not_called()
            self.assertEqual([t.name for t in fig.data], ["US 5Y Real · TIPS"])
            fig = build_japan_rates_figure("1Y", index)
            self.assertEqual([t.name for t in fig.data], ["Nikkei 225 (R2)"])
            self.assertIn("Japan 2Y", fig.layout.meta["missing_series"])

    def test_null_calendar_rows_do_not_break_line(self):
        frame = pd.DataFrame(
            {
                "observation_date": pd.to_datetime(
                    ["2026-01-02", "2026-01-05", "2026-01-06"]
                ),
                "china_2y": [1.40, float("nan"), 1.42],
            }
        )
        fig = go.Figure()

        _add_trace(
            fig,
            frame,
            "china_2y",
            "China 2Y",
            width=2.1,
        )

        self.assertEqual(len(fig.data), 1)
        trace = fig.data[0]
        self.assertEqual(
            list(pd.to_datetime(trace.x)),
            list(pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06"])),
        )
        values = list(trace.y)
        self.assertEqual(values[0], 1.40)
        self.assertTrue(pd.isna(values[1]))
        self.assertEqual(values[2], 1.42)
        self.assertTrue(trace.connectgaps)


    def test_country_figures_are_separate_and_preserve_yield_spreads(self):
        import macro_platform.asia_rates as asia_rates

        china = pd.DataFrame(
            {
                "observation_date": pd.to_datetime(["2026-01-02", "2026-01-05"]),
                "china_2y": [1.40, 1.41],
                "china_10y": [1.85, 1.86],
                "china_10y_2y_pct": [0.45, 0.45],
            }
        )
        japan = pd.DataFrame(
            {
                "observation_date": pd.to_datetime(["2026-01-02", "2026-01-05"]),
                "japan_2y": [1.05, 1.06],
                "japan_10y": [1.95, 1.97],
                "japan_10y_2y_pct": [999.0, 999.0],
            }
        )

        old_china = asia_rates.load_china_gov_yields
        old_japan = asia_rates.load_japan_gov_yields
        try:
            asia_rates.load_china_gov_yields = lambda: china.copy()
            asia_rates.load_japan_gov_yields = lambda: japan.copy()
            china_fig = build_china_rates_figure("1Y")
            fig = build_japan_rates_figure("1Y")
        finally:
            asia_rates.load_china_gov_yields = old_china
            asia_rates.load_japan_gov_yields = old_japan

        names = [trace.name for trace in fig.data]
        self.assertEqual(
            names,
            [
                "Japan 2Y",
                "Japan 10Y",
                "Japan 10Y−2Y (R1)",
            ],
        )
        self.assertEqual([t.name for t in china_fig.data], ["China 2Y", "China 10Y", "China 10Y−2Y (R1)"])
        japan_spread = fig.data[-1]
        self.assertAlmostEqual(float(japan_spread.y[0]), 0.90, places=8)
        self.assertAlmostEqual(float(japan_spread.y[1]), 0.91, places=8)

    def test_duplicate_date_with_trailing_null_keeps_last_valid_value(self):
        frame = pd.DataFrame(
            {
                "observation_date": pd.to_datetime(
                    ["2026-01-02"] * 3 + ["2026-01-05", "2026-01-06"]
                ),
                "china_2y": [1.39, 1.40, float("nan"), float("nan"), 1.42],
            }
        )
        fig = go.Figure()

        _add_trace(fig, frame, "china_2y", "China 2Y", width=2.1)

        self.assertEqual(len(fig.data), 1)
        trace = fig.data[0]
        self.assertEqual(
            list(pd.to_datetime(trace.x)),
            list(pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06"])),
        )
        self.assertEqual(trace.y[0], 1.40)
        self.assertTrue(pd.isna(trace.y[1]))
        self.assertEqual(trace.y[2], 1.42)
        self.assertTrue(trace.connectgaps)

    def test_final_japan_spread_preserves_partial_missing_yields(self):
        dates = pd.to_datetime(
            ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07"]
        )
        japan = pd.DataFrame(
            {
                "observation_date": dates,
                "japan_2y": [1.05, float("nan"), 1.07, 1.08],
                "japan_10y": [1.95, 1.97, float("nan"), 2.01],
                "japan_10y_2y_pct": [999.0] * 4,
            }
        )

        with patch(
            "macro_platform.asia_rates.load_china_gov_yields",
            return_value=pd.DataFrame(),
        ), patch(
            "macro_platform.asia_rates.load_japan_gov_yields",
            return_value=japan.copy(),
        ):
            fig = build_japan_rates_figure("1Y")

        spreads = [trace for trace in fig.data if trace.name == "Japan 10Y−2Y (R1)"]
        self.assertEqual(len(spreads), 1)
        spread = spreads[0]
        self.assertEqual(list(pd.to_datetime(spread.x)), list(dates))
        self.assertAlmostEqual(float(spread.y[0]), 0.90, places=8)
        self.assertTrue(pd.isna(spread.y[1]))  # Missing 2Y.
        self.assertTrue(pd.isna(spread.y[2]))  # Missing 10Y.
        self.assertAlmostEqual(float(spread.y[3]), 0.93, places=8)
        self.assertTrue(spread.connectgaps)


if __name__ == "__main__":
    unittest.main()

