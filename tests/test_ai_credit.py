"""Credit history must retain actual dates, units, gaps and source distinctions."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
import requests

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
    def test_selected_five_exclude_retired_names_equity_prices_and_one_year(self):
        raw = source()
        raw["series"]["eq_px_nebius"] = [150., 160., 170.]
        raw["series"]["sn_nebius"] = [200., 210., 220.]
        raw["catalogue"].append({"id": "sn_nebius", "label": "Nebius 5y CDS", "unit": "bp"})
        payload = cds.parse_source(raw)
        expected = ["NVIDIA 5Y", "AMD 5Y", "Alphabet 5Y（谷歌）", "Microsoft 5Y（微软）", "Oracle 5Y"]
        self.assertEqual(cds.cds_summary(payload)["公司 / 指数"].tolist(), expected)
        fig = cds.build_cds_figure(payload=payload)
        self.assertEqual([trace.name for trace in fig.data], expected)
        self.assertFalse(fig.layout.meta["missing_series"])
        self.assertEqual(set(payload["series"]), set(cds.SERIES))

    def test_coverage_uses_actual_priced_days_and_each_companys_date(self):
        table = cds.cds_summary(cds.parse_source(source())).set_index("公司 / 指数")
        self.assertEqual(table.loc["NVIDIA 5Y", "观测数"], 2)
        self.assertEqual(table.loc["NVIDIA 5Y", "源日历天数"], 3)
        self.assertEqual(table.loc["NVIDIA 5Y", "源日历覆盖率（%）"], 66.7)
        self.assertEqual(table.loc["NVIDIA 5Y", "距源截止日（天）"], 1)
        self.assertEqual(table.loc["Alphabet 5Y（谷歌）", "实际观测日"], "2026-10-28")

    def test_company_name_still_rejects_equity_price_descriptor(self):
        raw = source()
        next(row for row in raw["catalogue"] if row["id"] == "sn_alphabet")["unit"] = "usd"
        with self.assertRaises(ValueError):
            cds.parse_source(raw)

    def test_whitelists_only_selected_corporate_cds(self):
        payload = cds.parse_source(source())
        self.assertEqual(set(payload["series"]), set(cds.SERIES))
        self.assertEqual(payload["series"]["sn_microsoft"]["quote_basis"], "source_aggregate")
        self.assertNotIn("eq_px_nvidia", payload["series"])
        self.assertIn("Five selected corporate", payload["methodology"])

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
        for window in ("5Y", "1Y", "6M", "3M", "1M"):
            fig = cds.build_cds_figure(window, cds.parse_source(source()))
            self.assertEqual(len(fig.data), len(cds.SERIES))
            self.assertTrue(all(t.connectgaps is False for t in fig.data))
            for adapter in (build_adaptive_echarts_option, build_safe_echarts_option):
                option = adapter(fig, window)
                oracle = next(s for s in option["series"] if s["name"] == "Oracle 5Y")
                self.assertEqual([p[1] for p in oracle["data"]], [100., None, 110.])
                self.assertTrue(oracle["showSymbol"])
                self.assertFalse(oracle["connectNulls"])
            self.assertNotIn("NVIDIA 1Y · 待数据源", fig.layout.meta["missing_series"])

    def test_hy_oas_retains_percent_values_and_its_own_calendar_and_axis(self):
        payload = cds.parse_source(source())
        hy_oas = pd.DataFrame({"observation_date": pd.to_datetime(["2026-10-24", "2026-10-29"]),
                               "oas_pct": [3.12, 3.48]})
        for window in ("5Y", "1Y", "6M", "3M", "1M"):
            fig = cds.build_cds_figure(window, payload, hy_oas=hy_oas)
            for adapter in (build_adaptive_echarts_option, build_safe_echarts_option):
                option = adapter(fig, window)
                self.assertEqual(len(option["series"]), 6)
                *companies, oas = option["series"]
                self.assertTrue(all(series["yAxisIndex"] == 0 for series in companies))
                self.assertEqual(oas["name"], cds.HY_OAS_NAME)
                self.assertEqual(oas["yAxisIndex"], 1)
                self.assertEqual(oas["data"], [["2026-10-24T00:00:00", 3.12], ["2026-10-29T00:00:00", 3.48]])
                self.assertEqual(option["yAxis"][1]["name"], "R1 · %")
                self.assertEqual(option["dataZoom"][0]["endValue"], "2026-10-29T00:00:00")
        missing = cds.build_cds_figure(payload=payload, hy_oas=hy_oas.iloc[:0])
        self.assertEqual(len(missing.data), 5)
        self.assertEqual(missing.layout.meta["missing_series"], [cds.HY_OAS_NAME])

    def test_hy_oas_reads_validated_fred_observations_without_persisting(self):
        import data
        response = requests.Response()
        response.status_code = 200
        response._content = b"observation_date,BAMLH0A0HYM2\n2026-10-26,3.12\n2026-10-27,\n2026-10-28,3.48\n"
        with patch.object(data, "http_get", return_value=response) as fetch, \
             patch.object(data, "_save_fred_success") as save:
            frame = data.get_hy_oas.__wrapped__()
        self.assertEqual(fetch.call_args.kwargs["params"], {"id": "BAMLH0A0HYM2"})
        self.assertEqual(frame.observation_date.dt.strftime("%Y-%m-%d").tolist(), ["2026-10-26", "2026-10-28"])
        self.assertEqual(frame.oas_pct.tolist(), [3.12, 3.48])
        save.assert_not_called()
        with patch.object(data, "http_get", side_effect=requests.Timeout):
            self.assertTrue(data.get_hy_oas.__wrapped__().empty)

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
            self.assertTrue(actual)
            self.assertEqual(table.loc[label, "最新CDS（bp）"], actual[-1]["spread_bps"])
            self.assertEqual(table.loc[label, "实际观测日"], actual[-1]["observation_date"])
            self.assertLessEqual(actual[-1]["observation_date"], payload["source_asof"])

    def test_freshness_probe_uses_independent_source_and_omits_retired_tenors(self):
        from scripts import probe_all_sources as probe
        jobs = {j[0]: j for j in probe.jobs()}
        self.assertNotIn("NVIDIA_CDS_1Y", jobs)
        with patch.object(probe, "get", return_value=type("Response", (), {"json": lambda self: source()})()):
            row = probe.check(jobs["NVIDIA_CDS_5Y"])
        self.assertEqual(row["source_latest"], "2026-10-27")
        self.assertEqual(row["status"], "source_behind_repository")


if __name__ == "__main__":
    unittest.main()
