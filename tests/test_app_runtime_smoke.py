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


def chart_specs(app):
    return [json.dumps(json.loads(chart.proto.json)["option"], sort_keys=True)
            for chart in app.get("bidi_component")
            if chart.proto.component_name.endswith("macro_linked_chart")]


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
        self.assertEqual(len(second.get('button_group')), 14)
        self.assertGreaterEqual(len(chart_specs(second)), 8)
        self.assertEqual(chart_specs(first), chart_specs(second))

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
        self.assertEqual(len(instance.get("button_group")), 14)
        specs = chart_specs(instance)
        # AppTest does not execute browser JavaScript. This assertion proves
        # the real Streamlit renderer emitted native chart messages, rather
        # than merely surviving with missing data or Plotly fallbacks.
        self.assertGreaterEqual(len(specs), 8)
        self.assertEqual(len(instance.get("plotly_chart")), 0)
        for spec in specs:
            option = json.loads(spec)
            self.assertTrue(option["series"])
            self.assertTrue(any(point[1] is not None for series in option["series"]
                                for point in series["data"]))
            self.assertTrue(all(axis["scale"] for axis in option["yAxis"]))
            self.assertTrue(all(zoom["filterMode"] == "filter" for zoom in option["dataZoom"]))
        self.assertEqual(len(instance.radio), 0)
        # Market assets retain their original unit and independent price axes.
        spec_text = " ".join(specs)
        risk = next(json.loads(spec) for spec in specs if 'COR1M (R4)' in spec)
        risk_series = {series["name"]: series for series in risk["series"]}
        self.assertEqual(len(risk["yAxis"]), 5)
        for name in ("COR1M (R4)", "COR3M (R4)", "VIXEQ−VIX (R2)"):
            self.assertIn(name, risk_series)
            self.assertTrue(any(point[1] is not None for point in risk_series[name]["data"]))
        self.assertNotIn("Rebased", spec_text)
        self.assertNotIn("起点100", spec_text)



if __name__ == "__main__":
    unittest.main()

