"""Chart-level fault isolation: a failed renderer must not abort the dashboard."""
import ast
import logging
from copy import deepcopy
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import plotly.graph_objects as go
import pandas as pd
from macro_platform.chart_axes import RANGE_OFFSETS, apply_client_time_controls


def _load_renderers():
    source = Path(__file__).resolve().parents[1] / "app.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    names = {"_render_adaptive_macro_figure", "_render_standard_macro_chart",
             "_recoverable_echarts_option", "_viewport_scaled_plotly_fallback",
             "_show_macro_plot_health", "_show_data_quality_notes"}
    functions = [node for node in tree.body
                 if isinstance(node, ast.FunctionDef) and node.name in names]
    ns = {}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), "exec"), ns)
    return ns


class ChartRendererRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.ns = _load_renderers()
        self.fig = go.Figure(go.Scatter(x=["2026-09-01", "2026-09-02"], y=[4.1, 4.2]))
        self.option = {"xAxis": {"type": "time"}, "yAxis": [{"scale": True}],
                       "series": [{"name": "Sample", "data": [["2026-09-01", 4.1]]}],
                       "dataZoom": [{"startValue": "2026-08-02", "endValue": "2026-09-02",
                                     "filterMode": "filter"}]}
        self.adapter = Mock(return_value=self.option)
        self.st = SimpleNamespace(
            echarts_chart=Mock(),
            plotly_chart=Mock(),
            warning=Mock(),
            error=Mock(),
            caption=Mock(),
            markdown=Mock(),
            segmented_control=Mock(return_value="1Y"),
            query_params={},
        )
        self.st.session_state = {}
        self.ns.update({
            "go": go,
            "pd": pd,
            "deepcopy": deepcopy,
            "RANGE_OFFSETS": RANGE_OFFSETS,
            "_echarts_axes": SimpleNamespace(build_adaptive_echarts_option=self.adapter),
            "st": self.st,
            "DEFAULT_CHART_RANGE": "1Y",
            "RANGES": ["5Y", "1Y", "6M", "3M", "1M"],
            "CHART_BUILD": "test-smoke",
            "_prepare_chart_for_client_ranges": Mock(return_value=self.fig),
            "apply_client_time_controls": apply_client_time_controls,
            "apply_server_time_window": Mock(return_value=self.fig),
            "apply_time_axis": Mock(return_value=self.fig),
            "PLOTLY_CONFIG": {},
            "logging": logging,
            "show_parameter_description": Mock(),
            "add_sources": Mock(),
        })

    def _render_standard(self):
        self.ns["_render_standard_macro_chart"](
            "<b>Chart</b>", "Description", "test_chart", Mock(), [], 1, self.fig
        )

    def test_adaptive_chart_still_renders_when_echarts_throws(self):
        self.st.echarts_chart.side_effect = RuntimeError("echarts unavailable")
        self.ns["_render_adaptive_macro_figure"](self.fig, "hk_8_range", "Raw")
        self.st.plotly_chart.assert_called_once()
        self.st.error.assert_not_called()

    def test_adaptive_option_error_falls_back_without_stopping_page(self):
        self.adapter.side_effect = ValueError("unexpected Plotly axis configuration")
        self.ns["_render_adaptive_macro_figure"](self.fig, "copper_flow")
        self.st.plotly_chart.assert_called_once()
        self.st.error.assert_not_called()

    def test_two_broken_engines_show_inline_error_instead_of_crashing(self):
        self.st.echarts_chart.side_effect = RuntimeError("echarts unavailable")
        self.st.plotly_chart.side_effect = RuntimeError("plotly unavailable")
        self.ns["_render_adaptive_macro_figure"](self.fig, "asia_rates")
        self.st.error.assert_called_once()

    def test_standard_macro_option_failure_keeps_other_charts_alive(self):
        self.adapter.side_effect = ValueError("echarts option error")
        self._render_standard()
        self.st.plotly_chart.assert_called_once()
        self.ns["show_parameter_description"].assert_called_once_with(1)
        self.ns["add_sources"].assert_called_once_with([])

    def test_standard_macro_renderer_failure_recovers(self):
        self.st.echarts_chart.side_effect = RuntimeError("Cloud chart renderer error")
        self._render_standard()
        self.st.plotly_chart.assert_called_once()
        self.st.error.assert_not_called()

    def test_adaptive_success_does_not_use_fallback(self):
        self.ns["_render_adaptive_macro_figure"](self.fig, "hk_5_range")
        self.st.echarts_chart.assert_called_once()
        self.st.plotly_chart.assert_not_called()


    def test_after_1y_load_a_failed_1m_refresh_reuses_dynamic_view(self):
        # Recreates the screenshot: first chart works, time switch/rerun fails
        # to build options. The next render must remain ECharts, not Plotly.
        dates = pd.date_range("2025-10-08", "2026-10-08", freq="D")
        self.fig = go.Figure(go.Scatter(x=dates, y=[0.5 if d.year < 2026
                            else 3.7 + 0.01 * (i % 10)
                            for i, d in enumerate(dates)]))
        from macro_platform.echarts_axes import build_adaptive_echarts_option
        working_option = build_adaptive_echarts_option(self.fig, "1Y")
        self.assertIsNotNone(working_option)
        self.adapter.return_value = working_option

        self.ns["_render_standard_macro_chart"](
            "<b>Rates</b>", "Description", "fed_range", Mock(), [], 1, self.fig
        )
        self.assertEqual(self.st.echarts_chart.call_count, 1)
        self.assertEqual(self.st.plotly_chart.call_count, 0)

        self.st.segmented_control.return_value = "1M"
        self.adapter.side_effect = RuntimeError("temporary converter failure")
        self.ns["_render_standard_macro_chart"](
            "<b>Rates</b>", "Description", "fed_range", Mock(), [], 1, self.fig
        )
        self.assertEqual(self.st.echarts_chart.call_count, 2)
        self.st.plotly_chart.assert_not_called()
        recovered = self.st.echarts_chart.call_args.kwargs
        self.assertTrue(recovered["options"] if "options" in recovered else True)
        option = self.st.echarts_chart.call_args.args[0]
        start = pd.Timestamp(option["dataZoom"][0]["startValue"])
        latest = pd.Timestamp(option["dataZoom"][0]["endValue"])
        self.assertEqual(start, latest - pd.DateOffset(months=1))
        self.assertTrue(option["yAxis"][0]["scale"])
        self.assertTrue(all(zoom["filterMode"] == "filter" for zoom in option["dataZoom"]))

    def test_fallback_1m_y_does_not_inherit_five_year_zero_floor(self):
        dates = pd.date_range("2021-10-08", "2026-10-08", freq="7D")
        fig = go.Figure(go.Scatter(
            x=dates, y=[0.25 if d.year < 2025 else 3.7 + i % 7 * 0.015
                        for i, d in enumerate(dates)], name="Policy rate",
        ))
        self.adapter.side_effect = RuntimeError("temporarily broken")
        fallback = self.ns["_viewport_scaled_plotly_fallback"](fig, "1M")
        self.assertGreater(fallback.layout.yaxis.range[0], 3.4)
        self.assertLess(fallback.layout.yaxis.range[1], 4.2)
        self.assertEqual(
            [b.label for b in fallback.layout.updatemenus[0].buttons],
            ["5Y", "1Y", "6M", "3M", "1M"],
        )
        # A fallback remains an independently zoomable X/Y chart.
        self.assertFalse(fallback.layout.yaxis.fixedrange)

    def test_first_load_converter_error_uses_tight_plotly_fallback(self):
        self.adapter.side_effect = ValueError("converter exception")
        dates = pd.date_range("2021-10-08", "2026-10-08", freq="7D")
        fig = go.Figure(go.Scatter(
            x=dates, y=[0.25 if d.year < 2025 else 3.75
                        for d in dates], name="Policy rate",
        ))
        self.st.segmented_control.return_value = "1M"
        self.ns["_render_standard_macro_chart"](
            "<b>Rates</b>", "Description", "fed_range", Mock(), [], 1, fig
        )
        self.st.plotly_chart.assert_called_once()
        rendered = self.st.plotly_chart.call_args.args[0]
        self.assertGreater(rendered.layout.yaxis.range[0], 3.0)
        self.assertLess(rendered.layout.yaxis.range[1], 4.5)


    def test_every_adaptive_chart_gets_visible_five_range_buttons(self):
        for key in ("hk_5_range", "hk_6_range", "hk_7_range",
                    "hk_8_range", "us_equity_risk", "precious_metals",
                    "crypto_market", "copper_flow", "asia_rates"):
            with self.subTest(chart=key):
                self.st.segmented_control.reset_mock()
                self.ns["_render_adaptive_macro_figure"](self.fig, key)
                controls = self.st.segmented_control.call_args
                self.assertEqual(
                    controls.kwargs["options"], ["5Y", "1Y", "6M", "3M", "1M"]
                )
                self.assertEqual(controls.kwargs["key"], f"{key}_time_window")

    def test_hk_one_month_zoom_uses_same_month_on_both_engines(self):
        self.st.segmented_control.return_value = "1M"
        self.ns["_render_adaptive_macro_figure"](self.fig, "hk_5_range", "Raw")
        self.adapter.assert_called_with(self.fig, "1M")
        self.assertIn("_1M", self.st.echarts_chart.call_args.kwargs["key"])
        self.st.echarts_chart.side_effect = RuntimeError("adapter unavailable")
        self.ns["_render_adaptive_macro_figure"](self.fig, "hk_5_range", "Raw")
        self.st.plotly_chart.assert_called_once()
        fallback = self.st.plotly_chart.call_args.args[0]
        self.assertEqual(fallback.layout.xaxis.tickformat, "%m-%d")
        # The common external selector replaces the duplicate Plotly buttons.
        self.assertFalse(fallback.layout.updatemenus)

    def test_hk_cached_recovery_updates_month_window(self):
        from macro_platform.echarts_axes import build_adaptive_echarts_option
        dates = pd.date_range("2025-10-01", "2026-10-08", freq="7D")
        self.fig = go.Figure(go.Scatter(x=dates, y=[3 + 0.1 * (i % 4)
                                                  for i in range(len(dates))]))
        self.adapter.return_value = build_adaptive_echarts_option(self.fig, "1Y")
        self.ns["_render_adaptive_macro_figure"](self.fig, "hk_6_range")
        self.adapter.side_effect = ValueError("temporary adapter failure")
        self.st.segmented_control.return_value = "3M"
        self.ns["_render_adaptive_macro_figure"](self.fig, "hk_6_range")
        self.assertEqual(self.st.echarts_chart.call_count, 2)
        self.st.plotly_chart.assert_not_called()
        option = self.st.echarts_chart.call_args.args[0]
        zoom = option["dataZoom"][0]
        self.assertEqual(
            pd.Timestamp(zoom["startValue"]),
            pd.Timestamp(zoom["endValue"]) - pd.DateOffset(months=3)
        )
        self.assertEqual(option["xAxis"]["axisLabel"]["formatter"]["month"], "{yyyy}-{MM}")


if __name__ == "__main__":
    unittest.main()
