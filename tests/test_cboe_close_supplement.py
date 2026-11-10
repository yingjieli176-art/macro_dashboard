from datetime import datetime, timezone
import unittest
from unittest.mock import Mock

import requests

from macro_platform.cboe_history import CHART_HISTORY, QUOTE, supplement_closes


NOW = datetime(2026, 11, 10, 0, 30, tzinfo=timezone.utc)
PREVIOUS = [{"observation_date": "2026-11-06", "close": 47.42}]


def response(payload):
    return Mock(spec=requests.Response, **{"json.return_value": payload})


class CboeCloseSupplementTests(unittest.TestCase):
    def test_lagging_csv_keeps_history_and_adds_only_completed_chart_closes(self):
        payload = {"symbol": "_VIXEQ", "timestamp": "2026-11-09 22:00:00", "data": [
            {"date": "2026-11-06", "close": "48.00"},
            {"date": "2026-11-09", "close": "43.90"},
            {"date": "2026-11-10", "close": "100.00"},
        ]}
        get = Mock(return_value=response(payload))
        records, url = supplement_closes(PREVIOUS, "VIXEQ", NOW, get)
        self.assertEqual(url, CHART_HISTORY.format("VIXEQ"))
        self.assertEqual(records, PREVIOUS + [{"observation_date": "2026-11-09", "close": 43.90}])
        payload["timestamp"] = "2026-11-09 20:00:00"
        self.assertEqual(supplement_closes(PREVIOUS, "VIXEQ", NOW, get), (PREVIOUS, None))

    def test_only_confirmed_vix_close_can_supplement_the_chart_history(self):
        quote = {"symbol": "_VIX", "data": {"symbol": "^VIX", "security_type": "index",
                 "current_price": 19.92, "close": 19.92, "last_trade_time": "2026-11-09T16:15:01"}}
        history = response({"symbol": "_VIX", "timestamp": "2026-11-09 22:00:00", "data": []})
        get = Mock(side_effect=[history, response(quote)])
        records, url = supplement_closes(PREVIOUS, "VIX", NOW, get)
        self.assertEqual(url, QUOTE.format("VIX"))
        self.assertEqual(records[-1], {"observation_date": "2026-11-09", "close": 19.92})
        quote["data"]["last_trade_time"] = "2026-11-09T15:00:00"
        get = Mock(side_effect=[history, response(quote)])
        self.assertEqual(supplement_closes(PREVIOUS, "VIX", NOW, get), (PREVIOUS, None))
