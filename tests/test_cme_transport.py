"""Verify original CME downloads without changing inventory dates or units."""
from types import ModuleType
from unittest.mock import Mock, patch
import unittest
from scripts import update_copper_snapshot as updater
from test_source_freshness import cme_frame


class CmeTransportTests(unittest.TestCase):
    def test_browser_transport_reads_original_xls_when_standard_http_is_unavailable(self):
        fake = ModuleType("curl_cffi")
        fake.requests = Mock()
        fake.requests.get.return_value = Mock(content=b"original-workbook",
                                             headers={"last-modified": "Tue, 20 Oct 2026 19:04:58 GMT"})
        with patch.dict("sys.modules", {"curl_cffi": fake}), \
             patch.object(updater.pd, "read_excel", return_value=cme_frame(activity="10/19/2026")), \
             patch.object(updater, "_request", side_effect=RuntimeError("standard transport timed out")) as fallback:
            result = updater._fetch_cme_stocks()
        self.assertEqual(result["date"], "2026-10-19")
        self.assertEqual(result["comex_stock_source"], updater.CME_STOCKS_URL)
        self.assertAlmostEqual(result["comex_stock_t"], 791679 * updater.SHORT_TON_TO_METRIC_TONNE)
        self.assertEqual(fake.requests.get.call_args.args[0], updater.CME_STOCKS_URL)
        fallback.assert_not_called()

    def test_standard_transport_remains_a_fallback(self):
        fake = ModuleType("curl_cffi")
        fake.requests = Mock()
        fake.requests.get.side_effect = RuntimeError("alternate transport unavailable")
        response = Mock(content=b"original-workbook", headers={})
        with patch.dict("sys.modules", {"curl_cffi": fake}), \
             patch.object(updater.pd, "read_excel", return_value=cme_frame(activity="10/19/2026")), \
             patch.object(updater, "_request", return_value=response):
            result = updater._fetch_cme_stocks()
        self.assertEqual(result["date"], "2026-10-19")

    def test_transport_failure_is_explicit_and_does_not_create_an_observation(self):
        fake = ModuleType("curl_cffi")
        fake.requests = Mock()
        fake.requests.get.side_effect = RuntimeError("timeout")
        with patch.dict("sys.modules", {"curl_cffi": fake}), \
             patch.object(updater, "_request", side_effect=RuntimeError("timeout")):
            with self.assertRaisesRegex(RuntimeError, "transports failed"):
                updater._fetch_cme_stocks()
