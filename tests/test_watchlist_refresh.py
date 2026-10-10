"""Exercise app helpers without importing its network-heavy top-level dashboard."""
import ast
import logging
from macro_platform.request_runtime import submit_jobs, completed_jobs
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
import threading
import time
import unittest
from unittest.mock import Mock
from zoneinfo import ZoneInfo


HELPERS = {
    "_fetch_quote_rows", "_apply_watchlist_quote_rows", "_cached_hk_common", "_empty_quote", "_symbol_market", "_remember_quote", "_stable_quote",
    "_get_watchlist_quote", "_request_watchlist_refresh", "_watchlist_symbols",
    "_load_watchlist_quotes", "_watchlist_refresh_status", "_active_quote_values",
    "render_watchlists",
}


def load_helpers(st):
    source = Path(__file__).resolve().parents[1] / "app.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    selected = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in HELPERS:
            node.decorator_list = []
            selected.append(node)
    namespace = {
        "st": st, "logging": logging, "time": time, "datetime": datetime,
        "DASHBOARD_TZ": ZoneInfo("Asia/Hong_Kong"),
        "ThreadPoolExecutor": ThreadPoolExecutor, "as_completed": as_completed,
        "WATCHLIST_KEYS": ("market_search_us", "market_search_hk", "market_search_cn"),
        "_quote_session_context": lambda row, market: ("交易中", row.get("regular_market_time")),
    }
    namespace.update({"submit_jobs": submit_jobs, "completed_jobs": completed_jobs,
                      "_quote_refresh_key": lambda: 0})
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(source), "exec"), namespace)
    return namespace


class FakeUI:
    def __init__(self):
        self.session_state = {}
        self.buttons = []
        self.captions = []
        self.on_fetch = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def columns(self, spec, **kwargs):
        return [self] * (spec if isinstance(spec, int) else len(spec))

    def empty(self):
        return self

    def button(self, label, **kwargs):
        self.buttons.append((label, kwargs))
        return False

    def caption(self, text):
        self.captions.append(text)

    def markdown(self, *args, **kwargs):
        pass

    def spinner(self, *args, **kwargs):
        return self

    def container(self, **kwargs):
        return self


