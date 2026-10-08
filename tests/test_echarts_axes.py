"""ECharts viewport autoscaling checks (no network access needed)."""
import unittest

import pandas as pd
import plotly.graph_objects as go

from macro_platform.echarts_axes import build_adaptive_echarts_option


class EchartsNativeAxes(unittest.TestCase):
    def test_one_month_uses_filtered_data_without_zero_floor(self):
        dates = pd.date_range("2021-10-01", "2026-10-01", freq="7D")
        vals = [0.7 if d.year < 2025 else 3.62 + ((i % 12) * 0.02)
                for i, d in enumerate(dates)]
        fig = go.Figure(data=[go.Scatter(x=dates, y=vals, mode="lines", name="IORB")])
        option = build_adaptive_echarts_option(fig, "1M")
        self.assertIsNotNone(option)
        self.assertEqual(option["yAxis"][0]["scale"], True)
        self.assertNotIn("min", option["yAxis"][0])
        self.assertNotIn("max", option["yAxis"][0])
        self.assertEqual(option["dataZoom"][0]["filterMode"], "filter")
        self.assertEqual(option["dataZoom"][1]["filterMode"], "filter")
        start = pd.Timestamp(option["dataZoom"][0]["startValue"])
        end = pd.Timestamp(option["dataZoom"][0]["endValue"])
        self.assertGreaterEqual((end-start).days, 27)
        self.assertLessEqual((end-start).days, 32)
        self.assertTrue(any(v[1] < 1.0 for v in option["series"][0]["data"]))
        self.assertEqual(option["toolbox"]["feature"]["dataZoom"]["yAxisIndex"], "none")

    def test_independent_right_axis(self):
        dates = pd.date_range("2026-09-01", periods=20, freq="D")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=dates, y=[3.8 + x/100 for x in range(20)], name="Left"))
        fig.add_trace(go.Scatter(x=dates, y=[200 + x for x in range(20)], name="Right", yaxis="y2"))
        fig.update_layout(yaxis2=dict(side="right", overlaying="y"))
        options = build_adaptive_echarts_option(fig, "1M")
        self.assertEqual(len(options["yAxis"]), 2)
        self.assertEqual(options["yAxis"][1]["position"], "right")
        self.assertTrue(options["yAxis"][1]["scale"])
        self.assertEqual(options["series"][1]["yAxisIndex"], 1)

    def test_no_observations(self):
        self.assertIsNone(build_adaptive_echarts_option(go.Figure(), "1M"))


if __name__ == "__main__":
    unittest.main()
