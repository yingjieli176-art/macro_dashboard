"""ECharts viewport autoscaling checks (no network access needed)."""
import unittest
import ast
import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from macro_platform.echarts_axes import build_adaptive_echarts_option, summarize_series_dates, expected_viewport_y_bounds


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

    def test_all_standard_us_charts_use_same_responsive_renderer(self):
        source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        renderer = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "_render_standard_macro_chart"
        )
        calls = [
            node.func.attr for node in ast.walk(renderer)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        ]
        self.assertIn("echarts_chart", calls)
        # The legacy Plotly call is now an intentional fail-open fallback when
        # Streamlit Cloud deploys app.py before its optional chart adapter.
        self.assertIn("plotly_chart", calls)
        self.assertIn('builder is None', ast.get_source_segment(source, renderer))
        self.assertNotIn('range_key == "normal_corridor_range"', ast.get_source_segment(source, renderer))
        for chart_no in range(1, 5):
            chart_name = f"render_macro_chart_{chart_no}"
            render_method = next(
                node for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name == chart_name
            )
            self.assertTrue(any(
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id == "_render_standard_macro_chart"
                for call in ast.walk(render_method)
            ))

    def test_exact_month_viewport_y_bounds_exclude_five_year_extremes(self):
        dates = pd.date_range("2021-10-01", "2026-10-01", freq="7D")
        fig = go.Figure(data=[go.Scatter(
            x=dates,
            y=[0.6 if d.year < 2025 else 3.65 + (i % 7) * 0.02
               for i, d in enumerate(dates)],
            name="Treasury"
        )])
        recent = expected_viewport_y_bounds(fig, "1M")["yaxis"]
        long = expected_viewport_y_bounds(fig, "5Y")["yaxis"]
        self.assertGreater(recent[0], 3.5)
        self.assertLess(recent[1], 3.9)
        self.assertLess(long[0], 1)
        self.assertGreater(long[1] - long[0], recent[1] - recent[0])

    def test_echarts_chart_options_are_json_serializable(self):
        dates = pd.date_range("2026-09-01", periods=25, freq="D")
        fig = go.Figure([go.Scatter(x=dates, y=[3.75 + i / 500 for i in range(25)])])
        config = build_adaptive_echarts_option(fig, "1M")
        json.dumps(config, allow_nan=False)
        self.assertTrue(all(axis.get("scale") is True for axis in config["yAxis"]))
        self.assertEqual(config["yAxis"][0]["boundaryGap"], ["7%", "7%"])

    def test_optional_adapter_import_does_not_crash_app_at_startup(self):
        source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        # Importing new helper names unconditionally was the startup ImportError.
        self.assertFalse(any(
            isinstance(node, ast.ImportFrom)
            and node.module == "macro_platform.echarts_axes"
            for node in ast.walk(tree)
        ))
        # The guard must run before any chart/page rendering.
        guarded = [node for node in tree.body if isinstance(node, ast.Try)
                   and any(isinstance(child, ast.Import)
                           and any(alias.name == "macro_platform.echarts_axes"
                                   for alias in child.names)
                           for child in node.body)]
        self.assertTrue(guarded)
        self.assertTrue(any(
            isinstance(handler.type, (ast.Tuple, ast.Name))
            for handler in guarded[0].handlers
        ))

    def test_no_observations(self):
        self.assertIsNone(build_adaptive_echarts_option(go.Figure(), "1M"))

    def test_curve_primary_and_spreads_use_independent_scales(self):
        dates = pd.date_range("2026-04-01", periods=28, freq="7D")
        fig = go.Figure()
        nominal = [4.9 + i * 0.01 for i in range(28)]
        two_year = [4.5 + i * 0.007 for i in range(28)]
        fig.add_trace(go.Scatter(x=dates, y=nominal, name="10Y"))
        fig.add_trace(go.Scatter(x=dates, y=two_year, name="2Y"))
        fig.add_trace(go.Scatter(
            x=dates, y=[a-b for a,b in zip(nominal, two_year)],
            yaxis="y2", name="10Y−2Y (R1)"
        ))
        fig.update_layout(yaxis2=dict(overlaying="y", side="right"))
        opts = build_adaptive_echarts_option(fig, "6M")
        self.assertEqual(opts["series"][2]["yAxisIndex"], 1)
        self.assertEqual(len(opts["yAxis"]), 2)
        self.assertTrue(all(ax["scale"] for ax in opts["yAxis"]))
        self.assertTrue(all(dz["filterMode"] == "filter" for dz in opts["dataZoom"]))

    def test_observation_dates_and_stale_warning(self):
        dates = ["2026-10-01", "2026-10-02"]
        fig = go.Figure(data=[go.Scatter(x=dates, y=[4.2, 4.3], name="2Y")])
        result = summarize_series_dates(
            fig, now=pd.Timestamp("2026-10-15"), maximum_age_days=7
        )
        self.assertEqual(result["latest_by_name"]["2Y"], "2026-10-02")
        self.assertEqual(result["stale_names"], ["2Y"])
        self.assertEqual(result["future_names"], [])


if __name__ == "__main__":
    unittest.main()
