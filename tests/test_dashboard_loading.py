"""Test loading helpers without running the dashboard's top-level network I/O."""
import ast
import uuid
from macro_platform.request_runtime import submit_jobs, completed_jobs, observed_cache, IncompleteObservedBundle
import logging
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from macro_platform.chart_axes import apply_client_time_controls


HELPERS = {
    "_fetch_quote_rows", "_apply_watchlist_quote_rows", "_empty_quote", "_load_market_quotes", "_load_yahoo_histories",
    "_prepare_chart_for_client_ranges", "_macro_snapshot_revision",
    "_cached_macro_figure", "_cached_hk_bundle", "_safe_macro_build",
    "_safe_hk_bundle", "_macro_error_figure", "_build_macro_figures_parallel",
    "_figure_has_real_observations",
    "_cache_safe_figure",
}


def load_helpers():
    source = Path(__file__).resolve().parents[1] / "app.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in HELPERS]
    constants = [node for node in tree.body if isinstance(node, ast.Assign)
                 and any(isinstance(target, ast.Name) and target.id in {"DEFAULT_CHART_RANGE", "CHART_BUILD", "MARKET_SYMBOLS"} for target in node.targets)]
    namespace = {
        "__file__": str(source), "st": st, "pd": pd, "go": go,
        "logging": logging, "uuid": uuid,
        "math": math, "IncompleteObservedBundle": IncompleteObservedBundle,
        "Path": Path, "ThreadPoolExecutor": ThreadPoolExecutor,
        "as_completed": as_completed, "apply_client_time_controls": apply_client_time_controls,
    }
    namespace.update({"observed_cache": observed_cache, "submit_jobs": submit_jobs, "completed_jobs": completed_jobs,
                      "_quote_refresh_key": lambda: 0})
    exec(compile(ast.Module(body=constants + selected, type_ignores=[]), str(source), "exec"), namespace)
    return namespace


