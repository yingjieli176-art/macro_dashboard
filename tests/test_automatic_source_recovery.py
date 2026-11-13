"""Recovery must cover every stored audit feed and preserve validated history."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import pandas as pd

from scripts import refresh_audited_sources as recovery
from scripts import update_dxy_snapshot as dxy
from scripts import sync_fred_verified_cache as fred


class AutomaticRecoveryTests(unittest.TestCase):
    def test_every_stored_audited_feed_has_a_writer(self):
        from scripts.probe_all_sources import jobs
        covered = set().union(*recovery.FAMILIES.values())
        missing = [key for key, _, _, stored, _ in jobs() if stored is not None and key not in covered]
        self.assertEqual(missing, [], "New stored feeds must be wired into automatic recovery")
        for script in recovery.FAMILIES:
            self.assertTrue((recovery.ROOT / "scripts" / script).is_file(), script)

    def test_lag_missing_and_unverified_retry_but_current_and_live_only_feeds_do_not(self):
        report = {"sources": [{"id": key, "status": status} for key, status in (
            ("MOVE", "pipeline_lag"), ("SPX_GEX", "pipeline_lag"), ("DX-Y.NYB", "pipeline_lag"),
            ("CFTC_JPY_NONCOMM_NET", "live_only"), ("SPX_PCR", "unverified"),
            ("SPX", "at_source_latest"), ("RSP", "source_behind_repository"),
            ("BAMLC0A0CM", "live_only"), ("UNKNOWN", "pipeline_lag"))]}
        jobs, unhandled = recovery.recovery_plan(report)
        scripts = {name for name, _ in jobs}
        self.assertEqual(scripts, {"update_move_index.py", "update_dealer_gamma.py", "update_dxy_snapshot.py",
                                   "update_cftc_yen.py", "update_spx_put_call_snapshot.py"})
        self.assertEqual(unhandled, ["UNKNOWN"])

    def test_collector_failure_does_not_block_other_valid_updates(self):
        def run(args, **kwargs):
            if args[-1].endswith("update_move_index.py"):
                raise subprocess.TimeoutExpired(args, 240)
        report = {"sources": [{"id": key, "status": "pipeline_lag"} for key in ("MOVE", "SPX_GEX")]}
        result = recovery.recover(report, run=run)
        self.assertEqual({r["script"]: r["status"] for r in result["collectors"]},
                         {"update_move_index.py": "collector_failed", "update_dealer_gamma.py": "collector_completed"})

    def test_dxy_preserves_older_history_and_rejects_regression_holes_and_invalid_values(self):
        def frame(days, values):
            return pd.DataFrame({"observation_date": pd.to_datetime(days), "close": values})
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "dxy.json"
            initial = frame(["2026-11-05", "2026-11-06", "2026-11-09"], [100, 101, 102])
            self.assertTrue(dxy.save_snapshot(initial, path))
            self.assertFalse(dxy.save_snapshot(initial, path))
            self.assertTrue(dxy.save_snapshot(frame(["2026-11-06", "2026-11-09", "2026-11-10"], [101, 102, 103]), path))
            before = path.read_bytes()
            self.assertEqual(len(json.loads(before)["records"]), 4)
            for bad in (frame(["2026-11-06", "2026-11-09"], [101, 102]),
                        frame(["2026-11-06", "2026-11-10"], [101, 103]),
                        frame(["2026-11-10"], [float("inf")]), frame(["2099-01-01"], [100])):
                with self.assertRaises(ValueError):
                    dxy.save_snapshot(bad, path)
                self.assertEqual(path.read_bytes(), before)

    def test_dxy_rejects_wrong_product_and_frequency(self):
        for meta in ({"symbol": "DXY", "instrumentType": "INDEX", "dataGranularity": "1d"},
                     {"symbol": dxy.SYMBOL, "instrumentType": "INDEX", "dataGranularity": "1wk"}):
            with self.assertRaisesRegex(ValueError, "identity or frequency"):
                dxy.parse_history({"chart": {"result": [{"meta": meta}]}})

    def test_audit_live_history_fallback_is_independent_of_stored_date(self):
        from scripts import probe_all_sources as probe
        from requests import HTTPError
        response = Mock()
        node = {"meta": {"symbol": "^MOVE", "instrumentType": "INDEX", "exchangeTimezoneName": "UTC"},
                "timestamp": [pd.Timestamp("2026-11-10T12:00Z").timestamp()],
                "indicators": {"quote": [{"close": [80]}]}}
        response.json.return_value = {"chart": {"result": [node]}}
        with patch.dict(sys.modules, {"curl_cffi": None}), patch.object(probe, "get", side_effect=HTTPError("429")), \
             patch.object(probe.requests, "get", return_value=response), patch.object(probe.time, "sleep"):
            self.assertEqual(probe.yahoo("^MOVE")[0], "2026-11-10")
            node["meta"]["symbol"] = "OTHER"
            with self.assertRaises(RuntimeError):
                probe.yahoo("^MOVE")

    def test_fred_publication_holiday_is_not_a_permanent_grace_period(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(fred, "OUT", Path(folder)):
            records = [{"date": day.strftime("%Y-%m-%d"), "value": 3.9}
                       for day in pd.bdate_range(end="2026-11-10", periods=20)]
            Path(folder, "SOFR.json").write_text(json.dumps({"series_id": "SOFR", "coverage_end": "2026-11-10", "records": records}))
            self.assertEqual(fred.snapshot_health("SOFR", "2026-11-13")["status"], "available")
            self.assertEqual(fred.snapshot_health("SOFR", "2026-11-16")["status"], "stale")


if __name__ == "__main__":
    unittest.main()
