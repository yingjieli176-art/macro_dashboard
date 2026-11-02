"""HKMA failover retains the official endpoint and validates the API response."""
import json
import unittest
from unittest.mock import Mock, patch

import requests

from scripts.update_hkma_snapshot import _fetch_proxy_records, MONETARY_BASE_URL


class HkmaTransportTests(unittest.TestCase):
    def test_http_origin_proxy_recovers_two_transport_timeouts(self):
        rows = [{"end_of_month": "2026-09", "aggr_balance_bf_disc_win": 54108}]
        response = Mock(text=json.dumps({"header": {"success": True}, "result": {"records": rows}}))
        with patch("scripts.update_hkma_snapshot.requests.get",
                   side_effect=[requests.Timeout("direct"), requests.Timeout("https origin"), response]) as get:
            self.assertEqual(_fetch_proxy_records(MONETARY_BASE_URL, {"pagesize": 15}), rows)
        urls = [call.args[0] for call in get.call_args_list]
        self.assertTrue(urls[0].startswith(MONETARY_BASE_URL))
        self.assertEqual(urls[2], urls[1].replace("r.jina.ai/https://", "r.jina.ai/http://", 1))
        self.assertIn("api.hkma.gov.hk/public/", urls[2])

    def test_fallback_never_accepts_unsuccessful_api_payload(self):
        response = Mock(text=json.dumps({"header": {"success": False, "err_msg": "Unavailable"}}))
        with patch("scripts.update_hkma_snapshot.requests.get", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "Unavailable"):
                _fetch_proxy_records(MONETARY_BASE_URL, {"pagesize": 15})
