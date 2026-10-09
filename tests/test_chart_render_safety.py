"""Chart-level fault isolation: a failed renderer must not abort the dashboard."""
import ast
import logging
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import plotly.graph_objects as go


def _load_renderers():
    source = Path(__file__).resolve().parents[1] / "app.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    names = {"_render_adaptive_macro_figure", "_render_standard_macro_chart"}
    functions = [node for node in tree.body
                 if isinstance(node, ast.FunctionDef) and node.name in names]
    ns = {}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), "exec"), ns)
    return ns


class ChartRendererRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.ns = _load_renderers()
        self.fig = go.Figure(go.Scatter(x=["2026-09-01", "2026-09-02"], y=[4.1, 4.2]))
        self.option = {"xAxis": {"type": "time"}, "yAxis": [{"scale": True}]}
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
        self.ns.update({
            "_echarts_axes": SimpleNamespace(build_adaptive_echarts_option=self.adapter),
            "st": self.st,
            "DEFAULT_CHART_RANGE": "1Y",
            "CHART_BUILD": "test-smoke",
            "_prepare_chart_for_client_ranges": Mock(return_value=self.fig),
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


if __name__ == "__main__":
    unittest.main()
