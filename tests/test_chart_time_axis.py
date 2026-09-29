import unittest

import pandas as pd
import plotly.graph_objects as go

from macro_platform.chart_axes import apply_time_axis


class ChartTimeAxisTests(unittest.TestCase):
    def _figure(self):
        dates = pd.date_range("2025-09-29", "2026-09-29", freq="D")
        return go.Figure(
            go.Scatter(
                x=dates,
                y=list(range(len(dates))),
                mode="lines",
            )
        )

    def test_three_month_range_is_three_months(self):
        fig = apply_time_axis(self._figure(), "3M")
        start, end = [pd.Timestamp(value) for value in fig.layout.xaxis.range]

        self.assertEqual(start.normalize(), pd.Timestamp("2026-06-29"))
        self.assertGreaterEqual(end, pd.Timestamp("2026-09-29"))
        self.assertLess(end, pd.Timestamp("2026-10-03"))

    def test_one_month_range_does_not_include_prior_year(self):
        fig = apply_time_axis(self._figure(), "1M")
        start, end = [pd.Timestamp(value) for value in fig.layout.xaxis.range]

        self.assertEqual(start.normalize(), pd.Timestamp("2026-08-29"))
        self.assertGreaterEqual(end, pd.Timestamp("2026-09-29"))
        self.assertEqual(start.year, 2026)

    def test_range_switch_changes_axis_start(self):
        one_year = apply_time_axis(self._figure(), "1Y")
        three_month = apply_time_axis(self._figure(), "3M")

        one_year_start = pd.Timestamp(one_year.layout.xaxis.range[0])
        three_month_start = pd.Timestamp(three_month.layout.xaxis.range[0])

        self.assertEqual(one_year_start.normalize(), pd.Timestamp("2025-09-29"))
        self.assertEqual(three_month_start.normalize(), pd.Timestamp("2026-06-29"))
        self.assertGreater(three_month_start, one_year_start)


if __name__ == "__main__":
    unittest.main()
