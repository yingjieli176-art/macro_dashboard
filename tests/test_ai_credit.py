"""Credit history must retain actual dates, units, gaps and source distinctions."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from macro_platform import ai_credit as cds
from macro_platform.echarts_axes import build_adaptive_echarts_option, build_safe_echarts_option
from scripts.update_ai_cds_snapshot import refresh


def source():
    return {"built": "2026-10-28", "dates": ["2026-10-26", "2026-10-27", "2026-10-28"],
        "catalogue": [{"id": key, "unit": "bp", "label": "CDX IG 5y" if key == "cdx_ig5" else
                       label.replace("5Y", "5y CDS")} for key, (label, _) in cds.SERIES.items()],
        "series": {**{key: [100., None, 110.] for key in cds.SERIES}, "sn_nvidia": [100., 105., None],
                   "eq_px_nvidia": [200., 300., 400.]}}


class AiCreditTests(unittest.TestCase):
    def test_whitelists_only_cds_and_labels_implied_series(self):
        payload = cds.parse_source(source())
        self.assertEqual(set(payload["series"]), set(cds.SERIES))
        self.assertEqual(payload["series"]["sn_coreweave"]["quote_basis"], "upfront_implied")
        self.assertNotIn("eq_px_nvidia", payload["series"])
        self.assertIn("40% recovery", payload["methodology"])

    def test_rejects_wrong_measures_dates_nonfinite_and_truncated_calendars(self):
        for mutation in (lambda p: p["catalogue"][0].update(unit="usd"),
                         lambda p: p["catalogue"][0].update(label="Oracle swap price"),
                         lambda p: p["dates"].__setitem__(1, p["dates"][0]),
                         lambda p: p["dates"].__setitem__(2, "2099-01-01"),
                         lambda p: p["series"]["sn_oracle"].pop(),
                         lambda p: p["series"]["sn_oracle"].__setitem__(0, float("inf")),
                         lambda p: p["series"]["sn_oracle"].__setitem__(0, -2),
                         lambda p: p["series"]["sn_oracle"].__setitem__(0, True)):
            payload = source(); mutation(payload)
            with self.assertRaises((ValueError, TypeError)):
                cds.parse_source(payload)

    def test_latest_table_uses_each_names_own_last_actual_observation(self):
        table = cds.cds_summary(cds.parse_source(source())).set_index("公司 / 指数")
        self.assertEqual(table.loc["NVIDIA 5Y", "实际观测日"], "2026-10-27")
        self.assertEqual(table.loc["NVIDIA 5Y", "最新CDS（bp）"], 105.)
        self.assertEqual(table.loc["Oracle 5Y", "实际观测日"], "2026-10-28")

    def test_native_and_rescue_charts_keep_null_gaps_and_visible_isolated_observations(self):
        with patch.object(cds, "load_nvidia_cds", return_value=pd.DataFrame(columns=["tenor"])):
            for window in ("5Y", "1Y", "6M", "3M", "1M"):
                fig = cds.build_cds_figure(window, cds.parse_source(source()))
                self.assertEqual(len(fig.data), 6)
                self.assertTrue(all(t.connectgaps is False for t in fig.data))
                for adapter in (build_adaptive_echarts_option, build_safe_echarts_option):
                    option = adapter(fig, window)
                    oracle = next(s for s in option["series"] if s["name"] == "Oracle 5Y")
                    self.assertEqual([p[1] for p in oracle["data"]], [100., None, 110.])
                    self.assertTrue(oracle["showSymbol"])
                    self.assertFalse(oracle["connectNulls"])
                self.assertIn("NVIDIA 1Y · 待数据源", fig.layout.meta["missing_series"])

    def test_invalid_refresh_never_overwrites_last_good_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cds.json"
            refresh(source(), path); before = path.read_bytes()
            bad = source(); bad["series"]["sn_oracle"] = [100., None, None]
            with self.assertRaises(ValueError): refresh(bad, path)
            self.assertEqual(path.read_bytes(), before)
            bad = source(); bad["catalogue"][0]["unit"] = "usd"
            with self.assertRaises(ValueError): refresh(bad, path)
            self.assertEqual(path.read_bytes(), before)

    def test_correction_merges_real_history_without_forward_filling(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cds.json"
            refresh(source(), path)
            update = source(); update["built"] = "2026-10-29"; update["dates"].append("2026-10-29")
            for key in cds.SERIES: update["series"][key].append(120.)
            update["series"]["sn_oracle"][0] = None
            result = refresh(update, path)
            self.assertEqual([r["spread_bps"] for r in result["series"]["sn_oracle"]["records"]],
                             [100., None, 110., 120.])

    def test_real_snapshot_table_matches_last_actual_point_in_every_series(self):
        payload = cds.load_cds_snapshot()
        self.assertTrue(payload)
        table = cds.cds_summary().set_index("公司 / 指数")
        for key, (label, _) in cds.SERIES.items():
            actual = [r for r in payload["series"][key]["records"] if r["spread_bps"] is not None]
            self.assertEqual(table.loc[label, "最新CDS（bp）"], actual[-1]["spread_bps"])
            self.assertEqual(table.loc[label, "实际观测日"], actual[-1]["observation_date"])
            self.assertLessEqual(actual[-1]["observation_date"], payload["source_asof"])

    def test_freshness_probe_uses_independent_source_and_preserves_missing_1y(self):
        from scripts import probe_all_sources as probe
        jobs = {j[0]: j for j in probe.jobs()}
        self.assertIn("NVIDIA_CDS_1Y", jobs)
        with patch.object(probe, "get", return_value=type("Response", (), {"json": lambda self: source()})()):
            row = probe.check(jobs["NVIDIA_CDS_5Y"])
        self.assertEqual(row["source_latest"], "2026-10-27")
        self.assertEqual(row["status"], "source_behind_repository")


if __name__ == "__main__":
    unittest.main()
