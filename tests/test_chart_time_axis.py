import unittest

import pandas as pd
import plotly.graph_objects as go

from macro_platform.chart_axes import apply_client_time_controls, apply_time_axis


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


    def test_client_controls_default_to_one_year(self):
        fig = apply_client_time_controls(self._figure(), default_range="1Y")
        start, end = [pd.Timestamp(value) for value in fig.layout.xaxis.range]

        self.assertEqual(start.normalize(), pd.Timestamp("2025-09-29"))
        self.assertGreaterEqual(end, pd.Timestamp("2026-09-29"))

    def test_client_controls_use_native_range_selector(self):
        fig = apply_client_time_controls(self._figure(), default_range="1Y")
        selector = fig.layout.xaxis.rangeselector
        labels = [button.label for button in selector.buttons]

        self.assertEqual(labels, ["5Y", "1Y", "6M", "3M", "1M"])
        self.assertTrue(selector.visible)
        self.assertEqual(len(fig.layout.updatemenus), 0)
        self.assertFalse(fig.layout.xaxis.fixedrange)
        self.assertEqual(fig.layout.xaxis.tickmode, "auto")

        three_month = selector.buttons[3]
        self.assertEqual(three_month.count, 3)
        self.assertEqual(three_month.step, "month")
        self.assertEqual(three_month.stepmode, "backward")
        self.assertEqual(selector.x, 0.0)
        self.assertEqual(selector.xanchor, "left")
        self.assertEqual(selector.y, 1.19)
        self.assertEqual(selector.borderwidth, 1)
        self.assertEqual(selector.activecolor, "#e7eefc")
        self.assertEqual(fig.layout.legend.y, 1.075)
        self.assertEqual(fig.layout.height, 440)
        self.assertEqual(fig.layout.margin.t, 106)
        self.assertEqual(fig.layout.margin.l, 62)
        self.assertEqual(fig.layout.margin.b, 38)

        year_shape_names = {
            getattr(shape, "name", None) for shape in (fig.layout.shapes or [])
        }
        self.assertNotIn("__dashboard_year_band__", year_shape_names)
        self.assertNotIn("__dashboard_year_divider__", year_shape_names)
        self.assertEqual(fig.layout.plot_bgcolor, "#ffffff")
        self.assertEqual(fig.layout.paper_bgcolor, "#ffffff")
        self.assertEqual(fig.layout.yaxis.gridcolor, "#e7edf3")
        self.assertEqual(fig.layout.xaxis.gridcolor, "#edf1f5")
        self.assertTrue(fig.layout.xaxis2.visible)
        self.assertEqual(fig.layout.xaxis2.matches, "x")
        self.assertEqual(fig.layout.xaxis2.overlaying, "x")
        self.assertEqual(fig.layout.xaxis2.side, "top")
        self.assertEqual(fig.layout.xaxis2.dtick, "M12")
        self.assertEqual(fig.layout.xaxis2.tickformat, "%Y")
        self.assertEqual(fig.layout.xaxis2.ticklabelmode, "period")



if __name__ == "__main__":
    unittest.main()
