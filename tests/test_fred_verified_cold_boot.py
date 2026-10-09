"""Cold-start safety: preserve official observed FRED data, never fabricate data."""
import ast
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

import pandas as pd
import plotly.graph_objects as go

import data
from scripts import sync_fred_verified_cache as sync

ROOT = Path(__file__).resolve().parents[1]


def isolated_fred_reader(ns):
    tree = ast.parse((ROOT / "data.py").read_text(encoding="utf-8"))
    func = next(x for x in tree.body if isinstance(x, ast.FunctionDef)
                and x.name == "_fred_series")
    func.decorator_list = []
    exec(compile(ast.Module(body=[func], type_ignores=[]), "data.py", "exec"), ns)
    return ns["_fred_series"]


class FredVerifiedColdBootTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.sid = "IORB"
        self.rows = [{"date": "2026-09-30", "value": 3.6},
                     {"date": "2026-10-01", "value": 3.7}]
        self.t0 = int(time.time())
        self.file = self.folder / (self.sid + ".json")
        self.file.write_text(json.dumps({
            "series_id": self.sid, "fetched_at": self.t0,
            "records": self.rows,
        }), encoding="utf-8")

    def _source_reader(self):
        return isolated_fred_reader({
            "time": time, "pd": pd,
            "_read_fred_success": data._read_fred_success,
            "_fetch_fred_graph": Mock(side_effect=OSError("no network")),
            "_fetch_fred_api": Mock(side_effect=OSError("no network")),
            "_save_fred_success": Mock(),
            "_FRED_LOCK": threading.RLock(),
            "_FRED_LAST_GOOD": {},
        })

    def test_recent_bundled_official_fred_points_load_without_a_single_http_call(self):
        with patch.object(data, "_FRED_SNAPSHOT_DIR", self.folder):
            disk = data._read_fred_success(self.sid)
            self.assertEqual(list(disk[self.sid]), [3.6, 3.7])
            self.assertTrue(disk.attrs["is_stale"])
            self.assertEqual(disk.attrs["source"], "FRED persisted last-good")
            requests = [Mock(side_effect=AssertionError("network not needed")),
                        Mock(side_effect=AssertionError("network not needed"))]
            get = isolated_fred_reader({
                "time": time, "pd": pd,
                "_read_fred_success": data._read_fred_success,
                "_fetch_fred_graph": requests[0],
                "_fetch_fred_api": requests[1],
                "_save_fred_success": Mock(),
                "_FRED_LOCK": threading.RLock(), "_FRED_LAST_GOOD": {},
            })
            frame = get(self.sid)
            self.assertEqual(list(frame[self.sid]), [3.6, 3.7])
            for request in requests:
                request.assert_not_called()

    def test_old_bundle_falls_back_after_failed_live_request_without_filling_gaps(self):
        old = self.t0 - 5 * 86400
        self.file.write_text(json.dumps({
            "series_id": self.sid, "fetched_at": old,
            "records": [{"date": "2026-09-30", "value": 3.6},
                        {"date": "2026-10-02", "value": 3.8}],
        }), encoding="utf-8")
        with patch.object(data, "_FRED_SNAPSHOT_DIR", self.folder):
            get = self._source_reader()
            result = get(self.sid)
        self.assertEqual(len(result), 2)
        self.assertNotIn(pd.Timestamp("2026-10-01"),
                         list(result["observation_date"]))
        self.assertTrue(result.attrs["is_stale"])
        self.assertTrue(result.attrs["is_fallback"])

    def test_corrupt_snapshot_does_not_create_fabricated_source_samples(self):
        self.file.write_text("{not-json", encoding="utf-8")
        with patch.object(data, "_FRED_SNAPSHOT_DIR", self.folder):
            self.assertIsNone(data._read_fred_success(self.sid))
            get = self._source_reader()
            result = get(self.sid)
        self.assertTrue(result.empty)
        self.assertTrue(result.attrs["unavailable"])

    def test_official_csv_parser_preserves_dates_and_rejects_invalid_feed(self):
        dates = pd.date_range("2026-09-01", periods=20)
        csv = "DATE,IORB\n" + "\n".join(
            f"{day:%Y-%m-%d},{3.5 if i < 10 else 3.7}"
            for i, day in enumerate(dates)
        )
        parsed = sync._parse_source(csv, "IORB")
        self.assertEqual(len(parsed), 20)
        self.assertAlmostEqual(parsed["value"].iloc[-1], 3.7)
        self.assertEqual(parsed["date"].iloc[-1], dates[-1])
        with self.assertRaises(ValueError):
            sync._parse_source(csv.replace("3.7", "99.99"), "IORB")
        with self.assertRaises(ValueError):
            sync._parse_source("DATE,IORB\n2026-09-01,3.6", "IORB")

    def test_new_york_fed_official_rate_json_keeps_only_actual_trade_dates(self):
        dates = pd.date_range("2026-09-01", periods=20, freq="D")
        session = Mock()
        session.get.return_value.json.return_value = {
            "refRates": [
                {"effectiveDate": day.strftime("%Y-%m-%d"),
                 "percentRate": 3.63 + (i % 2) * 0.01}
                for i, day in enumerate(dates)
            ]
        }
        session.get.return_value.raise_for_status.return_value = None
        frame = sync._fetch_primary(session, "EFFR")
        self.assertEqual(len(frame), 20)
        self.assertEqual(frame.date.max(), pd.Timestamp("2026-09-20"))
        self.assertAlmostEqual(float(frame.value.iloc[0]), 3.63)

    def test_federal_reserve_iorb_csv_preserves_observed_dates(self):
        dates = pd.date_range("2026-09-01", periods=20, freq="D")
        csv = "\n".join(
            ["Metadata"] * 5 +
            ["Time Period,RESBM_N.D"] +
            [f"{day:%Y-%m-%d},{3.65 if i < 15 else 3.9}"
             for i, day in enumerate(dates)]
        )
        session = Mock()
        session.get.return_value.text = csv
        session.get.return_value.raise_for_status.return_value = None
        frame = sync._fetch_primary(session, "IORB")
        self.assertEqual(len(frame), 20)
        self.assertAlmostEqual(float(frame.value.iloc[-1]), 3.9)

    def test_failed_upstream_sync_keeps_existing_observed_snapshot_unchanged(self):
        before = self.file.read_bytes()
        with patch.object(sync, "OUT", self.folder), \
             patch.object(sync, "_fetch_primary", side_effect=OSError("no primary feed")), \
             patch.object(sync, "_fetch_csv", side_effect=OSError("no network")), \
             patch.object(sync, "_fetch_api", side_effect=OSError("no key")):
            series_id, payload, reason = sync.refresh_one(self.sid)
        self.assertEqual(series_id, self.sid)
        self.assertIsNone(payload)
        self.assertIn("no network", reason)
        self.assertEqual(self.file.read_bytes(), before)

    def test_chart1_can_render_from_four_real_source_snapshots_offline(self):
        chart = go.Figure()
        for sid in ("IORB", "RRPONTSYAWARD", "EFFR", "SOFR"):
            chart.add_trace(go.Scatter(
                x=["2026-09-30", "2026-10-01"],
                y=[3.6, 3.7], name=sid
            ))
        from macro_platform.echarts_axes import build_adaptive_echarts_option
        option = build_adaptive_echarts_option(chart, "1M")
        self.assertIsNotNone(option)
        self.assertEqual(len(option["series"]), 4)
        self.assertTrue(option["yAxis"][0]["scale"])
        self.assertTrue(all(z["filterMode"] == "filter" for z in option["dataZoom"]))


if __name__ == "__main__":
    unittest.main()
