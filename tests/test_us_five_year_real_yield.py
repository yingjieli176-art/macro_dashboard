"""Regression: show genuine US 5Y TIPS yield without inventing observations."""
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


class FiveYearTIPSChartTests(unittest.TestCase):
    def setUp(self):
        self.ns = load_figure_builder()
        self.dates = ["2024-10-07", "2026-09-30", "2026-10-01", "2026-10-06"]
        self.data = {
            "DGS10": sample("DGS10", [4.0, 4.1, 4.2, 4.3], self.dates),
            "DFII10": sample("DFII10", [1.5, 1.6, 1.7, 1.8], self.dates),
            "DFII5": sample("DFII5", [1.9, 2.73, None, 2.66], self.dates),
            "T10YIE": sample("T10YIE", [2.5, 2.5, 2.5, 2.5], self.dates),
        }
        self.ns.update({
            "get_dgs10": Mock(return_value=self.data["DGS10"]),
            "get_dfii10": Mock(return_value=self.data["DFII10"]),
            "get_dfii5": Mock(return_value=self.data["DFII5"]),
            "get_fred_series": Mock(return_value=self.data["T10YIE"]),
        })

    def test_real_five_year_tips_is_a_separate_dashed_right_axis(self):
        fig = self.ns["build_fig2"]("5Y")
        self.assertEqual(len(fig.data), 4)
        five = next(x for x in fig.data if x.name == "5Y Real · TIPS (R1)")
        self.assertEqual(five.yaxis, "y2")
        self.assertEqual(five.line.dash, "dash")
        self.assertEqual(list(five.y[:2]), [1.9, 2.73])
        self.assertTrue(pd.isna(five.y[2]))
        self.assertEqual(float(five.y[3]), 2.66)
        self.assertIn("Real yield", fig.layout.yaxis2.title.text)
        self.ns["get_dfii5"].assert_called_once_with()
        self.ns["get_fred_series"].assert_called_once_with("T10YIE")

    def test_both_short_and_long_windows_keep_five_year_real_yield(self):
        fig = self.ns["build_fig2"]("5Y")
        for period in ("5Y", "1Y", "3M", "1M"):
            with self.subTest(period=period):
                option = build_adaptive_echarts_option(fig, period)
                five = next(x for x in option["series"] if x["name"] == "5Y Real · TIPS (R1)")
                self.assertEqual(five["yAxisIndex"], 1)
                self.assertTrue(option["yAxis"][1]["scale"])
                self.assertTrue(all(zoom["filterMode"] == "filter" for zoom in option["dataZoom"]))
                self.assertEqual(len(five["data"]), 4)

    def test_missing_fred_dfii5_does_not_fabricate_data_or_break_other_lines(self):
        self.ns["get_dfii5"].return_value = sample("DFII5", [], [])
        fig = self.ns["build_fig2"]("5Y")
        self.assertEqual(len(fig.data), 3)
        self.assertIn("5Y Real · TIPS (R1)", fig.layout.meta["missing_series"])
        self.assertIn("10Y Real (R1)", [x.name for x in fig.data])
        self.assertIn("10Y Nominal", [x.name for x in fig.data])
        self.assertIn("10Y Breakeven (R1)", [x.name for x in fig.data])

    def test_chart_sources_and_label_point_to_dfii5(self):
        app = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
        data = (Path(__file__).resolve().parents[1] / "data.py").read_text(encoding="utf-8")
        self.assertIn("https://fred.stlouisfed.org/series/DFII5", app)
        self.assertIn('return _fred_series("DFII5")', data)
        self.assertIn("5Y Real TIPS (R1)", app)


if __name__ == "__main__":
    unittest.main()
