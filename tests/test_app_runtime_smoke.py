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
        self.assertEqual(len(second.get('button_group')), 18)
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
        self.assertEqual(len(instance.get("button_group")), 18)
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
            for index, axis in enumerate(option["yAxis"]):
                bars = any(s["type"] == "bar" and s["yAxisIndex"] == index for s in option["series"])
                self.assertEqual(axis["scale"], not bars)
            self.assertTrue(all(zoom["filterMode"] == "filter" for zoom in option["dataZoom"]))
        self.assertEqual(len(instance.radio), 0)
        drawdown = next(json.loads(spec) for spec in specs if 'SPX' in spec)
        self.assertEqual([series["name"] for series in drawdown["series"]],
                         ["SPX（标普500市值加权）", "RSP（标普500等权ETF）"])
        china = next(json.loads(spec) for spec in specs
                     if any(series["name"] == "沪深300" for series in json.loads(spec)["series"]))
        self.assertEqual([series["name"] for series in china["series"]], ["沪深300", "中证1000", "中证2000"])
        self.assertFalse(any("距前高跌幅" in element.value.columns for element in instance.dataframe))
        # Market assets retain their original unit and independent price axes.
        spec_text = " ".join(specs)
        treasury = next(json.loads(spec) for spec in specs if '"30Y"' in spec)
        thirty = next(series for series in treasury["series"] if series["name"] == "30Y")
        self.assertEqual(thirty["yAxisIndex"], 0)
        self.assertTrue(any(point[1] is not None for point in thirty["data"]))
        risk = next(json.loads(spec) for spec in specs if 'COR3M (R3)' in spec)
        risk_series = {series["name"]: series for series in risk["series"]}
        self.assertEqual(len(risk["yAxis"]), 4)
        self.assertFalse(any("COR1M" in name or "VIXEQ−VIX" in name for name in risk_series))
        for name in ("COR3M (R3)", "VIXEQ/VIX (R2)"):
            self.assertIn(name, risk_series)
            self.assertTrue(any(point[1] is not None for point in risk_series[name]["data"]))
        self.assertNotIn("Rebased", spec_text)
        carry = next(json.loads(spec) for spec in specs if 'JPY 20-session appreciation (R2)' in spec)
        self.assertEqual(len(carry["yAxis"]), 4)
        self.assertEqual([series["name"] for series in carry["series"]],
                         ["US−Japan 2Y spread", "USD/JPY (R1)", "JPY 20-session appreciation (R2)", "CFTC JPY speculative net (R3)"])
        self.assertEqual([series["yAxisIndex"] for series in carry["series"]], [0, 1, 2, 3])
        self.assertEqual(carry["series"][-1]["type"], "bar")
        money = next(json.loads(spec) for spec in specs if '"M2 MoM"' in spec)
        self.assertEqual(next(s for s in money["series"] if s["name"] == "M2 MoM")["type"], "bar")
        self.assertTrue(all(any(point[1] is not None for point in series["data"]) for series in carry["series"]))
        self.assertNotIn("起点100", spec_text)



if __name__ == "__main__":
    unittest.main()

