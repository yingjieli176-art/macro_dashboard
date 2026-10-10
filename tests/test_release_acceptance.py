"""Success-path and delayed-publication regressions missed by outage-only smoke checks."""
import ast
from concurrent.futures import Future
import json
import pickle
from pathlib import Path
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from macro_platform.market_history import completed_daily_closes
from macro_platform.echarts_axes import build_adaptive_echarts_option
from test_dashboard_loading import load_helpers

ROOT = Path(__file__).resolve().parents[1]


def load_functions(names, namespace):
    tree = ast.parse((ROOT / "app.py").read_text())
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                and node.name in names]
    imports = [node for node in tree.body if isinstance(node, ast.ImportFrom)
               and node.module == "urllib.parse"]
    for node in selected:
        node.decorator_list = []
    exec(compile(ast.Module(body=imports+selected, type_ignores=[]), str(ROOT / "app.py"), "exec"), namespace)
    return namespace


class ReleaseAcceptance(unittest.TestCase):
    def test_new_session_preserves_real_samples_on_shared_macro_cache_hit(self):
        rows = json.loads((ROOT/'data_snapshots/fred_cache/SOFR.json').read_text())['records'][-20:]
        dates = pd.to_datetime([row['date'] for row in rows])
        values = [row['value'] for row in rows]
        ns = load_helpers()
        builder = Mock(side_effect=lambda *args: go.Figure(go.Scatter(
            x=dates, y=pd.Series(values), name='SOFR')))
        for number in (1, 2, 3, 4, 9, 10, 11, 12):
            ns[f'build_fig{number}'] = builder
        ns['build_asia_rates_figure'] = builder
        ns['_cached_macro_figure'].clear()
        self.addCleanup(ns['_cached_macro_figure'].clear)
        first = ns['_cached_macro_figure'](1, (), 'cache-sample-regression')
        # No per-session last-good chart exists for the second caller.
        st.session_state.clear()
        second = ns['_cached_macro_figure'](1, (), 'cache-sample-regression')
        option = build_adaptive_echarts_option(second)
        self.assertIsNotNone(option)
        self.assertEqual(option, build_adaptive_echarts_option(first))
        self.assertEqual(list(second.data[0].y), values)
        self.assertEqual([pd.Timestamp(value).strftime('%Y-%m-%d') for value in second.data[0].x],
                         [row['date'] for row in rows])
        self.assertEqual(builder.call_count, 1)

    def test_hk_raw_cache_survives_plotly_pickle_with_actual_closes(self):
        rows = json.loads((ROOT/'data_snapshots/hk_market_daily.json').read_text())['series']['0700.HK']['records'][-20:]
        dates = pd.to_datetime([row['observation_date'] for row in rows])
        values = [row['close'] for row in rows]
        ns = load_helpers()
        ns['build_fig5'] = Mock(side_effect=lambda *args, **kwargs: [go.Figure(go.Scatter(
            x=dates, y=pd.Series(values), name='Tencent raw close')) for _ in range(4)])
        ns['_cached_hk_bundle'].clear()
        self.addCleanup(ns['_cached_hk_bundle'].clear)
        first = ns['_cached_hk_bundle']((), 'cache-sample-regression')
        st.session_state.clear()
        second = ns['_cached_hk_bundle']((), 'cache-sample-regression')
        for original, cached in zip(first, second):
            restored = pickle.loads(pickle.dumps(cached))
            self.assertEqual(list(restored.data[0].y), values)
            self.assertEqual(build_adaptive_echarts_option(restored),
                             build_adaptive_echarts_option(original))
            self.assertIsNotNone(build_adaptive_echarts_option(restored))
        self.assertEqual(ns['build_fig5'].call_count, 1)

    def test_successful_yahoo_read_uses_actual_repository_raw_observations(self):
        records = json.loads((ROOT / "data_snapshots/hk_market_daily.json").read_text())["series"]["0700.HK"]["records"][-3:]
        response = Mock()
        response.json.return_value = {"chart": {"result": [{
            "meta": {"exchangeTimezoneName": "Asia/Hong_Kong", "instrumentType": "EQUITY"},
            "timestamp": [int(pd.Timestamp(row["observation_date"], tz="Asia/Hong_Kong").timestamp()) for row in records],
            "indicators": {"quote": [{"close": [row["close"] for row in records]}],
                           "adjclose": [{"adjclose": [1, 2, 3]}]},
        }]}}
        get = Mock(return_value=response)
        ns = load_functions({"get_yahoo_daily_history"}, {
            "pd": pd, "http_get": get,
            "completed_daily_closes": completed_daily_closes,
        })
        # Intentionally no requests global: production removed that import.
        frame = ns["get_yahoo_daily_history"]("0700.HK")
        self.assertEqual(frame.close.tolist(), [row["close"] for row in records])
        self.assertEqual(frame.observation_date.dt.strftime("%Y-%m-%d").tolist(),
                         [row["observation_date"] for row in records])
        response.raise_for_status.assert_called_once()
        self.assertEqual(get.call_args.kwargs["params"]["interval"], "1d")
        ns["get_yahoo_daily_history"]("GC=F")
        self.assertTrue(get.call_args.args[0].endswith("GC%3DF"))

    def setUp(self):
        st.session_state.clear()
        self.addCleanup(st.session_state.clear)
        self.ns = load_functions({"_publish_late_dashboard_result", "_newest_quote",
                                  "_quote_regular_age_seconds", "_empty_quote"}, {
            "st": st, "time": time, "MARKET_SYMBOLS": {"HSI": "^HSI"},
            "_remember_quote": lambda symbol, row: row,
            "_valid_market_timestamp": lambda value: value,
            "_watchlist_symbols": lambda: ["KEEP"],
            "_apply_watchlist_quote_rows": Mock(),
            "_figure_has_real_observations": lambda figure: bool(figure),
        })

    def test_late_market_result_is_persisted_before_a_rerun(self):
        row = {"price": 123.0, "regular_market_time": time.time()}
        self.assertTrue(self.ns["_publish_late_dashboard_result"]("market", {"^HSI": row}))
        self.assertEqual(st.session_state["_market_quotes_snapshot"]["HSI"]["price"], 123)
        self.assertGreater(st.session_state["_market_quotes_snapshot_time"], 0)

    def test_late_old_quote_does_not_replace_a_newer_manual_quote(self):
        now = time.time()
        st.session_state["_market_quotes_snapshot"] = {"HSI": {"price": 200, "regular_market_time": now}}
        self.ns["_publish_late_dashboard_result"]("market", {"^HSI": {"price": 100, "regular_market_time": now-100}})
        self.assertEqual(st.session_state["_market_quotes_snapshot"]["HSI"]["price"], 200)

    def test_late_watchlist_result_respects_current_symbols_and_controls(self):
        st.session_state["precious_metals_time_window"] = "3M"
        st.session_state["hk_5_range_time_window"] = "1M"
        row = {"price": 123, "regular_market_time": time.time()}
        self.ns["_publish_late_dashboard_result"]("watchlist", {"KEEP": row, "REMOVED": row})
        self.ns["_apply_watchlist_quote_rows"].assert_called_once_with(["KEEP"], {"KEEP": row}, ["KEEP"])
        self.assertEqual(st.session_state["precious_metals_time_window"], "3M")
        self.assertEqual(st.session_state["hk_5_range_time_window"], "1M")

    def test_failed_late_results_do_not_request_another_rerun(self):
        self.assertFalse(self.ns["_publish_late_dashboard_result"]("market", {"^HSI": {"price": None}}))
        self.assertFalse(self.ns["_publish_late_dashboard_result"]("hk5", [False]*4))
        self.assertFalse(self.ns["_publish_late_dashboard_result"](10, False))

    def test_delayed_completion_updates_once_without_losing_controls(self):
        future = Future()
        state = {"_late_dashboard_jobs": {future: "market"},
                 "_source_watch_until": time.monotonic()+60,
                 "_source_watch_revision": ("unchanged",),
                 "hk_5_range_time_window": "1M", "precious_metals_time_window": "3M"}
        ui = SimpleNamespace(session_state=state, rerun=Mock())
        self.ns.update({"st": ui, "_macro_snapshot_revision": lambda: ("unchanged",)})
        load_functions({"_poll_source_completion"}, self.ns)
        poll = self.ns["_poll_source_completion"]
        poll(); ui.rerun.assert_not_called()
        future.set_result({"^HSI": {"price": 123, "regular_market_time": time.time()}})
        poll(); ui.rerun.assert_called_once()
        self.assertEqual(state["_market_quotes_snapshot"]["HSI"]["price"], 123)
        self.assertFalse(state["_late_dashboard_jobs"])
        poll(); ui.rerun.assert_called_once()
        self.assertEqual(state["hk_5_range_time_window"], "1M")
        self.assertEqual(state["precious_metals_time_window"], "3M")


if __name__ == "__main__":
    unittest.main()
