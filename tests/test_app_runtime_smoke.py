"""Offline end-to-end Streamlit script smoke check.

Network is deliberately disabled so a failing external market-data provider does
not mask a dashboard startup or widget-rendering regression.
"""
import unittest
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


if __name__ == "__main__":
    unittest.main()
