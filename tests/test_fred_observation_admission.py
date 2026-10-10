"""Live refreshes must not poison verified backups on an invalid success response."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import pandas as pd

import data
from scripts import sync_fred_verified_cache as sync

ROOT = Path(__file__).resolve().parents[1]


class FredObservationAdmission(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.sid = "IORB"
        payload = json.loads((ROOT / "data_snapshots/fred_cache/IORB.json").read_text())
        self.records = payload["records"][-20:]
        self.good = pd.DataFrame({
            "observation_date": pd.to_datetime([row["date"] for row in self.records]),
            self.sid: [row["value"] for row in self.records],
        })
        self.good.attrs.update({"source": "FRED graph CSV", "is_stale": False, "is_fallback": False})

    def test_invalid_live_success_preserves_disk_memory_and_then_recovers_without_clear(self):
        for defect in ("future", "infinity", "out_of_bounds"):
            with self.subTest(defect=defect), \
                 patch.object(data, "_FRED_SNAPSHOT_DIR", self.folder), \
                 patch.object(data, "_FRED_LAST_GOOD", {}), \
                 patch.object(data, "_FRED_REFRESH", Mock()):
                # Older and restored observations both come from the actual backup.
                previous = self.good.iloc[:-1].copy()
                data._save_fred_success(self.sid, previous)
                path = self.folder / "IORB.json"
                before = path.read_bytes()
                bad = self.good.copy()
                if defect == "future":
                    bad.loc[bad.index[-1], "observation_date"] = (
                        pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
                        + pd.Timedelta(days=1))
                else:
                    bad.loc[bad.index[-1], self.sid] = float("inf") if defect == "infinity" else 99.99
                # Warm the real revision-aware getter before the failure/recovery.
                pd.testing.assert_frame_equal(data.get_iorb(), previous)
                with patch.object(data, "_fetch_fred_graph", return_value=bad), \
                     patch.object(data, "_fetch_fred_api", side_effect=OSError("API unavailable")):
                    stale = data._refresh_fred_series(self.sid)
                self.assertTrue(stale.attrs["is_stale"])
                self.assertIn("ValueError", stale.attrs["fallback_reason"])
                pd.testing.assert_frame_equal(stale, previous)
                self.assertEqual(path.read_bytes(), before)
                self.assertNotIn(self.sid, data._FRED_LAST_GOOD)
                with patch.object(data, "_fetch_fred_graph", return_value=self.good.copy()):
                    data._refresh_fred_series(self.sid)
                recovered = data.get_iorb()
                pd.testing.assert_frame_equal(recovered, self.good)
                self.assertFalse(recovered.attrs["is_stale"])
                self.assertEqual(json.loads(path.read_text())["records"], self.records)

    def test_invalid_bundled_data_stays_unavailable_instead_of_entering_chart(self):
        path = self.folder / "IORB.json"
        invalid = {"series_id": self.sid, "records": [
            {"date": row["date"], "value": 99.99} for row in self.records]}
        path.write_text(json.dumps(invalid))
        with patch.object(data, "_FRED_SNAPSHOT_DIR", self.folder), \
             patch.object(data, "_FRED_LAST_GOOD", {}), \
             patch.object(data, "_FRED_REFRESH", Mock()):
            self.assertIsNone(data._read_fred_success(self.sid))
            self.assertTrue(data.get_iorb().attrs["unavailable"])

    def test_wrong_csv_series_is_rejected_and_api_can_restore_the_requested_series(self):
        csv = "DATE,SOFR\n" + "\n".join(
            f"{row['date']},{row['value']}" for row in self.records)
        response = Mock(text=csv)
        with patch.object(data, "_FRED_SNAPSHOT_DIR", self.folder), \
             patch.object(data, "_FRED_LAST_GOOD", {}), \
             patch.object(data, "http_get", return_value=response), \
             patch.object(data, "_fetch_fred_api", return_value=self.good.copy()) as api:
            with self.assertRaisesRegex(ValueError, "no IORB series"):
                data._fetch_fred_graph(self.sid)
            restored = data._refresh_fred_series(self.sid)
            api.assert_called_once_with(self.sid)
            pd.testing.assert_frame_equal(restored, self.good)

    def test_collector_and_health_report_reject_tomorrow_and_implausible_rates(self):
        for defect in ("future", "out_of_bounds"):
            records = [dict(row) for row in self.records]
            if defect == "future":
                records[-1]["date"] = (pd.Timestamp.now(tz="UTC")
                    + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            else:
                records[-1]["value"] = 99.99
            csv = "DATE,IORB\n" + "\n".join(
                f"{row['date']},{row['value']}" for row in records)
            with self.subTest(defect=defect), self.assertRaises(ValueError):
                sync._parse_source(csv, self.sid)
            (self.folder / "IORB.json").write_text(json.dumps({
                "series_id": self.sid, "records": records,
                "coverage_end": records[-1]["date"],
            }))
            with patch.object(sync, "OUT", self.folder):
                self.assertEqual(sync.snapshot_health(self.sid)["status"], "missing_or_invalid")


if __name__ == "__main__":
    unittest.main()
