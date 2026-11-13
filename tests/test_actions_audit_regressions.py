"""Regressions reproduced from November 11/12 Actions failures."""
from contextlib import redirect_stdout
from datetime import datetime, timezone
from io import StringIO
import unittest
from unittest.mock import Mock

import pandas as pd

from macro_platform.echarts_axes import option_observation_health
from scripts.audit_source_freshness import federal_publication_health
from scripts.sync_fred_verified_cache import _fetch_primary, _parse_source
from scripts.update_spx_put_call_snapshot import refresh


class ActionsAuditRegressions(unittest.TestCase):
    def test_federal_holiday_cadence_preserves_real_dates_and_eventual_failure(self):
        option = {"series": [{"name": "TGA_DAILY", "data": [["2026-11-09", .922633]]}]}
        original = option_observation_health(option, now="2026-11-12")
        self.assertEqual(original["stale_names"], ["TGA_DAILY"])
        corrected = federal_publication_health(original, "2026-11-12")
        self.assertEqual(corrected["due_by_name"]["TGA_DAILY"], "2026-11-12")
        self.assertEqual(corrected["latest_by_name"]["TGA_DAILY"], "2026-11-09")
        self.assertEqual(corrected["stale_names"], [])
        overdue = federal_publication_health(option_observation_health(option, now="2026-11-13"), "2026-11-13")
        self.assertEqual(overdue["stale_names"], ["TGA_DAILY"])
        # A market close keeps its original exchange-agnostic warning; federal
        # publication exceptions must not alter all chart calendars globally.
        self.assertEqual(option_observation_health(option, now="2026-11-12")["stale_names"], ["TGA_DAILY"])

    def test_federal_cadence_cannot_hide_future_date(self):
        option = {"series": [{"name": "SOFR", "data": [["2026-11-13", 3.9]]}]}
        health = federal_publication_health(option_observation_health(option, now="2026-11-12"), "2026-11-12")
        self.assertEqual(health["future_names"], ["SOFR"])

    def test_prates_omits_future_effective_rows_but_generic_admission_rejects_them(self):
        today = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
        dates = pd.date_range(today - pd.Timedelta(days=20), today + pd.Timedelta(days=1))
        text = "Time Period,RESBM_N.D\n" + "\n".join(f"{d:%Y-%m-%d},3.9" for d in dates)
        session = Mock()
        session.get.return_value.text = text
        result = _fetch_primary(session, "IORB")
        self.assertEqual(result.date.max(), today)
        self.assertEqual(len(result), 21)
        self.assertTrue(result.value.eq(3.9).all())
        with self.assertRaisesRegex(ValueError, "future"):
            _parse_source(text.replace("Time Period,RESBM_N.D", "DATE,IORB"), "IORB")

    def test_unchanged_spx_history_still_exposes_rejected_new_reports(self):
        days = pd.bdate_range(end="2026-11-06", periods=750)
        rows = [{"observation_date": f"{d:%Y-%m-%d}", "ratio": 1.0} for d in days]
        saved = {row["observation_date"]: row for row in rows}
        previous = {"records": rows}
        def fetch(day, now):
            if day > "2026-11-06":
                raise ValueError("Explicit SPX + SPXW ratio and volume rows required")
            return saved.get(day)
        output = StringIO()
        with redirect_stdout(output):
            result = refresh(previous, datetime(2026, 11, 11, 20, tzinfo=timezone.utc), fetch=fetch)
        self.assertIsNone(result)
        self.assertEqual(previous["records"], rows)
        self.assertIn("SPX report rejected: 2026-11-09", output.getvalue())
        self.assertIn("SPX report rejected: 2026-11-10", output.getvalue())


if __name__ == "__main__":
    unittest.main()
