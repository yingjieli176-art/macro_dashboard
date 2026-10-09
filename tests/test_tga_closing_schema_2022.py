"""True Treasury DTS TGA fixings across the April 2022 schema change."""
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd

from macro_platform.treasury_cash import parse_dts_tga_rows, read_verified_tga_snapshot
from scripts.sync_tga_daily_snapshot import fetch_latest_official


class Treasury2022SchemaTests(unittest.TestCase):
    def test_named_tga_close_uses_different_field_across_2022_change(self):
        rows = [
            {"record_date": "2022-04-15",
             "account_type": "Treasury General Account (TGA) Closing Balance",
             "close_today_bal": "510000", "open_today_bal": "500000"},
            {"record_date": "2022-04-18",
             "account_type": "Treasury General Account (TGA) Closing Balance",
             "close_today_bal": None, "open_today_bal": "520000"},
            {"record_date": "2026-10-08",
             "account_type": "Treasury General Account (TGA) Closing Balance",
             "close_today_bal": None, "open_today_bal": "750000"},
            {"record_date": "2026-10-08",
             "account_type": "Total Operating Balance",
             "close_today_bal": "900000", "open_today_bal": "880000"},
        ]
        parsed = parse_dts_tga_rows(rows).set_index("observation_date")
        self.assertEqual(len(parsed), 3)
        self.assertAlmostEqual(parsed.loc[pd.Timestamp("2022-04-15"), "TGA_DAILY"], .510)
        self.assertAlmostEqual(parsed.loc[pd.Timestamp("2022-04-18"), "TGA_DAILY"], .520)
        self.assertAlmostEqual(parsed.loc[pd.Timestamp("2026-10-08"), "TGA_DAILY"], .750)

    def test_ordinary_opening_balance_is_never_labeled_as_closing(self):
        rows = [
            {"record_date": "2026-10-08",
             "account_type": "Treasury General Account Opening Balance",
             "open_today_bal": "900000", "close_today_bal": None},
            {"record_date": "2026-10-08",
             "account_type": "Total Operating Balance",
             "open_today_bal": "600000", "close_today_bal": None},
        ]
        self.assertTrue(parse_dts_tga_rows(rows).empty)

    def test_actual_closing_total_is_allowed_if_primary_label_missing(self):
        rows = [
            {"record_date": "2026-10-08", "account_type": "Total Operating Balance",
             "open_today_bal": "700000", "close_today_bal": "720000"},
        ]
        frame = parse_dts_tga_rows(rows)
        self.assertAlmostEqual(frame.TGA_DAILY.iloc[0], .720)
        self.assertEqual(frame.attrs["total_operating_fallback_dates"], 1)

    def test_verified_snapshot_can_cold_start_without_fabrication(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "treasury_tga_daily.json"
            observations = [
                {"record_date": f"2026-10-{i:02d}",
                 "account_type": "Treasury General Account (TGA) Closing Balance",
                 "open_today_bal": str(700000 + 1000*i),
                 "close_today_bal": None}
                for i in range(1, 9)
            ]
            path.write_text(json.dumps({
                "source": "U.S. Treasury Daily Treasury Statement",
                "fetched_at": int(time.time()),
                "coverage_end": "2026-10-08",
                "records": observations,
            }), encoding="utf-8")
            result = read_verified_tga_snapshot(path)
            self.assertEqual(len(result), 8)
            self.assertFalse(result.attrs["is_stale"])
            self.assertAlmostEqual(result.TGA_DAILY.iloc[-1], 0.708)
            path.write_text(path.read_text().replace(
                '"coverage_end": "2026-10-08"', '"coverage_end": "2026-10-01"'
            ), encoding="utf-8")
            self.assertTrue(read_verified_tga_snapshot(path).empty)

    def test_synced_official_rows_need_recent_observation(self):
        now = pd.Timestamp.now().normalize()
        data = [{
            "record_date": (now - pd.Timedelta(days=i)).strftime("%Y-%m-%d"),
            "account_type": "Treasury General Account (TGA) Closing Balance",
            "open_today_bal": str(700000 + i),
            "close_today_bal": None,
        } for i in range(35)]
        response = Mock()
        response.json.return_value = {"data": data}
        response.raise_for_status.return_value = None
        session = Mock()
        session.get.return_value = response
        raw, parsed = fetch_latest_official(session)
        self.assertEqual(len(parsed), 35)
        self.assertTrue(all("Closing Balance" in r["account_type"] for r in raw))
        self.assertEqual(raw[-1]["record_date"], now.strftime("%Y-%m-%d"))


if __name__ == "__main__":
    unittest.main()
