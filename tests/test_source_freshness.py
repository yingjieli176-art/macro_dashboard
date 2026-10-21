"""Prevent authentic old or differently measured observations looking fresh."""
from datetime import date
from pathlib import Path
import json
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from macro_platform.echarts_axes import option_observation_health
from scripts.update_copper_snapshot import parse_cme_stocks, SHORT_TON_TO_METRIC_TONNE
from scripts.update_hkma_daily_snapshot import parse_hkab_latest
from scripts import update_hkma_snapshot
from scripts.audit_source_freshness import audit


def cme_frame(activity="10/16/2026", total=791679, unit="Short Tons"):
    return pd.DataFrame([
        ["COPPER - HIGH GRADE", None, "Report Date: 10/19/2026"],
        [unit, None, "Activity Date: " + activity],
        ["DELIVERY POINT", "PREV TOTAL", "TOTAL TODAY"],
        ["Total Registered (warranted)", 470921, 470921],
        ["Total Eligible (non-warranted)", 319465, 320758],
        ["TOTAL COPPER", 790386, total],
    ])


class SourceFreshnessTests(unittest.TestCase):
    def test_audit_checks_field_dates_instead_of_snapshot_download_time(self):
        reports = audit(now="2026-10-20")
        copper = next(r for r in reports if r["file"] == "copper_market_daily.json")
        root = Path(__file__).resolve().parents[1]
        payload = json.loads((root / "data_snapshots/copper_market_daily.json").read_text())
        expected = max(row["date"] for row in payload["records"] if row.get("comex_stock_t") is not None)
        self.assertEqual(copper["latest_by_name"]["comex_stock_t"], expected)
        old = audit(now=pd.Timestamp(expected) + pd.DateOffset(months=6))
        self.assertIn("comex_stock_t", next(r for r in old if r["file"] == copper["file"])["stale_names"])

    def test_cme_uses_activity_date_and_converts_short_tons(self):
        row = parse_cme_stocks(cme_frame(), date(2026, 10, 20))
        self.assertEqual(row["date"], "2026-10-16")
        self.assertEqual(row["comex_stock_short_tons"], 791679)
        self.assertAlmostEqual(row["comex_stock_t"], 791679 * SHORT_TON_TO_METRIC_TONNE)
        self.assertNotEqual(row["comex_stock_t"], 791679)

    def test_cme_bad_unit_wrong_total_and_future_activity_are_rejected(self):
        for frame in (cme_frame(unit="Ounces"), cme_frame(total=800000),
                      cme_frame(activity="10/21/2026")):
            with self.subTest(frame=frame.to_dict()), self.assertRaises(ValueError):
                parse_cme_stocks(frame, date(2026, 10, 20))

    def test_hkab_preserves_dated_pair_and_does_not_use_other_tenors(self):
        html = """<h2>Rates as at 11:15a.m.</h2><p>Hong Kong Time on 2026-10-20.</p>
        <div>Overnight <b>2.33411</b></div><div>1 Month 2.70446</div>
        <div>3 Months <b>3.28536</b></div><div>Historical Rates 2026</div>"""
        row = parse_hkab_latest(html, date(2026, 10, 20))
        self.assertEqual(row["end_of_date"], "2026-10-20")
        self.assertEqual(row["hibor_3m"], 3.28536)
        self.assertEqual(row["hibor_overnight"], 2.33411)
        for bad in (html.replace("3 Months", "6 Months"), html.replace("2026-10-20", "2099-10-20")):
            with self.assertRaises(ValueError):
                parse_hkab_latest(bad, date(2026, 10, 20))

    def test_monthly_publication_lag_and_market_overlay_have_separate_rules(self):
        option = {"series": [
            {"name": "M2 YoY", "data": [["2026-08-31", 5.2]]},
            {"name": "Tencent Price (R1)", "data": [["2026-09-30", 500]]},
        ]}
        report = option_observation_health(option, chart_key="hk_5_range", now="2026-10-20")
        self.assertEqual(report["stale_names"], ["Tencent Price (R1)"])
        self.assertEqual(report["monthly_names"], ["M2 YoY"])
        report = option_observation_health(option, chart_key="hk_5_range", now="2026-11-10")
        self.assertIn("M2 YoY", report["stale_names"])
        self.assertIn("2026-08-31", report["stale_details"][0])

    def test_newer_null_nonfinite_or_bad_dates_do_not_hide_real_staleness(self):
        report = option_observation_health({"series": [{"name": "COMEX 库存", "data": [
            ["2026-09-30", 500], ["2026-10-20", None], ["2026-10-21", float("inf")],
            ["bad-date", 600], ["2026-10-22", float("nan")]]}]}, now="2026-10-20")
        self.assertEqual(report["latest_by_name"], {"COMEX 库存": "2026-09-30"})
        self.assertEqual(report["stale_names"], ["COMEX 库存"])
        self.assertFalse(report["future_names"])

    def test_sparse_optional_hibor_cannot_block_verified_monthly_money(self):
        months = pd.date_range(end="2026-09-01", periods=78, freq="MS")
        existing = {d.strftime("%Y-%m"): {"end_of_month": d.strftime("%Y-%m"),
                    "m2_hkd": 9000000, "m3_hkd": 9100000, "monetary_base_total": 2000000,
                    "aggr_balance": 50000, "outstanding_efbn": 1300000,
                    "ow_lb_bf_disc_win": 1100000} for d in months}
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(update_hkma_snapshot, "OUT", Path(folder) / "snapshot.json"), \
             patch.object(update_hkma_snapshot, "load_existing", return_value=existing), \
             patch.object(update_hkma_snapshot, "fetch_monetary_history", return_value=[
                 {"end_of_month": "2026-09", "hibor_fixing_3m": 3.2}]), \
             patch.object(update_hkma_snapshot, "fetch_monetary_base_history", return_value=[]):
            update_hkma_snapshot.main()
            self.assertTrue(update_hkma_snapshot.OUT.exists())

    def test_data_publisher_retries_a_real_push_race_without_erasing_other_source(self):
        import os
        root = Path(__file__).resolve().parents[1]
        git = shutil.which("git")
        def run(args, cwd):
            return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            remote, seed, worker, other = [folder / n for n in ("remote.git", "seed", "worker", "other")]
            run([git, "init", "--bare", "--initial-branch=main", str(remote)], folder)
            run([git, "clone", str(remote), str(seed)], folder)
            for repo in (seed,):
                run([git, "config", "user.name", "Test"], repo)
                run([git, "config", "user.email", "test@example.invalid"], repo)
            (seed / "baseline.json").write_text('{}')
            run([git, "add", "."], seed); run([git, "commit", "-m", "baseline"], seed)
            run([git, "push", "origin", "main"], seed)
            for repo in (worker, other):
                run([git, "clone", str(remote), str(repo)], folder)
                run([git, "config", "user.name", "Test"], repo)
                run([git, "config", "user.email", "test@example.invalid"], repo)
            for repo, name in ((worker, "first.json"), (other, "second.json")):
                (repo / name).write_text('{"observed":true}')
                run([git, "add", name], repo); run([git, "commit", "-m", name], repo)
            binpath = folder / "bin"; binpath.mkdir()
            marker = folder / "raced"
            wrapper = binpath / "git"
            wrapper.write_text('#!/usr/bin/env python3\nimport subprocess,sys\nfrom pathlib import Path\n'
                f'git={git!r}\nmarker=Path({str(marker)!r})\n'
                'if len(sys.argv)>1 and sys.argv[1]=="push" and not marker.exists():\n'
                ' marker.touch()\n'
                f' subprocess.run([git,"push","origin","main"],cwd={str(other)!r},check=True,capture_output=True)\n'
                'raise SystemExit(subprocess.call([git]+sys.argv[1:]))\n')
            wrapper.chmod(0o755)
            env = dict(os.environ, PATH=str(binpath) + os.pathsep + os.environ['PATH'])
            result = subprocess.run(['bash', str(root / 'scripts/push_snapshot.sh')], cwd=worker,
                                    env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(marker.exists())
            self.assertEqual(run([git, 'show', 'main:first.json'], remote).stdout, '{"observed":true}')
            self.assertEqual(run([git, 'show', 'main:second.json'], remote).stdout, '{"observed":true}')


    def test_daily_warns_after_two_weekdays_but_weekly_keeps_its_cadence(self):
        points = [["2026-10-16", 1.0]]
        report = option_observation_health({"series": [
            {"name": "10Y", "data": points},
            {"name": "Reserve Balances (R1)", "data": points},
        ]}, now="2026-10-21")
        self.assertEqual(report["stale_names"], ["10Y"])
        self.assertEqual(report["due_by_name"]["10Y"], "2026-10-20")
        self.assertEqual(report["cadence_by_name"]["Reserve Balances (R1)"], "周频")
        monday = option_observation_health({"series": [{"name": "VIX", "data": points}]}, now="2026-10-19")
        self.assertFalse(monday["stale_names"])

    def test_hkab_can_advance_when_a_historical_endpoint_times_out(self):
        from scripts import update_hkma_daily_snapshot as updater
        today = pd.Timestamp.now(tz="UTC").date()
        records = [{"end_of_date": d.strftime("%Y-%m-%d"), "hibor_overnight": 2.1,
                    "hibor_3m": 3.1, "closing_balance": 54000}
                   for d in pd.date_range(end=pd.Timestamp(today)-pd.Timedelta(days=1), periods=350)]
        html = f"Rates as at 11:15a.m. Hong Kong Time on {today.isoformat()}. Overnight 2.2 3 Months 3.2 Historical Rates"
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)/"daily.json"
            output.write_text(json.dumps({"records": records}))
            with patch.object(updater, "OUT", output), \
                 patch.object(updater, "_fetch_recent_pages", side_effect=RuntimeError("transport timed out")) as fetch, \
                 patch.object(updater, "_optional_latest", return_value=[]), \
                 patch.object(updater, "_fetch_bytes", return_value=html.encode()):
                updater.main()
            payload = json.loads(output.read_text())
            self.assertEqual(payload["records"][-1]["end_of_date"], today.isoformat())
            self.assertEqual(payload["records"][-1]["hibor_3m"], 3.2)
            self.assertEqual(len(payload["records"]), 351)
            self.assertEqual(len(payload["source_errors"]), 3)
            self.assertEqual((today - fetch.call_args.args[2]).days, 30)

    def test_market_audit_does_not_silently_accept_a_missing_required_symbol(self):
        from scripts import audit_source_freshness as checker
        original = checker.json.loads
        def missing_hstech(text, *args, **kwargs):
            data = original(text, *args, **kwargs)
            if isinstance(data.get("series"), dict) and "HSTECH" in data["series"]:
                data["series"].pop("HSTECH")
            return data
        with patch.object(checker.json, "loads", side_effect=missing_hstech):
            report = next(r for r in checker.audit(now="2026-10-21") if r["file"] == "hk_market_daily.json")
        self.assertEqual(report["missing_names"], ["HSTECH"])



    def test_monthly_backup_retains_main_updates_when_live_transport_fails(self):
        from scripts import update_censtat_money_supply as backup
        from io import BytesIO
        rows = [{"end_of_month": d.strftime("%Y-%m"), "m2_hkd": 100, "m3_hkd": 101}
                for d in pd.date_range(end="2026-08-01", periods=72, freq="MS")]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "data_snapshots").mkdir()
            (root / "data_snapshots/hkma_monetary_statistics.json").write_text(json.dumps({"records": rows}))
            out = root / "data_snapshots/backup.json"
            with patch.object(backup, "ROOT", root), patch.object(backup, "OUT", out), \
                 patch.object(backup.urllib.request, "urlopen", return_value=BytesIO(b'{"dataSet": []}')), \
                 patch.object(update_hkma_snapshot, "_fetch_proxy_records", side_effect=RuntimeError("timeout")):
                backup.main()
            data = json.loads(out.read_text())
            self.assertEqual(data["coverage_end"], "2026-08")
            self.assertEqual(data["record_count"], 72)
            self.assertFalse(data["fresh_fetch_ok"])
            self.assertEqual(data["fetch_error"], "timeout")


    def test_original_treasury_source_advances_fred_mirror_without_losing_history(self):
        from scripts import sync_fred_verified_cache as sync
        from unittest.mock import Mock
        previous = [{"date": d.strftime("%Y-%m-%d"), "value": 4.1}
                    for d in pd.date_range(end="2026-10-19", periods=20)]
        xml = '<feed xmlns:m="urn:m" xmlns:d="urn:d"><m:properties><d:NEW_DATE>2026-10-20T00:00:00</d:NEW_DATE><d:BC_10YEAR>4.20</d:BC_10YEAR></m:properties></feed>'
        response = Mock(text=xml)
        session = Mock()
        session.get.return_value = response
        with tempfile.TemporaryDirectory() as folder, patch.object(sync, "OUT", Path(folder)):
            (Path(folder)/"DGS10.json").write_text(json.dumps({"records": previous}))
            actual = sync._fetch_treasury(session, "DGS10")
        self.assertEqual(len(actual), 21)
        self.assertEqual(actual.iloc[-1]["date"], pd.Timestamp("2026-10-20"))
        self.assertEqual(actual.iloc[-1]["value"], 4.2)
        self.assertIn("home.treasury.gov", session.get.call_args.args[0])

    def test_original_cboe_close_keeps_source_date_and_correct_index(self):
        from scripts import sync_fred_verified_cache as sync
        from unittest.mock import Mock
        csv = "DATE,OPEN,HIGH,LOW,CLOSE\n" + "\n".join(
            f"{d:%m/%d/%Y},15,20,12,18.5" for d in pd.date_range(end="2026-10-20", periods=20))
        session = Mock()
        session.get.return_value = Mock(text=csv)
        actual = sync._fetch_primary(session, "VXVCLS")
        self.assertEqual(actual.iloc[-1]["date"], pd.Timestamp("2026-10-20"))
        self.assertEqual(actual.iloc[-1]["value"], 18.5)
        self.assertTrue(session.get.call_args.args[0].endswith("/VIX3M_History.csv"))

if __name__ == "__main__":
    unittest.main()
