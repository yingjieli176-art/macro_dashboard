"""Failure/recovery and real Git race coverage for unattended US refreshes."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

import pandas as pd
import requests
from scripts import refresh_us_sources as refresh
from scripts import publish_source_refresh as publisher
from scripts import update_tail_risk_snapshot as tail
from scripts import sync_fred_verified_cache as fred


class AutomaticUSRefreshTests(unittest.TestCase):
    def test_failed_family_does_not_block_others_and_supplement_runs_last(self):
        called = []
        def run(args, **kwargs):
            name = Path(args[1]).name
            called.append(name)
            if name == "sync_fred_verified_cache.py":
                raise subprocess.TimeoutExpired(args, 360)
            return Mock(returncode=0)
        results = refresh.collect(["update_equity_risk_snapshot.py", "sync_fred_verified_cache.py", "update_srf_usage.py"], run)
        self.assertEqual(results["sync_fred_verified_cache.py"], 124)
        self.assertEqual(results["update_srf_usage.py"], 0)
        self.assertEqual(called[-1], "update_equity_risk_snapshot.py")

    def test_success_exit_with_lag_still_retries_and_outages_are_not_ignored(self):
        outcomes = dict.fromkeys(refresh.COLLECTORS, 0)
        scripts = refresh.retry_collectors(outcomes, [
            {"id": "DGS10", "status": "pipeline_lag"},
            {"id": "SPX_PCR", "status": "unverified"},
            {"id": "SKEW", "status": "at_source_latest"}])
        self.assertIn("sync_fred_verified_cache.py", scripts)
        self.assertIn("update_spx_put_call_snapshot.py", scripts)
        self.assertNotIn("update_tail_risk_snapshot.py", scripts)

    def test_future_announced_iorb_does_not_poison_observed_history(self):
        dates = pd.date_range(end=pd.Timestamp.now(tz="UTC").tz_localize(None).normalize(), periods=15)
        text = "Time Period,RESBM_N.D\n" + "\n".join(f"{d:%Y-%m-%d},3.65" for d in dates) + "\n2099-01-01,3.5"
        session = Mock(); session.get.return_value.text = text
        frame = fred._fetch_primary(session, "IORB")
        self.assertEqual(len(frame), 15)
        self.assertEqual(frame.date.max(), dates.max())

    def test_tail_risk_csv_timeout_still_appends_official_history(self):
        now = datetime(2026, 11, 11, 1, tzinfo=timezone.utc)
        previous = {"symbol": "VVIX", "records": [{"observation_date": "2026-11-09", "close": 110.}]}
        get = Mock(side_effect=[requests.Timeout(), Mock(**{"json.return_value": {
            "symbol": "_VVIX", "timestamp": "2026-11-11 00:09:00",
            "data": [{"date": "2026-11-10", "close": 111.}]}})])
        with tempfile.TemporaryDirectory() as folder, patch.object(tail, "ROOT", Path(folder)):
            path = Path(folder) / "data_snapshots/vvix_daily.json"
            path.parent.mkdir(); path.write_text(json.dumps(previous))
            tail.refresh_one("VVIX", now, get)
            self.assertEqual(json.loads(path.read_text())["records"][-1]["close"], 111.)

    def test_new_published_spxo_aggregate_keeps_its_explicit_identity(self):
        from macro_platform.spx_options import parse_daily
        product = "SPX + SPXW + SPXO"
        row = parse_daily({"ratios": [{"name": product + " PUT/CALL RATIO", "value": 1.11}],
                           product: [{"name": "VOLUME", "call": 2928697, "put": 3256609, "total": 6185306}]},
                          "2026-11-09", datetime(2026, 11, 11, tzinfo=timezone.utc))
        self.assertEqual(row["product"], product)
        self.assertEqual(row["ratio"], 1.11)

    def test_concurrent_fred_dates_merge_and_upstream_revision_wins(self):
        dates = pd.date_range("2026-10-01", periods=15)
        records = [{"date": f"{d:%Y-%m-%d}", "value": 3.} for d in dates]
        remote = {"series_id": "EFFR", "records": records, "coverage_end": records[-1]["date"]}
        local = dict(remote, records=records + [{"date": "2026-10-16", "value": 3.1}], coverage_end="2026-10-16")
        remote["records"] = [dict(r) for r in records]
        remote["records"][-1]["value"] = 2.9
        result = json.loads(publisher.merge_fred_snapshot("data_snapshots/fred_cache/EFFR.json",
                            json.dumps(local).encode(), json.dumps(remote).encode()))
        self.assertEqual(result["records"][-2]["value"], 2.9)
        self.assertEqual(result["records"][-1]["date"], "2026-10-16")

    def test_bad_copper_family_does_not_change_saved_history(self):
        from scripts.refresh_copper_current import merge_frame
        records = {"2026-11-09": {"date": "2026-11-09", "wti_usd_bbl": 60.}}
        candidate = {d: dict(r) for d, r in records.items()}
        with self.assertRaises(ValueError):
            merge_frame(candidate, pd.DataFrame([{"date": "2099-01-01", "wti_usd_bbl": 61.}]),
                        now="2026-11-11")
        self.assertEqual(records["2026-11-09"]["wti_usd_bbl"], 60.)

    def test_real_parallel_snapshot_publication_keeps_both_new_dates(self):
        def git(root, *args):
            return subprocess.run(["git", *args], cwd=root, capture_output=True, check=True, text=True).stdout
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); remote = root / "remote.git"
            git(root, "init", "--bare", "--initial-branch=main", str(remote))
            seed = root / "seed"; git(root, "clone", str(remote), str(seed))
            for repo in [seed]:
                git(repo, "config", "user.name", "Test"); git(repo, "config", "user.email", "test@example.invalid")
            name = "data_snapshots/fred_cache/EFFR.json"
            def save(repo, end):
                records = [{"date": f"{d:%Y-%m-%d}", "value": 3.} for d in pd.date_range("2026-10-01", end)]
                path = repo / name; path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(dict(series_id="EFFR", coverage_end=end, records=records)))
            save(seed, "2026-10-15"); git(seed, "add", "."); git(seed, "commit", "-m", "seed"); git(seed, "push", "origin", "main")
            worker = root / "worker"; git(root, "clone", str(remote), str(worker))
            git(worker, "config", "user.name", "Test"); git(worker, "config", "user.email", "test@example.invalid")
            save(worker, "2026-10-17")
            save(seed, "2026-10-16"); git(seed, "add", "."); git(seed, "commit", "-m", "other collector"); git(seed, "push", "origin", "main")
            publisher.publish(worker, audit=lambda _: None)
            payload = json.loads(git(remote, "show", "main:" + name))
            self.assertEqual(payload["coverage_end"], "2026-10-17")
            self.assertEqual(len(payload["records"]), 17)


if __name__ == "__main__":
    unittest.main()
