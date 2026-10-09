"""Regression cases discovered in the final accuracy/performance audit."""
import ast
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import pandas as pd
from macro_platform.background_refresh import BackgroundRefresh
from macro_platform.market_history import completed_daily_closes
from macro_platform.hk_liquidity import _market_snapshot_history
from scripts import update_hk_market_daily as hk_sync
from scripts import sync_fred_verified_cache as fred_sync
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def helpers(path, names, namespace):
    tree = ast.parse((ROOT / path).read_text())
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    for node in selected:
        node.decorator_list = []
    exec(compile(ast.Module(body=selected, type_ignores=[]), path, "exec"), namespace)
    return namespace


class AccuracyPerformanceTests(unittest.TestCase):
    def test_closed_and_unknown_us_prices_keep_their_regular_quote_timestamp(self):
        ns = helpers("app.py", {"_quote_session_context", "_active_quote_values", "_valid_market_timestamp"}, {
            "time": time, "_us_overnight_window_now": lambda: False,
            "_us_clock_state": lambda: "休市",
        })
        now = time.time()
        for state in ("CLOSED", ""):
            row = {"market_state": state, "price": 100, "change_pct": 1,
                   "regular_market_time": now - 8 * 3600, "post_price": 110,
                   "post_change_pct": 11, "post_market_time": now - 4 * 3600}
            self.assertEqual(ns["_active_quote_values"](row, "US"), (100, 1))
            self.assertEqual(ns["_quote_session_context"](row, "US")[1], row["regular_market_time"])

    def test_same_day_crypto_bar_is_excluded_until_utc_midnight(self):
        node = {"timestamp": [1791417600, 1791504000],
                "meta": {"instrumentType": "CRYPTOCURRENCY", "exchangeTimezoneName": "UTC"},
                "indicators": {"quote": [{"close": [100, 200]}]}}
        frame = completed_daily_closes(node, now="2026-10-09T12:00:00Z")
        self.assertEqual(frame.close.tolist(), [100])
        after = completed_daily_closes(node, now="2026-10-10T00:00:00Z")
        self.assertEqual(after.close.tolist(), [100, 200])

    def test_equity_bar_completes_after_local_session_end_and_uses_raw_close(self):
        start = int(pd.Timestamp("2026-10-09T01:30Z").timestamp())
        end = int(pd.Timestamp("2026-10-09T08:00Z").timestamp())
        node = {"timestamp": [start], "meta": {
            "exchangeTimezoneName": "Asia/Hong_Kong", "instrumentType": "EQUITY",
            "currentTradingPeriod": {"regular": {"start": start, "end": end}}},
            "indicators": {"quote": [{"close": [120]}], "adjclose": [{"adjclose": [100]}]}}
        self.assertTrue(completed_daily_closes(node, now="2026-10-09T07:59Z").empty)
        self.assertEqual(completed_daily_closes(node, now="2026-10-09T08:01Z").close.tolist(), [120])

    def test_invalid_daily_bars_are_rejected_without_truncating_parallel_arrays(self):
        node = {"timestamp": [1600000000, 1600086400, 1600172800],
                "indicators": {"quote": [{"close": [100, float("inf"), -1]}]}}
        self.assertEqual(completed_daily_closes(node).close.tolist(), [100])
        node["timestamp"].pop()
        with self.assertRaises(ValueError):
            completed_daily_closes(node)

    def test_hk_five_year_history_retains_every_day_and_extremum(self):
        payload = json.loads((ROOT / "data_snapshots/hk_market_daily.json").read_text())
        for symbol, node in payload["series"].items():
            with self.subTest(symbol=symbol):
                full = pd.DataFrame(node["records"])
                full.observation_date = pd.to_datetime(full.observation_date)
                full = full[full.observation_date >= full.observation_date.max() - pd.DateOffset(years=5)]
                shown = _market_snapshot_history(symbol, "price", "5Y")
                self.assertEqual(shown.observation_date.tolist(), full.observation_date.tolist())
                self.assertEqual(shown.price.tolist(), full.close.tolist())

    def test_raw_migration_does_not_merge_legacy_adjusted_history(self):
        legacy = {"series": {"0700.HK": {"records": [{"observation_date": "2026-09-01", "close": 80}]}}}
        self.assertTrue(hk_sync._existing_frame(legacy, "0700.HK").empty)
        legacy["series"]["0700.HK"]["price_basis"] = "raw_close"
        self.assertEqual(hk_sync._existing_frame(legacy, "0700.HK").close.tolist(), [80])

    def test_hour_old_fred_snapshot_queues_refresh_without_waiting_for_http(self):
        snapshot = pd.DataFrame({"observation_date": pd.to_datetime(["2026-10-05"]), "SOFR": [3.88]})
        snapshot.attrs["fetched_at"] = time.time() - 83 * 3600
        scheduler, live = Mock(), Mock(side_effect=AssertionError("snapshot read must not wait for HTTP"))
        ns = helpers("data.py", {"_fred_series"}, {"time": time, "pd": pd,
            "_read_fred_success": lambda _: snapshot, "_FRED_REFRESH": scheduler,
            "_refresh_fred_series": live})
        self.assertEqual(ns["_fred_series"]("SOFR").SOFR.tolist(), [3.88])
        scheduler.submit.assert_called_once()
        live.assert_not_called()

    def test_background_refresh_is_single_flight(self):
        started, release = threading.Event(), threading.Event()
        scheduler = BackgroundRefresh(max_workers=1, retry_seconds=0)
        def refresh():
            started.set()
            release.wait(2)
        try:
            self.assertTrue(scheduler.submit("SOFR", refresh))
            self.assertTrue(started.wait(2))
            self.assertFalse(scheduler.submit("SOFR", refresh))
        finally:
            release.set()
            scheduler._pool.shutdown(wait=True)

    def test_fred_health_distinguishes_available_stale_and_missing_series(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(fred_sync, "OUT", Path(folder)):
            dates = pd.date_range("2026-09-20", periods=12)
            payload = {"series_id": "SOFR", "coverage_end": "2026-10-01", "records": [
                {"date": date.strftime("%Y-%m-%d"), "value": 3.88} for date in dates]}
            file = Path(folder) / "SOFR.json"
            file.write_text(json.dumps(payload))
            self.assertEqual(fred_sync.snapshot_health("SOFR", now="2026-10-09")["status"], "available")
            self.assertEqual(fred_sync.snapshot_health("SOFR", now="2026-11-09")["status"], "stale")
            self.assertEqual(fred_sync.snapshot_health("EFFR", now="2026-10-09")["status"], "missing_or_invalid")
            payload["records"][-1]["value"] = float("inf")
            file.write_text(json.dumps(payload))
            self.assertEqual(fred_sync.snapshot_health("SOFR", now="2026-10-09")["status"], "missing_or_invalid")

    def test_peer_quote_sources_run_concurrently_and_newest_timestamp_wins(self):
        barrier = threading.Barrier(3, timeout=2)
        def getter(ts):
            def fetch(_):
                barrier.wait()
                return {"price": ts, "regular_market_time": ts}
            return fetch
        ns = helpers("app.py", {"_fetch_quote"}, {
            "ThreadPoolExecutor": ThreadPoolExecutor, "_symbol_market": lambda _: "HK",
            "_get_sina_hk_quote_safe": getter(1), "_get_tencent_quote_safe": getter(3),
            "_get_eastmoney_quote_safe": getter(2), "_tag_quote_role": lambda row, _: row,
            "_newest_quote": lambda rows: max(rows, key=lambda row: row["regular_market_time"]),
            "_quote_regular_age_seconds": lambda _: 0, "_regular_session_now": lambda _: False})
        self.assertEqual(ns["_fetch_quote"]("0700.HK")["price"], 3)

    def test_ready_chart_is_rendered_on_main_thread_before_slow_chart_finishes(self):
        release = threading.Event()
        main_thread = threading.get_ident()
        def build(number, *_):
            if number == 13:
                if not release.wait(2):
                    raise AssertionError("fast charts were held behind a slow chart")
            return number
        ns = helpers("app.py", {"_build_macro_figures_parallel"}, {
            "st": SimpleNamespace(session_state={}), "CHART_BUILD": "test",
            "ThreadPoolExecutor": ThreadPoolExecutor, "as_completed": as_completed,
            "_macro_snapshot_revision": lambda: (), "_cached_macro_figure": build,
            "_safe_macro_build": lambda _, builder: builder(),
            "_safe_hk_bundle": lambda *_: [5, 6, 7, 8]})
        completed = []
        def render(number, figure):
            self.assertEqual(threading.get_ident(), main_thread)
            completed.append(number)
            if number == 1:
                self.assertNotIn(13, completed)
                release.set()
        try:
            result = ns["_build_macro_figures_parallel"](render)
        finally:
            release.set()
        self.assertEqual(set(completed), set(range(1, 14)))
        self.assertEqual(len(completed), 13)
        self.assertEqual(set(result), set(range(1, 14)))


if __name__ == "__main__":
    unittest.main()
