import unittest
from unittest.mock import patch

import pandas as pd
import plotly.graph_objects as go

from macro_platform.asia_rates import _add_trace, build_asia_rates_figure


class AsiaRatesTraceTests(unittest.TestCase):
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


    def test_final_figure_contains_all_six_rate_series(self):
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
            fig = build_asia_rates_figure("1Y")
        finally:
            asia_rates.load_china_gov_yields = old_china
            asia_rates.load_japan_gov_yields = old_japan

        names = [trace.name for trace in fig.data]
        self.assertEqual(
            names,
            [
                "China 2Y",
                "China 10Y",
                "China 10Y−2Y",
                "Japan 2Y",
                "Japan 10Y",
                "Japan 10Y−2Y",
            ],
        )
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
            fig = build_asia_rates_figure("1Y")

        spreads = [trace for trace in fig.data if trace.name == "Japan 10Y−2Y"]
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