class DashboardLoadingTests(unittest.TestCase):
    def setUp(self):
        self.ns = load_helpers()
        self.ns["_cached_macro_figure"].clear()
        self.ns["_cached_hk_bundle"].clear()
        st.session_state.clear()
        dates = pd.to_datetime(["2021-09-29", "2025-09-29", "2026-09-29"])
        self.figure = go.Figure(go.Scatter(x=dates, y=[100, 110, 120], name="full history"))
        for number in (1, 2, 3, 4, 9, 10, 11, 12):
            self.ns[f"build_fig{number}"] = Mock(side_effect=lambda *args: go.Figure(self.figure))
        self.ns["build_asia_rates_figure"] = Mock(side_effect=lambda *args: go.Figure(self.figure))
        self.ns["build_fig5"] = Mock(side_effect=lambda *args, **kwargs: [go.Figure(self.figure) for _ in range(4)])
        self.ns["build_hk_core_snapshot_figures"] = Mock(
            side_effect=lambda *args: (go.Figure(self.figure), go.Figure(self.figure))
        )

    def tearDown(self):
        self.ns["_cached_macro_figure"].clear()
        self.ns["_cached_hk_bundle"].clear()
        st.session_state.clear()

    def test_one_year_view_preserves_five_year_data_and_all_controls(self):
        figure = self.ns["_prepare_chart_for_client_ranges"](go.Figure(self.figure), "test-chart")
        start, end = map(pd.Timestamp, figure.layout.xaxis.range)
        self.assertEqual(start, pd.Timestamp("2025-09-29"))
        # The chart intentionally extends X by a small right-hand date margin.
        # Test the observation viewport, not an obsolete exact-axis endpoint.
        self.assertGreaterEqual(end, pd.Timestamp("2026-09-29"))
        self.assertLessEqual(end, pd.Timestamp("2026-10-06"))
        self.assertEqual(len(figure.data[0].x), 3)
        self.assertEqual(pd.Timestamp(figure.data[0].x[0]), pd.Timestamp("2021-09-29"))
        # The current fallback uses relayout buttons to rescale both X and Y;
        # the old Plotly range selector would change X only.
        buttons = figure.layout.updatemenus[0].buttons
        self.assertEqual([button.label.strip() for button in buttons], ["5Y", "1Y", "6M", "3M", "1M"])
        self.assertEqual([button.method for button in buttons], ["relayout"] * 5)
        self.assertFalse(figure.layout.xaxis.rangeselector.visible)
        self.assertNotEqual(figure.layout.uirevision, "test-chart:client-range")

    def test_unchanged_charts_are_reused_and_cached_figures_are_isolated(self):
        first = self.ns["_build_macro_figures_parallel"]()
        self.assertEqual(set(first), set(range(1, 14)))
        first[1].data[0].name = "modified by renderer"
        second = self.ns["_build_macro_figures_parallel"]()
        self.assertEqual(second[1].data[0].name, "full history")
        for number in (1, 2, 3, 4, 9, 10, 11, 12):
            self.ns[f"build_fig{number}"].assert_called_once()
        self.ns["build_asia_rates_figure"].assert_called_once()
        self.ns["build_fig5"].assert_called_once_with("5Y")

    def test_legacy_market_mode_state_cannot_change_raw_charts_or_duplicate_cache(self):
        self.ns["_build_macro_figures_parallel"]()
        for key in ("precious_metals_mode", "crypto_market_mode", "hk_5_range_market_mode", "hk_8_range_market_mode"):
            st.session_state[key] = "Rebased 100"
        result = self.ns["_build_macro_figures_parallel"]()
        self.assertEqual(set(result), set(range(1, 14)))
        for number in (1, 10, 11):
            self.ns[f"build_fig{number}"].assert_called_once_with("5Y")
        self.ns["build_fig5"].assert_called_once_with("5Y")

    def test_failed_figure_is_not_cached_and_can_recover_immediately(self):
        self.ns["build_fig1"].side_effect = [TimeoutError("source unavailable"), self.figure]
        first = self.ns["_build_macro_figures_parallel"]()
        self.assertEqual(len(first[1].data), 0)
        second = self.ns["_build_macro_figures_parallel"]()
        self.assertEqual(len(second[1].data), 1)
        self.assertEqual(self.ns["build_fig1"].call_count, 2)

    def test_partial_hk_bundle_keeps_good_charts_and_recovers_without_cache_clear(self):
        partial = [go.Figure(), self.figure, self.figure, self.figure]
        self.ns["build_fig5"].side_effect = [partial, [self.figure]*4]
        first = self.ns["_safe_hk_bundle"](())
        self.assertEqual(len(first[0].data), 0)
        self.assertEqual(len(first[1].data), 1)
        second = self.ns["_safe_hk_bundle"](())
        self.assertEqual(len(second[0].data), 1)
        self.assertEqual(self.ns["build_fig5"].call_count, 2)

    def test_hk_composite_error_keeps_banking_and_funding_data(self):
        self.ns["_cached_hk_bundle"].clear()
        self.ns["build_fig5"].side_effect = OSError("optional market overlay failed")
        figures = self.ns["_safe_hk_bundle"](())
        self.assertEqual(len(figures), 4)
        self.assertEqual(len(figures[1].data), 1)
        self.assertEqual(len(figures[2].data), 1)
        self.ns["build_hk_core_snapshot_figures"].assert_called_once_with("5Y")

    def test_snapshot_replacement_invalidates_figure_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / "data_snapshots"
            folder.mkdir()
            snapshot = folder / "test.json"
            snapshot.write_text("{}")
            self.ns["__file__"] = str(root / "app.py")
            before = self.ns["_macro_snapshot_revision"]()
            self.ns["_cached_macro_figure"](1, before, self.ns["CHART_BUILD"])
            snapshot.write_text('{"updated": true}')
            after = self.ns["_macro_snapshot_revision"]()
            self.assertNotEqual(before, after)
            self.ns["_cached_macro_figure"](1, after, self.ns["CHART_BUILD"])
            self.assertEqual(self.ns["build_fig1"].call_count, 2)

    def test_index_quotes_are_concurrent_and_fallback_runs_on_main_thread(self):
        main = threading.get_ident()
        barrier = threading.Barrier(6, timeout=2)
        first_six = {"^IXIC", "^GSPC", "^DJI", "^HSI", "HSTECH.HK", "000001.SS"}
        def fetch(symbol, key):
            self.assertEqual(key, 123)
            self.assertNotEqual(threading.get_ident(), main)
            if symbol in first_six:
                barrier.wait()
            if symbol == "^HSI":
                raise TimeoutError("provider failure")
            return {"price": 100, "regular_market_time": 1780000000}
        def remember(symbol, row):
            self.assertEqual(threading.get_ident(), main)
            if row.get("price") is None:
                return {"price": 99, "_stale": True}
            return row
        self.ns["_get_cached_quote"] = fetch
        self.ns["_remember_quote"] = remember
        result = self.ns["_load_market_quotes"](123)
        self.assertEqual(set(result), {"nasdaq", "sp500", "dow", "hsi", "hstech", "sh", "sz", "csi300"})
        self.assertEqual(result["hsi"], {"price": 99, "_stale": True})

    def test_history_pair_is_concurrent_and_one_failure_keeps_other_series(self):
        barrier = threading.Barrier(2, timeout=2)
        frame = pd.DataFrame({"observation_date": [pd.Timestamp("2026-09-29")], "close": [100]})
        def fetch(symbol):
            barrier.wait()
            if symbol == "SI=F":
                raise TimeoutError("silver source unavailable")
            return frame
        self.ns["get_yahoo_daily_history"] = fetch
        result = self.ns["_load_yahoo_histories"](("GC=F", "SI=F"))
        pd.testing.assert_frame_equal(result["GC=F"], frame)
        self.assertTrue(result["SI=F"].empty)
        self.assertEqual(list(result["SI=F"].columns), ["observation_date", "close"])


if __name__ == "__main__":
    unittest.main()

