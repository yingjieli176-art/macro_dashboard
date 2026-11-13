"""30Y stays an observed nominal yield on the shared left axis."""
import ast
from pathlib import Path
import unittest

import pandas as pd
import plotly.graph_objects as go

from macro_platform.chart_axes import RANGE_OFFSETS
from macro_platform.echarts_axes import build_adaptive_echarts_option
from macro_platform.parameter_guide import compact_parameter_labels


def load_builder():
    source = Path(__file__).resolve().parents[1] / "app.py"
    names = {"build_fig3", "filter_range", "add_line", "_mark_missing_series"}
    nodes = [node for node in ast.parse(source.read_text()).body
             if isinstance(node, ast.FunctionDef) and node.name in names]
    ns = {"pd": pd, "go": go, "RANGE_OFFSETS": RANGE_OFFSETS,
          "chart_height": lambda *args: 420,
          "apply_chart_style": lambda fig, *args: fig}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), ns)
    return ns


class ThirtyYearTreasuryTests(unittest.TestCase):
    def setUp(self):
        self.ns = load_builder()
        self.dates = pd.to_datetime(["2024-10-01", "2026-09-30", "2026-10-01", "2026-10-28"])
        self.frames = {}
        self.ndx = pd.DataFrame(columns=["observation_date", "close"])
        self.ns["_load_yahoo_histories"] = lambda symbols: {"^NDX": self.ndx}
        for symbol, values in {"DGS3MO": [4., 4., 4., 4.],
                               "DGS2": [4.2, 4.2, 4.2, 4.2],
                               "DGS10": [4.5, 4.6, 4.7, 4.8],
                               "DGS30": [4.9, None, 5.1, 5.37]}.items():
            self.frames[symbol] = pd.DataFrame({"observation_date": self.dates, symbol: values})
            self.ns["get_" + symbol.lower()] = lambda symbol=symbol: self.frames[symbol].copy()

    def test_thirty_year_preserves_original_values_and_missing_observations(self):
        fig = self.ns["build_fig3"]("5Y")
        self.assertEqual([trace.name for trace in fig.data],
                         ["3M", "2Y", "10Y", "30Y", "10Y−2Y (R1)", "30Y−10Y (R1)"])
        thirty = next(trace for trace in fig.data if trace.name == "30Y")
        self.assertEqual(list(pd.to_datetime(thirty.x)), list(self.dates))
        self.assertEqual([thirty.y[i] for i in (0, 2, 3)], [4.9, 5.1, 5.37])
        self.assertTrue(pd.isna(thirty.y[1]))
        self.assertIn("%<extra>", thirty.hovertemplate)
        for period in RANGE_OFFSETS:
            option = build_adaptive_echarts_option(fig, period)
            observed = next(series for series in option["series"] if series["name"] == "30Y")
            self.assertEqual(observed["yAxisIndex"], 0)
            self.assertIsNone(observed["data"][1][1])
            self.assertFalse(observed["connectNulls"])
            self.assertTrue(option["yAxis"][0]["scale"])
            for name in ("10Y−2Y (R1)", "30Y−10Y (R1)"):
                spread = next(series for series in option["series"] if series["name"] == name)
                self.assertEqual(spread["yAxisIndex"], 1)

    def test_missing_thirty_year_does_not_synthesize_a_curve_or_hide_other_tenors(self):
        self.frames["DGS30"] = pd.DataFrame(columns=["observation_date", "DGS30"])
        fig = self.ns["build_fig3"]("5Y")
        self.assertEqual(fig.layout.meta["missing_series"], ["30Y", "30Y−10Y (R1)", "NASDAQ-100 (R2)"])
        self.assertEqual([trace.name for trace in fig.data],
                         ["3M", "2Y", "10Y", "10Y−2Y (R1)"])

    def test_long_end_spread_uses_same_day_yields_and_preserves_gaps(self):
        fig = self.ns["build_fig3"]("5Y")
        spread = next(trace for trace in fig.data if trace.name == "30Y−10Y (R1)")
        self.assertEqual(list(pd.to_datetime(spread.x)), list(self.dates))
        for index, expected in ((0, .4), (2, .4), (3, .57)):
            self.assertAlmostEqual(spread.y[index], expected)
        self.assertTrue(pd.isna(spread.y[1]))
        self.assertEqual(spread.yaxis, "y2")
        self.assertNotIn("10Y−3M (R1)", [trace.name for trace in fig.data])
        for period in RANGE_OFFSETS:
            option = build_adaptive_echarts_option(fig, period)
            item = next(series for series in option["series"] if series["name"] == spread.name)
            self.assertIsNone(item["data"][1][1])
            self.assertFalse(item["connectNulls"])
            self.assertEqual(item["yAxisIndex"], 1)

    def test_missing_ten_year_keeps_spread_missing_on_that_date(self):
        self.frames["DGS10"].loc[2, "DGS10"] = float("nan")
        fig = self.ns["build_fig3"]("5Y")
        spread = next(trace for trace in fig.data if trace.name == "30Y−10Y (R1)")
        self.assertTrue(pd.isna(spread.y[2]))

    def test_nasdaq_uses_original_closes_and_its_own_axis(self):
        dates = self.dates[[0, 2, 3]]
        prices = [19925.11, 24537.45, 25870.82]
        self.ndx = pd.DataFrame({"observation_date": dates, "close": prices})
        fig = self.ns["build_fig3"]("5Y")
        for period in RANGE_OFFSETS:
            option = build_adaptive_echarts_option(fig, period)
            index = option["series"][-1]
            self.assertEqual(index["name"], "NASDAQ-100 (R2)")
            self.assertEqual(index["yAxisIndex"], 2)
            self.assertEqual(index["data"], [[date.isoformat(), price] for date, price in zip(dates, prices)])
            self.assertIn("pts", option["yAxis"][2]["name"])
            self.assertEqual(compact_parameter_labels(option)[index["name"]], "NASDAQ-100（纳斯达克100）〔右轴2 · 指数点〕")

    def test_original_source_is_collected_and_included_in_chart_freshness_audit(self):
        from scripts.sync_fred_verified_cache import SERIES, TREASURY_FIELDS
        from scripts.probe_all_sources import jobs
        self.assertIn("DGS30", SERIES)
        self.assertEqual(TREASURY_FIELDS["DGS30"], "BC_30YEAR")
        source = next(row for row in jobs() if row[0] == "DGS30")
        self.assertEqual(source[1], [3])
        self.assertEqual(source[2], "daily")


if __name__ == "__main__":
    unittest.main()
