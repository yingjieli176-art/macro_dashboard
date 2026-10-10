"""Failure/recovery, latency and resource regressions for the consolidated update."""
import ast
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

import data
from macro_platform.background_refresh import BackgroundRefresh
from macro_platform.request_runtime import (
    WorkerPool, PeriodicWorker, completed_jobs, http_get, request_budget, observed_cache,
)
from macro_platform.hk_liquidity import build_hk_liquidity_figures
from test_dashboard_loading import load_helpers

ROOT = Path(__file__).resolve().parents[1]


def until(predicate, seconds=3):
    deadline = time.monotonic()+seconds
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError("background result did not arrive")
        time.sleep(.005)


class ConsolidatedRuntime(unittest.TestCase):
    def test_snapshot_revision_invalidates_the_source_cache_immediately(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"observed.txt"
            path.write_text("1")
            calls = []
            @observed_cache(lambda: (path,))
            def read():
                calls.append(1)
                return pd.DataFrame({"observation_date": pd.to_datetime(["2026-10-09"]),
                                     "value": [float(path.read_text())]})
            try:
                self.assertEqual(read().value.tolist(), [1])
                self.assertEqual(read().value.tolist(), [1])
                path.write_text("22")
                self.assertEqual(read().value.tolist(), [22])
                self.assertEqual(len(calls), 2)
            finally:
                read.clear()

    def test_empty_live_source_retries_after_short_failure_window(self):
        calls = []
        @observed_cache()
        def read():
            calls.append(1)
            return pd.DataFrame({"value": [] if len(calls) == 1 else [42]})
        try:
            with patch("macro_platform.request_runtime.time.monotonic", return_value=100):
                self.assertTrue(read().empty)
                self.assertTrue(read().empty)
                self.assertEqual(len(calls), 1)
            with patch("macro_platform.request_runtime.time.monotonic", return_value=111):
                self.assertEqual(read().value.tolist(), [42])
            self.assertEqual(len(calls), 2)
        finally:
            read.clear()

    def test_failed_source_keeps_last_observations_and_marks_stale(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"revision.txt"; path.write_text("good")
            @observed_cache(lambda: (path,))
            def read():
                if path.read_text() != "good":
                    return pd.DataFrame(columns=["observation_date", "value"])
                return pd.DataFrame({"observation_date": pd.to_datetime(["2026-10-08"]), "value": [4.0]})
            try:
                previous = read()
                path.write_text("upstream unavailable")
                retained = read()
                pd.testing.assert_frame_equal(previous, retained)
                self.assertTrue(retained.attrs["is_stale"])
                self.assertEqual(retained.observation_date.tolist(), previous.observation_date.tolist())
            finally:
                read.clear()

    def test_refresh_is_visible_through_getter_without_clearing_caches(self):
        with tempfile.TemporaryDirectory() as folder:
            scheduler = BackgroundRefresh(max_workers=1, retry_seconds=0)
            self.addCleanup(scheduler.close)
            frame = pd.DataFrame({"observation_date": pd.to_datetime(["2026-10-09"]), "DGS2": [4.0]})
            started, release = threading.Event(), threading.Event()
            def fetch(_):
                started.set(); release.wait(3)
                return frame.copy()
            with patch.object(data, "_FRED_SNAPSHOT_DIR", Path(folder)), \
                 patch.object(data, "_FRED_LAST_GOOD", {}), \
                 patch.object(data, "_FRED_REFRESH", scheduler), \
                 patch.object(data, "_fetch_fred_graph", fetch):
                old = frame.copy(); old["DGS2"] = 3.0
                data._save_fred_success("DGS2", old)
                import json
                file = Path(folder)/"DGS2.json"
                payload = json.loads(file.read_text()); payload["fetched_at"] -= 7200
                file.write_text(json.dumps(payload))
                self.assertEqual(data.get_dgs2().DGS2.tolist(), [3.0])
                self.assertTrue(started.wait(3))
                release.set()
                until(lambda: json.loads(file.read_text())["records"][-1]["value"] == 4.0)
                self.assertEqual(data.get_dgs2().DGS2.tolist(), [4.0])
                self.assertEqual(data.get_dgs2().observation_date.tolist(), frame.observation_date.tolist())
                scheduler._pool.shutdown(wait=True)

    def test_missing_source_returns_immediately_and_recovers_in_memory(self):
        with tempfile.TemporaryDirectory() as folder:
            scheduler = BackgroundRefresh(max_workers=1, retry_seconds=0)
            release = threading.Event()
            frame = pd.DataFrame({"observation_date": pd.to_datetime(["2026-10-09"]), "DGS2": [4.0]})
            def fetch(_):
                release.wait(3)
                return frame.copy()
            with patch.object(data, "_FRED_SNAPSHOT_DIR", Path(folder)), \
                 patch.object(data, "_FRED_LAST_GOOD", {}), \
                 patch.object(data, "_FRED_REFRESH", scheduler), \
                 patch.object(data, "_fetch_fred_graph", fetch), \
                 patch.object(data, "_save_fred_success", side_effect=OSError("read-only disk")):
                begin = time.monotonic()
                first = data.get_dgs2()
                self.assertTrue(first.empty)
                self.assertTrue(first.attrs["unavailable"])
                self.assertLess(time.monotonic()-begin, .3)
                release.set()
                until(lambda: "DGS2" in data._FRED_LAST_GOOD)
                self.assertEqual(data.get_dgs2().DGS2.tolist(), [4.0])
                scheduler._pool.shutdown(wait=True)
            scheduler.close()

    def test_empty_plot_is_not_a_success_cache_entry(self):
        ns = load_helpers()
        figure = go.Figure(go.Scatter(x=["2026-10-09"], y=[4.0]))
        for number in (1, 2, 3, 4, 9, 10, 11, 12):
            ns[f"build_fig{number}"] = Mock(return_value=figure)
        builder = Mock(side_effect=[go.Figure(), figure])
        ns["build_asia_rates_figure"] = builder
        ns["_cached_macro_figure"].clear()
        with self.assertRaises(ValueError):
            ns["_cached_macro_figure"](13, (), "recovery")
        recovered = ns["_cached_macro_figure"](13, (), "recovery")
        self.assertEqual(len(recovered.data), 1)
        self.assertEqual(builder.call_count, 2)

    def test_budget_does_not_wait_for_an_already_running_slow_task(self):
        pool = WorkerPool(2, "audit-budget")
        release = threading.Event()
        slow = pool.submit("slow", lambda: release.wait(3))
        fast = pool.submit("fast", lambda: 42)
        try:
            begin = time.monotonic()
            done = list(completed_jobs({slow: "slow", fast: "fast"}, budget=.08))
            self.assertLess(time.monotonic()-begin, .3)
            self.assertEqual([(key, future.result()) for key, future in done], [("fast", 42)])
            self.assertFalse(slow.done())
        finally:
            release.set(); pool.close()
            slow.result(timeout=3)

    def test_workers_coalesce_pending_tasks_and_bound_the_queue(self):
        pool = WorkerPool(1, "audit-coalesce", max_pending=2)
        release = threading.Event()
        first = pool.submit("same", lambda: release.wait(3))
        try:
            self.assertIs(pool.submit("same", lambda: 99), first)
            pool.submit("second", lambda: 2)
            with self.assertRaises(RuntimeError):
                pool.submit("third", lambda: 3)
        finally:
            release.set(); pool.close()
            first.result(timeout=3)
        with self.assertRaises(RuntimeError):
            pool.submit("closed", lambda: 1)

    def test_request_budget_prevents_later_retries_after_expiry(self):
        with patch("requests.get") as get:
            with request_budget(0):
                with self.assertRaises(requests.Timeout):
                    http_get("https://example.invalid", timeout=10)
            get.assert_not_called()

    def test_public_requests_share_a_process_wide_concurrency_limit(self):
        pool = WorkerPool(12, "audit-http")
        lock = threading.Lock()
        current = peak = 0
        def get(*args, **kwargs):
            nonlocal current, peak
            with lock:
                current += 1; peak = max(peak, current)
            time.sleep(.03)
            with lock:
                current -= 1
            return requests.Response()
        try:
            with patch("requests.get", side_effect=get):
                futures = [pool.submit(index, lambda: http_get("https://example.invalid")) for index in range(12)]
                for future in futures:
                    future.result(timeout=3)
            self.assertLessEqual(peak, 8)
            self.assertGreater(peak, 1)
        finally:
            pool.close()

    def test_repeated_session_bursts_and_release_converge_after_requests_finish(self):
        # Cache release cannot kill a request already executing. Repeated
        # sessions must still converge after those requests are allowed to end.
        from macro_platform import request_runtime as runtime
        lock = threading.Lock()
        active = peak = 0
        for cycle in range(6):
            entered, release = threading.Event(), threading.Event()
            prefix = f"audit-session-burst-{cycle}"
            pool = WorkerPool(12, prefix, max_pending=40)
            def get(*args, **kwargs):
                nonlocal active, peak
                with lock:
                    active += 1
                    peak = max(peak, active)
                    if active == 8:
                        entered.set()
                try:
                    self.assertTrue(release.wait(3))
                    return requests.Response()
                finally:
                    with lock:
                        active -= 1
            try:
                with patch("requests.get", side_effect=get):
                    futures = {session: pool.submit(session, lambda: http_get("https://example.invalid"))
                               for session in range(40)}
                    self.assertTrue(entered.wait(3))
                    for session, future in futures.items():
                        self.assertIs(pool.submit(session, lambda: None), future)
                    self.assertLessEqual(len(pool._pending), 40)
                    pool.close()
                    self.assertEqual(active, 8, "Closing the pool must not pretend to kill active HTTP")
                    release.set()
                    until(lambda: not pool._pending)
                    until(lambda: not any(thread.name.startswith(prefix) for thread in threading.enumerate()))
                    self.assertEqual(active, 0)
            finally:
                release.set()
                pool.close()
                pool._pool.shutdown(wait=True)
        self.assertEqual(peak, 8)
        # No HTTP permits were leaked by completion or cancellation.
        acquired = 0
        try:
            for _ in range(8):
                self.assertTrue(runtime._HTTP_SLOTS.acquire(timeout=.1))
                acquired += 1
        finally:
            for _ in range(acquired):
                runtime._HTTP_SLOTS.release()

    def test_periodic_worker_stops_before_its_next_update(self):
        called = threading.Event()
        worker = PeriodicWorker(called.set, 3600, "audit-periodic")
        self.assertTrue(called.wait(3))
        worker.close()
        until(lambda: not worker.thread.is_alive())

    def test_clearing_news_resource_stops_the_old_idle_thread(self):
        source = ast.parse((ROOT/"app.py").read_text())
        node = next(n for n in source.body if isinstance(n, ast.FunctionDef) and n.name == "_start_news_background_updater")
        called = threading.Event()
        ns = {"st": st, "PeriodicWorker": PeriodicWorker, "_write_news_snapshot": called.set,
              "NEWS_BACKGROUND_INTERVAL_SECONDS": 3600}
        exec(compile(ast.Module(body=[node], type_ignores=[]), "app.py", "exec"), ns)
        start = ns["_start_news_background_updater"]
        first = start(); self.assertTrue(called.wait(3))
        start.clear()
        until(lambda: not first.thread.is_alive())
        second = start()
        try:
            self.assertIsNot(first, second)
        finally:
            start.clear()

    def test_fast_chart_publishes_before_slow_overview_or_watchlist(self):
        ns = load_helpers()
        st.session_state.clear()
        figure = go.Figure(go.Scatter(x=["2026-10-09"], y=[4.0]))
        for number in (1, 2, 3, 4, 9, 10, 11, 12):
            ns[f"build_fig{number}"] = Mock(return_value=figure)
        ns["build_asia_rates_figure"] = Mock(return_value=figure)
        ns["build_fig5"] = Mock(return_value=[figure]*4)
        for name in ("_cached_macro_figure", "_cached_hk_bundle"):
            ns[name].clear()
        release = threading.Event()
        published = []
        def quotes():
            self.assertTrue(release.wait(3))
            return {}
        def chart(number, _):
            self.assertNotIn("market", published) if not release.is_set() else None
            published.append(number)
            release.set()
        ns["_build_macro_figures_parallel"](chart, {"market": quotes, "watchlist": quotes},
                                               lambda key, _: published.append(key))
        self.assertLess(published.index(1) if 1 in published else 99, len(published))
        self.assertIsInstance(published[0], int)
        self.assertEqual({value for value in published if isinstance(value, int)}, set(range(1, 14)))
        self.assertIn("market", published); self.assertIn("watchlist", published)

    def test_hk_equity_overlays_preserve_actual_closes_and_separate_index_units(self):
        import json
        snapshot = json.loads((ROOT/'data_snapshots/hk_market_daily.json').read_text())['series']
        with patch.object(requests.sessions.Session, "request", side_effect=requests.Timeout("offline")):
            figures = build_hk_liquidity_figures("5Y")
        for index in (0, 3):
            traces = {trace.name: trace for trace in figures[index].data}
            for name, symbol, axis in (("Tencent Price (R1)", "0700.HK", "y2"),
                                       ("HKEX Price (R1)", "0388.HK", "y2"),
                                       ("HSTECH Index (R2)", "HSTECH", "y3"),
                                       ("HSI Index (R2)", "^HSI", "y3")):
                trace = traces[name]
                expected = {row['observation_date']: row['close'] for row in snapshot[symbol]['records']}
                self.assertEqual(trace.yaxis, axis)
                self.assertGreater(len(trace.y), 20)
                for date, value in zip(trace.x, trace.y):
                    if pd.notna(value):
                        self.assertAlmostEqual(float(value), expected[pd.Timestamp(date).strftime('%Y-%m-%d')])


if __name__ == "__main__":
    unittest.main()
