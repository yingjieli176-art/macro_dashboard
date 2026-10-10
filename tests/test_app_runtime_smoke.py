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
    def test_fresh_session_can_render_warmed_shared_chart_caches(self):
        from scripts.benchmark_runtime import offline_http, offline_urlopen
        app = Path(__file__).resolve().parents[1] / 'app.py'
        with patch.object(requests.sessions.Session, 'request', new=offline_http), \
             patch('urllib.request.urlopen', new=offline_urlopen):
            first = AppTest.from_file(str(app), default_timeout=90).run()
            second = AppTest.from_file(str(app), default_timeout=90).run()
        self.assertFalse(first.exception)
        self.assertFalse(second.exception)
        self.assertEqual(len(second.get('button_group')), 13)
        self.assertGreaterEqual(len(second.get('echarts_chart')), 8)
        self.assertEqual([chart.proto.spec for chart in first.get('echarts_chart')],
                         [chart.proto.spec for chart in second.get('echarts_chart')])

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
        self.assertEqual(len(instance.radio), 0)
        # Market assets retain their original unit and independent price axes.
        spec_text = " ".join(chart.proto.spec for chart in native)
        self.assertNotIn("Rebased", spec_text)
        self.assertNotIn("起点100", spec_text)



if __name__ == "__main__":
    unittest.main()