class WatchlistRefreshTests(unittest.TestCase):
    def setUp(self):
        self.ui = FakeUI()
        self.ns = load_helpers(self.ui)
        self.store = {}
        self.ns["_last_good_quote_store"] = lambda: self.store
        self.ns["_get_cached_quote"] = Mock(side_effect=AssertionError("manual refresh must bypass cache"))
        self.ns["_fetch_quote"] = Mock(side_effect=lambda symbol: self.quote())

    def quote(self, price=10, timestamp=1780000000):
        return {**self.ns["_empty_quote"](), "price": price, "change_pct": 1,
                "regular_market_time": timestamp}

    def load(self, symbols, manual=False):
        self.ns["_load_watchlist_quotes"](symbols, manual=manual)

    def test_consecutive_manual_refreshes_fetch_again_even_if_prices_unchanged(self):
        self.load(["NVDA", "600160.SS"])
        self.load(["NVDA", "600160.SS"], manual=True)
        self.load(["NVDA", "600160.SS"], manual=True)
        self.assertEqual(self.ns["_fetch_quote"].call_count, 6)
        self.ns["_get_cached_quote"].assert_not_called()
        result = self.ui.session_state["_watchlist_refresh_result"]
        self.assertEqual((result["received"], result["changed"]), (2, 0))
        self.assertIn("报价未变化", self.ns["_watchlist_refresh_status"]())

    def test_provider_exception_retains_old_quote_and_reports_missing(self):
        self.load(["NVDA"])
        self.ns["_fetch_quote"] = Mock(side_effect=TimeoutError("provider timed out"))
        self.load(["NVDA", "NBIS"], manual=True)
        snapshot = self.ui.session_state["_watchlist_quotes_snapshot"]
        self.assertEqual(snapshot["NVDA"]["price"], 10)
        self.assertTrue(snapshot["NVDA"]["_stale"])
        self.assertIsNone(snapshot["NBIS"]["price"])
        result = self.ui.session_state["_watchlist_refresh_result"]
        self.assertEqual((result["received"], result["retained"], result["missing"]), (0, 1, 1))
        self.assertIn("请求失败", self.ns["_watchlist_refresh_status"]())
        self.assertNotIn("报价未变化", self.ns["_watchlist_refresh_status"]())

    def test_price_change_count_and_source_timestamp_are_preserved(self):
        self.load(["NVDA"])
        fresh = self.quote(price=11, timestamp=1780000060)
        self.ns["_fetch_quote"] = Mock(return_value=fresh)
        self.load(["NVDA"], manual=True)
        self.assertEqual(self.ui.session_state["_watchlist_refresh_result"]["changed"], 1)
        self.assertEqual(self.ns["_get_watchlist_quote"]("NVDA")["regular_market_time"], 1780000060)
        self.assertFalse(self.ns["_get_watchlist_quote"]("NVDA")["_stale"])

    def test_non_refresh_interactions_only_fetch_new_symbols(self):
        self.load(["NVDA"])
        self.load(["NVDA"])
        self.load(["NVDA", "NBIS"])
        self.load(["NBIS"])
        self.assertEqual(self.ns["_fetch_quote"].call_count, 2)
        self.assertEqual(set(self.ui.session_state["_watchlist_quotes_snapshot"]), {"NBIS"})

    def test_quotes_run_concurrently_and_state_updates_stay_on_main_thread(self):
        barrier = threading.Barrier(6, timeout=2)
        main_thread = threading.get_ident()
        def fetch(symbol):
            self.assertNotEqual(threading.get_ident(), main_thread)
            if int(symbol) < 6:
                barrier.wait()
            return self.quote()
        def remember(symbol, row):
            self.assertEqual(threading.get_ident(), main_thread)
            return row
        self.ns["_fetch_quote"] = fetch
        self.ns["_remember_quote"] = remember
        progress = Mock()
        self.ns["_load_watchlist_quotes"]([str(i) for i in range(11)], manual=True, progress=progress)
        self.assertEqual(self.ui.session_state["_watchlist_refresh_result"]["received"], 11)
        self.assertEqual(progress.caption.call_count, 11)
        progress.caption.assert_called_with("刷新中… 11/11")

    def test_refresh_callback_leaves_overview_snapshot_untouched(self):
        overview = {"hsi": self.quote()}
        self.ui.session_state["_market_quotes_snapshot"] = overview
        self.ns["_request_watchlist_refresh"]()
        self.load(["0700.HK"], manual=True)
        self.assertTrue(self.ui.session_state["_watchlist_refresh_pending"])
        self.assertIs(self.ui.session_state["_market_quotes_snapshot"], overview)

    def test_empty_and_legacy_watchlists(self):
        self.ui.session_state["market_search_us_confirmed"] = {"symbol": "NVDA"}
        self.ui.session_state["market_search_hk_confirmed"] = [None, {"symbol": "NVDA"}, {"symbol": "0700.HK"}]
        self.ui.session_state["market_search_cn_confirmed"] = "invalid"
        self.assertEqual(self.ns["_watchlist_symbols"](), ["NVDA", "0700.HK"])
        self.load([], manual=True)
        self.ns["_fetch_quote"].assert_not_called()
        self.assertIn("暂无自选标的", self.ns["_watchlist_refresh_status"]())

    def test_fragment_shows_busy_progress_result_and_reenables_button(self):
        self.ui.session_state["market_search_us_confirmed"] = [{"symbol": "NVDA"}]
        self.ns["_render_quote_block"] = lambda item: "quote"
        self.ns["_delete_confirmed"] = lambda *args: None
        self.ns["_open_search"] = lambda *args: None
        self.ns["render_watchlists"]()
        self.ui.buttons.clear()
        self.ns["_request_watchlist_refresh"]()
        self.ns["render_watchlists"]()
        refresh_buttons = [(label, opts) for label, opts in self.ui.buttons if "refresh_watchlist_quotes" in opts.get("key", "")]
        self.assertEqual([label for label, _ in refresh_buttons], ["刷新中…", "↻ 刷新"])
        self.assertTrue(refresh_buttons[0][1]["disabled"])
        self.assertIs(refresh_buttons[1][1]["on_click"], self.ns["_request_watchlist_refresh"])
        self.assertFalse(self.ui.session_state["_watchlist_refresh_pending"])
        self.assertIn("取得报价 1/1", self.ui.captions[-1])


if __name__ == "__main__":
    unittest.main()

