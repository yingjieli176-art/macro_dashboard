from datetime import datetime, timezone
import unittest
from unittest.mock import Mock
import requests
from scripts.update_equity_risk_snapshot import refresh_payload

NOW = datetime(2026, 11, 11, 1, tzinfo=timezone.utc)


def response(symbol="VIXEQ", timestamp="2026-11-11 00:09:00"):
    return Mock(**{"json.return_value": {"symbol": "_" + symbol, "timestamp": timestamp,
        "data": [{"date": "2026-11-10", "close": 44.11}, {"date": "2026-11-11", "close": 99.}]}})


class EquityRiskRefreshTests(unittest.TestCase):
    def setUp(self):
        self.previous = {"symbol": "VIXEQ", "coverage_end": "2026-11-09", "updated_at": "old",
                         "records": [{"observation_date": "2026-11-09", "close": 43.9}]}

    def test_csv_is_not_required_and_transient_failure_retries(self):
        get = Mock(side_effect=[requests.Timeout(), response()])
        new = refresh_payload(self.previous, "VIXEQ", NOW, get)
        self.assertEqual(get.call_count, 2)
        self.assertEqual(new["records"], self.previous["records"] + [{"observation_date": "2026-11-10", "close": 44.11}])
        self.assertIn("charts/historical/_VIXEQ.json", new["latest_source_url"])
        self.assertEqual(self.previous["updated_at"], "old")

    def test_spx_retains_cache_schema_and_original_history(self):
        old = {"series_id": "SP500", "records": [{"date": "2026-11-09", "value": 7549.94}]}
        new = refresh_payload(old, "SPX", NOW, Mock(return_value=response("SPX")))
        self.assertEqual(new["records"][0], old["records"][0])
        self.assertEqual(new["records"][-1], {"date": "2026-11-10", "value": 44.11})
        self.assertEqual(new["series_id"], "SP500")

    def test_wrong_identity_incomplete_and_future_publications_do_not_update(self):
        for payload in (response("OTHER"), response(timestamp="2026-11-10 20:00:00"),
                        response(timestamp="2099-01-01 00:00:00")):
            self.assertIsNone(refresh_payload(self.previous, "VIXEQ", NOW, Mock(return_value=payload)))

    def test_aware_publication_offset_does_not_admit_intraday_close(self):
        # 16:00Z is 11:00 New York, before the closing publication cutoff.
        self.assertIsNone(refresh_payload(self.previous, "VIXEQ", NOW,
            Mock(return_value=response(timestamp="2026-11-10T23:00:00+07:00"))))

    def test_unchanged_snapshot_keeps_fetch_timestamp(self):
        old = dict(self.previous, records=[{"observation_date": "2026-11-10", "close": 44.11}])
        get = Mock()
        self.assertIsNone(refresh_payload(old, "VIXEQ", NOW, get))
        get.assert_not_called()
