"""Regression: show a single observed US 10Y TIPS yield without inventing observations."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import pandas as pd
import plotly.graph_objects as go

from macro_platform.chart_axes import RANGE_OFFSETS
from macro_platform.echarts_axes import build_adaptive_echarts_option


def load_figure_builder():
    root = Path(__file__).resolve().parents[1]
    source = root / "app.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    selected = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name in ("build_fig2", "filter_range", "add_line", "_mark_missing_series")
    ]
    ns = {"pd": pd, "go": go, "RANGE_OFFSETS": RANGE_OFFSETS}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(source), "exec"), ns)
    ns["chart_height"] = lambda compact, normal: normal
    ns["apply_chart_style"] = lambda fig, height, date_range: fig
    return ns


def sample(column, values, dates):
    return pd.DataFrame({
        "observation_date": pd.to_datetime(dates), column: values,
    })


class TenYearTIPSChartTests(unittest.TestCase):
    def setUp(self):
        self.ns = load_figure_builder()
        self.dates = ["2024-10-07", "2026-09-30", "2026-10-01", "2026-10-06"]
        self.data = {
            "DGS10": sample("DGS10", [4.0, 4.1, 4.2, 4.3], self.dates),
            "DFII10": sample("DFII10", [1.5, 1.6, None, 1.8], self.dates),
            "DFII5": sample("DFII5", [1.9, 2.73, None, 2.66], self.dates),
            "T10YIE": sample("T10YIE", [2.5, 2.5, 2.5, 2.5], self.dates),
        }
        self.ns.update({
            "get_dgs10": Mock(return_value=self.data["DGS10"]),
            "get_dfii10": Mock(return_value=self.data["DFII10"]),
            "get_dfii5": Mock(return_value=self.data["DFII5"]),
            "get_fred_series": Mock(return_value=self.data["T10YIE"]),
        })

    def test_ten_year_tips_is_observed_once_on_the_right_axis(self):
        fig = self.ns["build_fig2"]("5Y")
        self.assertEqual(len(fig.data), 3)
        tips = next(x for x in fig.data if x.name == "10Y Real · TIPS (R1)")
        self.assertEqual(tips.yaxis, "y2")
        self.assertEqual(list(tips.y[:2]), [1.5, 1.6])
        self.assertTrue(pd.isna(tips.y[2]))
        self.assertEqual(float(tips.y[3]), 1.8)
        self.ns["get_dfii5"].assert_not_called()
        self.ns["get_dfii10"].assert_called_once_with()
        self.ns["get_fred_series"].assert_called_once_with("T10YIE")

    def test_all_windows_keep_single_ten_year_observation_calendar(self):
        fig = self.ns["build_fig2"]("5Y")
        for period in ("5Y", "1Y", "6M", "3M", "1M"):
            option = build_adaptive_echarts_option(fig, period)
            tips = next(x for x in option["series"] if x["name"] == "10Y Real · TIPS (R1)")
            self.assertEqual(tips["yAxisIndex"], 1)
            self.assertEqual(len(tips["data"]), 4)
            self.assertIsNone(tips["data"][2][1])
            self.assertFalse(any("5Y" in x["name"] for x in option["series"]))

    def test_missing_dfii10_does_not_manufacture_real_yields(self):
        self.ns["get_dfii10"].return_value = sample("DFII10", [], [])
        fig = self.ns["build_fig2"]("5Y")
        self.assertEqual(len(fig.data), 2)
        self.assertIn("10Y Real · TIPS (R1)", fig.layout.meta["missing_series"])
        self.assertEqual([x.name for x in fig.data], ["10Y Nominal", "10Y Breakeven (R1)"])
        self.ns["get_dfii5"].assert_not_called()

    def test_chart_two_title_description_and_sources_use_ten_year_tips(self):
        source = (Path(__file__).resolve().parents[1] / "app.py").read_text()
        tree = ast.parse(source)
        render = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "render_macro_chart_2")
        text = ast.get_source_segment(source, render)
        self.assertIn("https://fred.stlouisfed.org/series/DFII10", text)
        self.assertNotIn("DFII5", text)
        self.assertNotIn("5Y", text)
        self.assertIn("US Treasury Yield Structure · 10Y", text)


if __name__ == "__main__":
    unittest.main()

