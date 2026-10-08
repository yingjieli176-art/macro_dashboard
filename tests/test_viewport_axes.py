"""Regression tests for viewport-dependent Y autoscaling.

Run: python -m unittest discover -s tests -p 'test_viewport_axes.py'
"""
import unittest

import pandas as pd
import plotly.graph_objects as go

from macro_platform.chart_axes import (
    apply_server_time_window,
    apply_selected_x_viewport,
)


class ViewportAxisRegression(unittest.TestCase):
    def make_chart(self, secondary=False):
        dates = pd.date_range("2021-10-01", "2026-10-01", freq="7D")
        # Older observations are deliberately far outside the short-term band.
        vals = [0.8 if d.year < 2025 else 3.60 + 0.24 * (i % 13) / 12
                for i, d in enumerate(dates)]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=dates, y=vals, mode="lines", name="Primary"))
        if secondary:
            fig.add_trace(go.Scatter(
                x=dates, y=[100 if d.year < 2025 else 200 + (i % 10)
                            for i, d in enumerate(dates)],
                yaxis="y2", mode="lines", name="Secondary"))
            fig.update_layout(yaxis2=dict(overlaying="y", side="right"))
        return fig

    def test_one_month_y_does_not_include_zero(self):
        fig = apply_server_time_window(self.make_chart(), "1M")
        lo, hi = fig.layout.yaxis.range
        self.assertGreater(lo, 3.4)
        self.assertLess(hi, 4.1)
        self.assertFalse(fig.layout.yaxis.autorange)

    def test_five_year_range_is_wider(self):
        narrow = apply_server_time_window(self.make_chart(), "1M")
        wide = apply_server_time_window(self.make_chart(), "5Y")
        delta_narrow = narrow.layout.yaxis.range[1] - narrow.layout.yaxis.range[0]
        delta_wide = wide.layout.yaxis.range[1] - wide.layout.yaxis.range[0]
        self.assertGreater(delta_wide, delta_narrow * 5)

    def test_secondary_y_axis_is_independent(self):
        fig = apply_server_time_window(self.make_chart(secondary=True), "1M")
        self.assertGreater(fig.layout.yaxis.range[0], 3.4)
        self.assertGreater(fig.layout.yaxis2.range[0], 190)
        self.assertLess(fig.layout.yaxis2.range[1], 220)

    def test_mouse_box_recalculates_y_and_x(self):
        fig = apply_server_time_window(self.make_chart(), "5Y")
        fig = apply_selected_x_viewport(
            fig, {"x": ["2026-09-10", "2026-09-28"]}
        )
        lo, hi = fig.layout.yaxis.range
        self.assertGreater(lo, 3.4)
        self.assertLess(hi, 4.1)
        self.assertEqual(pd.Timestamp(fig.layout.xaxis.range[0]), pd.Timestamp("2026-09-10"))

    def test_empty_selection_keeps_existing_axes(self):
        fig = apply_server_time_window(self.make_chart(), "1M")
        before = tuple(fig.layout.yaxis.range)
        apply_selected_x_viewport(fig, {"x": []})
        self.assertEqual(tuple(fig.layout.yaxis.range), before)


if __name__ == "__main__":
    unittest.main()
