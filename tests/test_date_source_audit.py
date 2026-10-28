"""Admission, audit coverage and request reuse across the full dashboard."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

import pandas as pd
import plotly.graph_objects as go
import requests

from macro_platform.echarts_axes import option_observation_health, summarize_series_dates
from macro_platform.request_runtime import observed_cache
from scripts import probe_all_sources as probe
from scripts.audit_source_freshness import raw_record_issues


class DateAndSourceAudit(unittest.TestCase):
    def tearDown(self):
        probe.reset_probe_cache()

    def test_inventory_uses_all_17_display_numbers_and_new_equity_sources(self):
        inventory = {key: charts for key, charts, *_ in probe.jobs()}
        self.assertEqual({c for charts in inventory.values() for c in charts}, set(range(1, 18)))
        for key, charts in {"SPX": [11], "RSP": [11], "000300": [12], "000852": [12],
                            "932000": [12], "china_2y": [13], "japan_2y": [14],
                            "GC=F": [15], "HG=F": [16], "BTC-USD": [17]}.items():
            self.assertEqual(inventory[key], charts)

    def test_tomorrows_observation_is_invalid_even_with_a_fresh_fetch(self):
        option = {"series": [{"name": "X", "data": [["2026-10-29", 1]]}]}
        self.assertEqual(option_observation_health(option, now="2026-10-28")["future_names"], ["X"])
        fig = go.Figure(go.Scatter(x=["2026-10-29"], y=[1], name="X"))
        self.assertEqual(summarize_series_dates(fig, now=pd.Timestamp("2026-10-28"))["future_names"], ["X"])
        row = probe.check(("X", [1], "daily", None, lambda: ("2099-01-01", "official")))
        self.assertEqual(row["status"], "unverified")

    def test_raw_audit_finds_bad_interior_dates_duplicates_and_nonfinite_values(self):
        payload = {"records": [{"date": "bad", "close": 1}, {"date": "2026-10-27", "close": 2},
                               {"date": "2026-10-27", "close": float("inf")},
                               {"date": "2026-10-29", "close": 3}]}
        self.assertEqual(raw_record_issues(payload, now="2026-10-28"), {
            "invalid_date_rows": 1, "future_date_rows": 1, "duplicate_date_rows": 1,
            "invalid_value_cells": 1})
        monthly = {"records": [{"end_of_month": "2026-10", "m2_hkd": 100}]}
        self.assertEqual(raw_record_issues(monthly, now="2026-10-28")["future_date_rows"], 1)

    def test_concurrent_identical_http_reads_share_one_download_and_one_failure(self):
        probe.reset_probe_cache()
        barrier = threading.Barrier(6)
        response = Mock()
        def slow(*args, **kwargs):
            time.sleep(.03)
            return response
        def fetch(_):
            barrier.wait()
            return probe.get("https://example.invalid/data", params={"year": 2026})
        with patch.object(probe.requests, "get", side_effect=slow) as get, ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(fetch, range(6)))
        self.assertTrue(all(result is response for result in results))
        self.assertEqual(get.call_count, 1)
        self.assertEqual(probe._PROBE_STATS, {"shared_http_requests": 1, "shared_http_reuses": 5})
        probe.reset_probe_cache()
        with patch.object(probe.requests, "get", side_effect=requests.Timeout("offline")) as get:
            for _ in range(3):
                with self.assertRaises(requests.Timeout):
                    probe.get("https://example.invalid/data")
        self.assertEqual(get.call_count, 1)

    def test_transport_failure_returns_dated_last_good_and_throttles_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"revision"
            path.write_text("v1")
            calls = []
            @observed_cache(paths=lambda: (path,))
            def source():
                calls.append(1)
                if len(calls) > 1:
                    raise requests.Timeout("offline")
                return pd.DataFrame({"observation_date": [pd.Timestamp("2026-10-27")], "close": [100.]})
            try:
                source()
                path.write_text("revision2")
                for _ in range(3):
                    stale = source()
                    self.assertEqual(stale.observation_date.iloc[0], pd.Timestamp("2026-10-27"))
                    self.assertTrue(stale.attrs["is_stale"])
                self.assertEqual(len(calls), 2)
            finally:
                source.clear()

    def test_hk_emergency_history_preserves_local_trading_dates_and_completed_bars(self):
        from macro_platform import hk_liquidity as hk
        days = [pd.Timestamp("2026-10-22 09:30", tz="Asia/Hong_Kong"),
                pd.Timestamp("2026-10-23 09:30", tz="Asia/Hong_Kong")]
        node = {"timestamp": [int(day.timestamp()) for day in days],
                "meta": {"exchangeTimezoneName": "Asia/Hong_Kong"},
                "indicators": {"quote": [{"close": [100, 102]}]}}
        response = Mock(); response.json.return_value = {"chart": {"result": [node]}}
        with patch.object(hk, "http_get", return_value=response) as get:
            frame = hk._market_monthly_close("0700.HK", "Tencent")
        self.assertEqual(frame.observation_date.dt.strftime("%Y-%m-%d").tolist(), ["2026-10-22", "2026-10-23"])
        self.assertEqual(get.call_args.kwargs["params"]["interval"], "1d")

    def test_vixeq_reader_excludes_future_and_nonfinite_closes(self):
        from macro_platform import us_equity_risk as risk
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"vixeq.json"
            path.write_text(json.dumps({"records": [
                {"observation_date": "2026-10-22", "close": 40},
                {"observation_date": "2026-10-23", "close": float("inf")},
                {"observation_date": "2099-01-01", "close": 41}]}))
            with patch.object(risk, "VIXEQ_SNAPSHOT_PATH", path):
                frame = risk.load_vixeq_snapshot()
        self.assertEqual(frame.observation_date.dt.strftime("%Y-%m-%d").tolist(), ["2026-10-22"])

    def test_tga_rejects_future_and_infinite_published_balances(self):
        from macro_platform.treasury_cash import parse_dts_tga_rows
        rows = [{"record_date": day, "account_type": "Treasury General Account Closing Balance",
                 "open_today_bal": value} for day, value in (
                     ("2026-10-22", 500000), ("2026-10-23", float("inf")), ("2099-01-01", 600000))]
        frame = parse_dts_tga_rows(rows)
        self.assertEqual(frame.observation_date.dt.strftime("%Y-%m-%d").tolist(), ["2026-10-22"])

    def test_japan_live_release_uses_same_admission_rules_as_snapshot(self):
        from macro_platform import asia_rates as asia
        csv = "title\n基準日,2年,10年\nR8.10.22,1,2\nR8.10.23,inf,2.1\n2099-01-01,1,2\n"
        response = Mock(content=csv.encode("cp932"))
        with patch.object(asia, "http_get", return_value=response):
            frame = asia._read_japan_csv(asia.JAPAN_CURRENT_URL)
        self.assertEqual(frame.observation_date.dt.strftime("%Y-%m-%d").tolist(), ["2026-10-22", "2026-10-23"])
        self.assertTrue(pd.isna(frame.japan_2y.iloc[-1]))
        self.assertTrue(pd.isna(frame.japan_10y_2y_pct.iloc[-1]))

    def test_quotes_reject_nonfinite_or_hours_ahead_timestamps(self):
        from test_accuracy_performance import helpers
        ns = helpers("app.py", {"_valid_market_timestamp"}, {"time": time})
        check = ns["_valid_market_timestamp"]
        now = time.time()
        self.assertAlmostEqual(check(now*1000), now, delta=1e-6)
        for invalid in (None, float("nan"), float("inf"), now+3600, 0):
            self.assertIsNone(check(invalid))

    def test_news_time_rejects_future_dates_and_preserves_prior_year(self):
        from data import _extract_time
        now = pd.Timestamp.now(tz="Asia/Hong_Kong")
        future = now+pd.Timedelta(days=2)
        self.assertEqual(_extract_time({"time": str(int(future.timestamp()))}), "")
        self.assertEqual(_extract_time({"time": future.strftime("%Y-%m-%d %H:%M:%S")}), "")
        self.assertEqual(_extract_time({"time": "2099-99-99 99:99:99"}), "")
        past = now-pd.DateOffset(years=1)
        self.assertTrue(_extract_time({"time": past.strftime("%Y-%m-%d %H:%M:%S")}).startswith(str(past.year)))

    def test_csi_probe_omits_only_the_apis_synthetic_left_boundary(self):
        from macro_platform.china_equity import completed_china_date
        end = completed_china_date()
        start = end-pd.Timedelta(days=45)
        rows = [{"indexCode": "000300", "indexNameCn": "沪深300", "tradeDate": day.strftime("%Y%m%d"),
                 "close": value} for day, value in ((start, 99999), (end, 4000))]
        response = Mock(); response.json.return_value = {"success": True, "data": rows}
        with patch.object(probe, "get", return_value=response):
            actual, url = probe.csindex("000300")
        self.assertEqual(actual, end.strftime("%Y-%m-%d"))


if __name__ == "__main__":
    unittest.main()
