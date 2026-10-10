"""Offline end-to-end Streamlit script smoke check.

Network is deliberately disabled so a failing external market-data provider does
not mask a dashboard startup or widget-rendering regression.
"""
import unittest
import json
from pathlib import Path
from unittest.mock import patch

import requests
from streamlit.testing.v1 import AppTest


class DashboardBootSmoke(unittest.TestCase):
    def test_full_dashboard_completes_when_sources_are_offline(self):
        app = Path(__file__).resolve().parents[1] / "app.py"
        with patch.object(requests.sessions.Session, "request", side_effect=requests.Timeout("offline CI")), \
             patch("urllib.request.urlopen", side_effect=OSError("offline CI")):
            instance = AppTest.from_file(str(app), default_timeout=90).run()
        self.assertFalse(
            instance.exception,
            msg="Streamlit app crashed during full script execution: "
                + "; ".join(str(error.message) for error in instance.exception),
        )
        self.assertEqual(len(instance.get("button_group")), 13)
        native = instance.get("echarts_chart")
        # AppTest does not execute browser JavaScript. This assertion proves
        # the real Streamlit renderer emitted native chart messages, rather
        # than merely surviving with missing data or Plotly fallbacks.
        self.assertGreaterEqual(len(native), 8)
        self.assertEqual(len(instance.get("plotly_chart")), 0)
        for chart in native:
            option = json.loads(chart.proto.spec)
            self.assertTrue(option["series"])
            self.assertTrue(any(point[1] is not None for series in option["series"]
                                for point in series["data"]))
            self.assertTrue(all(axis["scale"] for axis in option["yAxis"]))
            self.assertTrue(all(zoom["filterMode"] == "filter" for zoom in option["dataZoom"]))
        self.assertEqual({radio.key: radio.value for radio in instance.radio}, {
            "hk_5_range_market_mode": "Raw", "hk_8_range_market_mode": "Raw",
            "precious_metals_mode": "Rebased 100", "crypto_market_mode": "Rebased 100",
        })
        with patch.object(requests.sessions.Session, "request", side_effect=requests.Timeout("offline CI")):
            for key, value in (("hk_5_range_market_mode", "Rebased 100"),
                               ("hk_8_range_market_mode", "Rebased 100"),
                               ("precious_metals_mode", "Raw"),
                               ("crypto_market_mode", "Raw")):
                instance.radio(key=key).set_value(value).run()
                self.assertFalse(instance.exception, key)
                self.assertEqual(instance.radio(key=key).value, value)
                self.assertGreaterEqual(len(instance.get("echarts_chart")), 8)
                self.assertEqual(len(instance.get("plotly_chart")), 0)


if __name__ == "__main__":
    unittest.main()

