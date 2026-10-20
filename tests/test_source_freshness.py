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


if __name__ == "__main__":
    unittest.main()
