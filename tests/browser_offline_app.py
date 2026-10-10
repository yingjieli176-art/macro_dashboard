"""CI-only browser entry point. Real repository snapshots, external sources offline.

Never deploy this entry point. No synthetic observations are inserted into charts.
"""
from pathlib import Path
import runpy
from unittest.mock import patch

import requests

with patch.object(requests.sessions.Session, "request", side_effect=requests.Timeout("offline browser acceptance")), \
     patch("urllib.request.urlopen", side_effect=OSError("offline browser acceptance")):
    runpy.run_path(str(Path(__file__).resolve().parents[1] / "app.py"), run_name="__main__")
