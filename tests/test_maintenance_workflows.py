"""Guard stable runtime against obsolete GitHub Actions auto-patching it.

This is a structural workflow regression test, not a network test.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

HISTORICAL_MIGRATIONS = (
    "upgrade-hk-chart5-2-daily.yml",
    "upgrade-us-tga-freshness.yml",
    "add-hk-market-history-fallback.yml",
    "upgrade-hk-market-terminal.yml",
    "add-hsi-to-hk-overlays.yml",
    "refine-hk-money-trend-momentum.yml",
    "migrate-chart5-platform-core.yml",
    "add-us-equity-risk-chart.yml",
)
OFFICIAL_REFRESHES = (
    "update-hkma-daily-snapshot.yml",
    "update-hkma-snapshot.yml",
    "update-hkma-base-rate-history.yml",
    "update-hk-market-daily.yml",
    "update-copper-snapshot.yml",
    "sync-fred-verified-cache.yml",
    "sync-tga-official-snapshot.yml",
    "update-vixeq-snapshot.yml",
)


def workflow_events(filename):
    """Extract top-level events, ignoring in-job 'on'/'schedule' strings."""
    content = (WORKFLOWS / filename).read_text(encoding="utf-8")
    match = re.search(r"(?m)^on:\s*\n(.*?)(?=^[A-Za-z_][\w-]*:|\Z)", content, re.S | re.M)
    if match is None:
        raise AssertionError(f"No workflow trigger block: {filename}")
    events = set()
    for line in match.group(1).splitlines():
        event = re.match(r"^  ([a-z][\w_-]*):", line)
        if event:
            events.add(event.group(1))
    return events, content


class WorkflowSafetyTests(unittest.TestCase):
    def test_obsolete_code_migrations_are_never_automatic(self):
        for name in HISTORICAL_MIGRATIONS:
            with self.subTest(workflow=name):
                events, content = workflow_events(name)
                self.assertEqual(events, {"workflow_dispatch"})
                self.assertIn("permissions:", content)

    def test_verified_data_updaters_remain_scheduled_and_do_not_write_app_code(self):
        for name in OFFICIAL_REFRESHES:
            with self.subTest(workflow=name):
                events, content = workflow_events(name)
                self.assertIn("schedule", events, name)
                self.assertIn("workflow_dispatch", events, name)
                self.assertIn("data_snapshots/", content)
                self.assertNotRegex(
                    content, r"(?m)^\s*git add\s+(?:app\.py|data\.py|macro_platform/)",
                )

    def test_runtime_contract_is_not_accidentally_removed(self):
        app = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("CHART_BUILD = ", app)
        for number in range(1, 14):
            self.assertIn(f"render_macro_chart_{number}(", app)
        self.assertIn("_macro_snapshot_revision", app)
        self.assertIn("_safe_hk_bundle", app)
        self.assertIn("_build_macro_figures_parallel", app)
        data = (ROOT / "data.py").read_text(encoding="utf-8")
        self.assertIn("parse_dts_tga_rows", data)
        self.assertIn("read_verified_tga_snapshot", data)


if __name__ == "__main__":
    unittest.main()
