"""CI-only browser entry point. Real repository snapshots, external sources offline.

Never deploy this entry point. No synthetic observations are inserted into charts.
"""
from pathlib import Path
import os
import runpy
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from acceptance_offline import install

install()
root = Path(os.environ.get("MACRO_ACCEPTANCE_APP_ROOT", str(Path(__file__).resolve().parents[1]))).resolve()
# The isolated rollback CI job runs the complete restored Git tree.
sys.path.insert(0, str(root))
os.chdir(root)
runpy.run_path(str(root / "app.py"), run_name="__main__")
