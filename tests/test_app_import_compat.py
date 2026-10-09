"""Regression tests for startup imports when Streamlit Cloud has mixed revisions."""
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

ISOLATED_STARTUP_CHECK = r"""
import builtins
import pathlib
import sys
import types

source = pathlib.Path("app.py").read_text(encoding="utf-8")
startup = source.split("st.set_page_config(", 1)[0]
assert "import macro_platform.echarts_axes as _echarts_axes" in startup
mode = sys.argv[1]

if mode == "absent":
    original_import = builtins.__import__
    def broken_optional_import(name, *args, **kwargs):
        if name == "macro_platform.echarts_axes":
            raise ImportError("simulated missing echarts module")
        return original_import(name, *args, **kwargs)
    builtins.__import__ = broken_optional_import
elif mode == "old":
    import macro_platform
    stub = types.ModuleType("macro_platform.echarts_axes")
    stub.build_adaptive_echarts_option = lambda *_args: None
    sys.modules["macro_platform.echarts_axes"] = stub
    macro_platform.echarts_axes = stub
else:
    raise ValueError(mode)

context = {"__name__": "__main__", "__file__": "app.py"}
exec(compile(startup, "app.py", "exec"), context)
if mode == "absent":
    assert context["_echarts_axes"] is None
else:
    assert context["_echarts_axes"] is stub
    assert not hasattr(stub, "summarize_series_dates")
    assert not hasattr(stub, "expected_viewport_y_bounds")
print("PASS:", mode)
"""


class CloudImportCompatibility(unittest.TestCase):
    def _assert_startup_works(self, mode):
        result = subprocess.run(
            [sys.executable, "-c", ISOLATED_STARTUP_CHECK, mode],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=55,
            check=False,
        )
        self.assertEqual(
            result.returncode, 0,
            msg=f"mode={mode}\nstdout={result.stdout}\nstderr={result.stderr}",
        )
        self.assertIn(f"PASS: {mode}", result.stdout)

    def test_missing_optional_echarts_module(self):
        self._assert_startup_works("absent")

    def test_old_optional_echarts_module_missing_helpers(self):
        self._assert_startup_works("old")


if __name__ == "__main__":
    unittest.main()
