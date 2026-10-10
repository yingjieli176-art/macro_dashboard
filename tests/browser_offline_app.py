"""CI-only browser entry point. Real repository snapshots, external sources offline.

Never deploy this entry point. No synthetic observations are inserted into charts.
"""
from pathlib import Path
import os
import runpy
from unittest.mock import patch

import requests

with patch.object(requests.sessions.Session, "request", side_effect=requests.Timeout("offline browser acceptance")), \
     patch("urllib.request.urlopen", side_effect=OSError("offline browser acceptance")):
    root = Path(os.environ.get("MACRO_ACCEPTANCE_APP_ROOT", str(Path(__file__).resolve().parents[1]))).resolve()
    # The isolated rollback CI job runs the complete restored Git tree.
    import sys
    sys.path.insert(0, str(root))
    os.chdir(root)
    runpy.run_path(str(root / "app.py"), run_name="__main__")
