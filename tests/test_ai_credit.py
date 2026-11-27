"""Credit history must retain actual dates, units, gaps and source distinctions."""
import copy
from datetime import date
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
import requests

from macro_platform import ai_credit as cds
from macro_platform import spacex_cds
from macro_platform.dashboard_layout import MACRO_DISPLAY_NUMBER
from macro_platform.echarts_axes import build_adaptive_echarts_option, build_safe_echarts_option
from scripts.update_ai_cds_snapshot import refresh, refresh_nvidia_issuer


def source():
    return {"built": "2026-10-28", "dates": ["2026-10-26", "2026-10-27", "2026-10-28"],
        "catalogue": [{"id": key, "unit": "bp", "label": "CDX IG 5y" if key == "cdx_ig5" else
                       ("CoreWeave 5y CDS (upfront-implied)" if key == "sn_coreweave" else label.replace("5Y", "5y CDS"))} for key, (label, _) in cds.SERIES.items()],
        "series": {**{key: [100., None, 110.] for key in cds.SERIES}, "sn_nvidia": [100., 105., None],
                   "eq_px_nvidia": [200., 300., 400.]}}


ISSUER_HTML = ("<p>Nvidia&#39;s five-year credit default swap last traded at "
               "<b>148 basis points</b> on 25 November 2026, on 5 five-year prints (12 in all tenors).</p>")


class AiCreditTests(unittest.TestCase):
    def test_newer_issuer_trade_uses_the_single_series_and_summary(self):
        payload = cds.parse_source(source())
        payload["nvidia_issuer_observation"] = cds.parse_nvidia_issuer_reference(ISSUER_HTML)
        self.assertEqual(payload["source_asof"], "2026-10-28")
        fig = cds.build_cds_figure(payload=payload, nvidia_1y=pd.DataFrame())
        traces = {trace.name: trace for trace in fig.data}
        self.assertEqual([name for name in traces if name.startswith("NVIDIA 5Y")], ["NVIDIA 5Y"])
        self.assertEqual(traces["NVIDIA 5Y"].x[-1], "2026-11-25")
        self.assertEqual(traces["NVIDIA 5Y"].y[-1], 148)
        self.assertIn("5 笔", traces["NVIDIA 5Y"].meta["observation_notes"]["2026-11-25"])
        summary = cds.cds_summary(payload, nvidia_1y=pd.DataFrame()).iloc[0]
        self.assertEqual(summary["实际观测日"], "2026-11-25")
        self.assertEqual(summary["最新CDS（bp）"], 148)
        self.assertEqual(summary["观测数"], 2)

    def test_issuer_refresh_survives_lagging_aggregate_and_deduplicates_when_it_catches_up(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "cds.json"
            original = source()
            refresh(original, path)
            reference = refresh_nvidia_issuer(ISSUER_HTML, path)
            self.assertEqual(reference["reported_trade_count"], 5)
            self.assertEqual(refresh(original, path)["nvidia_issuer_observation"], reference)
            self.assertEqual(refresh_nvidia_issuer(ISSUER_HTML.replace("25 November", "24 November"), path), reference)
            before = path.read_bytes()
            with self.assertRaises(ValueError):
                refresh_nvidia_issuer(ISSUER_HTML.replace("5 five-year", "0 five-year"), path)
            self.assertEqual(path.read_bytes(), before)

            updated = copy.deepcopy(original)
            updated["built"] = "2026-11-25"
            updated["dates"].append("2026-11-25")
            for values in updated["series"].values():
                values.append(None)
            updated["series"]["sn_nvidia"][-1] = 149
            result = refresh(updated, path)
            self.assertIsNone(cds.nvidia_issuer_reference(result))
            self.assertNotIn("nvidia_issuer_observation", result)
            self.assertIsNone(refresh_nvidia_issuer(ISSUER_HTML, path))

    def test_nvidia_backfill_preserves_primary_values_and_attribution_in_one_series(self):
        payload = cds.parse_source(source())
        payload["source_asof"] = "2026-11-19"
        payload["series"]["sn_nvidia"]["records"] = [
            {"observation_date": day, "spread_bps": bp} for day, bp in (
                ("2026-11-02", 135.), ("2026-11-03", None), ("2026-11-09", None),
                ("2026-11-12", None), ("2026-11-19", None),
            )
        ]
        original = copy.deepcopy(payload)
        fig = cds.build_cds_figure("1M", payload, nvidia_1y=pd.DataFrame())
        self.assertEqual(payload, original)
        for adapter in (build_adaptive_echarts_option, build_safe_echarts_option):
            traces = {trace["name"]: trace for trace in adapter(fig, "1M")["series"]}
            main = traces["NVIDIA 5Y"]
            self.assertEqual([point[1] for point in main["data"]], [135., None, 134., 139., 121., 124.])
            self.assertFalse(main["connectNulls"])
            self.assertEqual([name for name in traces if name.startswith("NVIDIA 5Y")], ["NVIDIA 5Y"])
            self.assertIn("补充成交", main["observationNotes"]["2026-11-09"])
            self.assertIn("盘中参考", main["observationNotes"]["2026-11-12"])
            self.assertNotIn("2026-11-02", main["observationNotes"])

    def test_oas_uses_newer_same_series_vintage_even_if_fred_csv_succeeds(self):
        import data
        sid = "BAMLH0A0HYM2"
        old = pd.DataFrame({"observation_date": pd.to_datetime(["2026-11-19"]), sid: [3.52]})
        new = pd.DataFrame({"observation_date": pd.to_datetime(["2026-11-20"]), sid: [3.68]})
        with patch.object(data, "completed_date", return_value=date(2026, 11, 20)), \
             patch.object(data, "_fetch_fred_graph", return_value=old), \
             patch.object(data, "_fetch_fred_api", side_effect=RuntimeError), \
             patch.object(data, "_fetch_alfred_graph", return_value=new):
            result = data._get_credit_oas(sid)
        self.assertEqual(result.oas_pct.tolist(), [3.68])

    def test_cdx_keeps_newer_actual_dates_without_filling_oas(self):
        raw = source()
        for key, (source_label, _, _, _) in cds.CDX_SERIES.items():
            raw["catalogue"].append({"id": key, "unit": "bp", "label": source_label})
            raw["series"][key] = [None, 100, 110]
        cdx = cds.parse_cdx_source(raw)
        less_recent = {key: rows[:-1] for key, rows in cdx.items()}
        self.assertEqual(cds.merge_cdx_history(cdx, less_recent), cdx)
        oas = pd.DataFrame({"observation_date": pd.to_datetime(["2026-10-27"]), "oas_pct": [3.5]})
        fig = cds.build_cds_figure(payload=cds.parse_source(raw), hy_oas=oas, cdx=cdx)
        option = build_adaptive_echarts_option(fig, "1M")
        curves = {series["name"]: series for series in option["series"]}
        self.assertEqual(curves[cds.HY_OAS_NAME]["data"][-1], ["2026-10-27T00:00:00", 3.5])
        for _, label, axis, _ in cds.CDX_SERIES.values():
            self.assertEqual(curves[label]["data"][-1], ["2026-10-28T00:00:00", 1.1])
            self.assertEqual(curves[label]["yAxisIndex"], axis)
        raw["catalogue"][-1]["unit"] = "price"
        with self.assertRaises(ValueError):
            cds.parse_cdx_source(raw)

    def test_spacex_uses_only_direct_spreads_on_five_year_new_trades(self):
        base = {
            "Action type": "NEWT", "Event type": "TRAD", "Original Dissemination Identifier": "",
            "Underlier ID-Leg 1": "8CA76V", "UPI FISN": "NA/CDS Corp SN Sr",
            "Notional currency-Leg 1": "USD", "Package indicator": "FALSE",
            "Execution Timestamp": "2026-11-17T18:00:00Z", "Expiration Date": "2031-12-20",
            "Spread-Leg 1": "0.0268", "Spread notation-Leg 1": "3",
        }
        variants = [
            {}, {"Spread-Leg 1": "264", "Spread notation-Leg 1": "4"},
            {"Expiration Date": "2029-12-20"}, {"Underlier ID-Leg 1": "other"},
            {"Spread-Leg 1": "", "Other payment amount": "365584"},
            {"Action type": "EROR", "Original Dissemination Identifier": "6"}, {},
        ]
        rows = [dict(base, **variant, **{"Dissemination Identifier": str(i)})
                for i, variant in enumerate(variants)]
        self.assertEqual(spacex_cds.daily_medians(rows, date(2026, 11, 20)), [
            {"observation_date": "2026-11-17", "spread_bps": 266., "trade_count": 2},
        ])

    def test_ig_and_hy_have_independent_percent_axes_and_observation_dates(self):
        hy = pd.DataFrame({'observation_date': pd.to_datetime(['2026-10-26', '2026-10-28']),
                           'oas_pct': [3.12, 3.48]})
        ig = pd.DataFrame({'observation_date': pd.to_datetime(['2026-10-27', '2026-10-29']),
                           'oas_pct': [.82, .91]})
        for window in ('5Y', '1Y', '6M', '3M', '1M'):
            fig = cds.build_cds_figure(window, cds.parse_source(source()), hy_oas=hy, ig_oas=ig)
            for adapter in (build_adaptive_echarts_option, build_safe_echarts_option):
                option = adapter(fig, window)
                curves = {s['name']: s for s in option['series']}
                self.assertEqual(curves[cds.IG_OAS_NAME]['yAxisIndex'], 2)
                self.assertEqual(curves[cds.HY_OAS_NAME]['yAxisIndex'], 1)
                self.assertEqual([p[1] for p in curves[cds.IG_OAS_NAME]['data']], [.82, .91])
                self.assertEqual([p[0][:10] for p in curves[cds.IG_OAS_NAME]['data']], ['2026-10-27', '2026-10-29'])
                self.assertEqual([p[0][:10] for p in curves[cds.HY_OAS_NAME]['data']], ['2026-10-26', '2026-10-28'])
                self.assertFalse(curves[cds.IG_OAS_NAME]['connectNulls'])
                self.assertEqual(option['yAxis'][1]['name'], 'R1 · %')
                self.assertEqual(option['yAxis'][2]['name'], 'R2 · %')
                self.assertTrue(option['yAxis'][1]['scale'] and option['yAxis'][2]['scale'])
        missing = cds.build_cds_figure(payload=cds.parse_source(source()), hy_oas=hy, ig_oas=ig.iloc[:0])
        self.assertIn(cds.IG_OAS_NAME, missing.layout.meta['missing_series'])
        self.assertIn(cds.HY_OAS_NAME, [t.name for t in missing.data])

    def test_ig_keeps_r2_label_when_hy_is_unavailable(self):
        ig = pd.DataFrame({'observation_date': pd.to_datetime(['2026-10-27', '2026-10-28']),
                           'oas_pct': [.82, .91]})
        fig = cds.build_cds_figure(payload=cds.parse_source(source()), ig_oas=ig)
        self.assertEqual(next(t for t in fig.data if t.name == cds.IG_OAS_NAME).yaxis, 'y3')
        for adapter in (build_adaptive_echarts_option, build_safe_echarts_option):
            option = adapter(fig, '1Y')
            curve = next(s for s in option['series'] if s['name'] == cds.IG_OAS_NAME)
            self.assertEqual(option['yAxis'][curve['yAxisIndex']]['name'], 'R2 · %')

    def test_ig_loader_requests_exact_fred_identity_and_does_not_persist(self):
        import data
        response = requests.Response()
        response.status_code = 200
        response._content = b'observation_date,BAMLC0A0CM\n2026-10-26,0.82\n2026-10-27,.\n2026-10-28,0.91\n'
        with patch.object(data, 'http_get', return_value=response) as fetch, \
             patch.object(data, '_save_fred_success') as save:
            result = data.get_ig_oas.__wrapped__()
        self.assertEqual(fetch.call_args_list[0].kwargs['params'], {'id': 'BAMLC0A0CM'})
        self.assertEqual(result.oas_pct.tolist(), [.82, .91])
        self.assertEqual(result.observation_date.dt.strftime('%Y-%m-%d').tolist(), ['2026-10-26', '2026-10-28'])
        save.assert_not_called()
        with patch.object(data, 'http_get', side_effect=requests.Timeout):
            self.assertTrue(data.get_ig_oas.__wrapped__().empty)
        response._content = response.content.replace(b'BAMLC0A0CM', b'BAMLH0A0HYM2')
        with patch.object(data, 'http_get', return_value=response), patch.object(data, 'FRED_API_KEY', ''):
            self.assertTrue(data.get_ig_oas.__wrapped__().empty)

    def test_ig_probe_retains_live_only_status_without_committing_feed_history(self):
        import data
        from scripts import probe_all_sources as probe
        job = next(j for j in probe.jobs() if j[0] == 'BAMLC0A0CM')
        frame = pd.DataFrame({'observation_date': pd.to_datetime(['2026-10-28']), 'oas_pct': [.91]})
        with patch.object(data, '_get_credit_oas', return_value=frame):
            row = probe.check(job)
        self.assertEqual(row['source_latest'], '2026-10-28')
        self.assertEqual(row['status'], 'live_only')
        self.assertEqual(row['source_url'], cds.IG_OAS_URL)
        self.assertEqual(row['charts'], [MACRO_DISPLAY_NUMBER["nvidia_cds"]])

    def test_chart_eight_excludes_other_issuers_and_equity_prices(self):
        raw = source()
        raw["series"]["eq_px_nebius"] = [150., 160., 170.]
        raw["series"]["sn_nebius"] = [200., 210., 220.]
        raw["catalogue"].append({"id": "sn_nebius", "label": "Nebius 5y CDS", "unit": "bp"})
        payload = cds.parse_source(raw)
        expected = ["NVIDIA 5Y", "AMD 5Y", "Alphabet 5Y（谷歌）", "Microsoft 5Y（微软）", "Amazon 5Y（亚马逊）"]
        self.assertEqual(cds.cds_summary(payload)["公司 / 指数"].tolist(), [*expected, cds.NVIDIA_1Y_NAME])
        fig = cds.build_cds_figure(payload=payload)
        self.assertEqual([trace.name for trace in fig.data], expected)
        self.assertEqual(fig.layout.meta["missing_series"], [cds.NVIDIA_1Y_NAME])
        self.assertEqual(set(payload["series"]), set(cds.SERIES))

    def test_nvidia_1y_uses_its_own_quotes_and_left_bp_axis(self):
        quotes = pd.DataFrame({
            "observation_date": pd.to_datetime(["2026-10-25", "2026-10-27", "2026-10-29"]),
            "tenor": ["1Y", "5Y", "1Y"],
            "spread_bps": [19., 95., 21.],
        })
        payload = cds.parse_source(source())
        with patch.object(cds, "load_nvidia_cds", return_value=quotes):
            summary = cds.cds_summary(payload).set_index("公司 / 指数")
            fig = cds.build_cds_figure(payload=payload)
        row = summary.loc[cds.NVIDIA_1Y_NAME]
        self.assertEqual(row["实际观测日"], "2026-10-29")
        self.assertEqual(row["最新CDS（bp）"], 21.)
        self.assertEqual(row["观测数"], 2)
        self.assertTrue(pd.isna(row["源日历覆盖率（%）"]))
        self.assertNotIn(cds.NVIDIA_1Y_NAME, fig.layout.meta["missing_series"])
        for adapter in (build_adaptive_echarts_option, build_safe_echarts_option):
            option = adapter(fig, "5Y")
            series = next(item for item in option["series"] if item["name"] == cds.NVIDIA_1Y_NAME)
            self.assertEqual(series["yAxisIndex"], 0)
            self.assertEqual(series["data"], [["2026-10-25T00:00:00", 19.], ["2026-10-29T00:00:00", 21.]])

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
        self.assertEqual(payload["series"]["sn_coreweave"]["quote_basis"], "upfront_implied")

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
        self.assertEqual(table.loc["AMD 5Y", "实际观测日"], "2026-10-28")

    def test_native_and_rescue_charts_keep_null_gaps_and_visible_isolated_observations(self):
        for window in ("5Y", "1Y", "6M", "3M", "1M"):
            fig = cds.build_cds_figure(window, cds.parse_source(source()))
            self.assertEqual(len(fig.data), len(cds.CREDIT_SERIES))
            self.assertTrue(all(t.connectgaps is False for t in fig.data))
            for adapter in (build_adaptive_echarts_option, build_safe_echarts_option):
                option = adapter(fig, window)
                amd = next(s for s in option["series"] if s["name"] == "AMD 5Y")
                self.assertEqual([p[1] for p in amd["data"]], [100., None, 110.])
                self.assertTrue(amd["showSymbol"])
                self.assertFalse(amd["connectNulls"])
            self.assertIn(cds.NVIDIA_1Y_NAME, fig.layout.meta["missing_series"])

    def test_hy_oas_retains_percent_values_and_its_own_calendar_and_axis(self):
        payload = cds.parse_source(source())
        hy_oas = pd.DataFrame({"observation_date": pd.to_datetime(["2026-10-24", "2026-10-29"]),
                               "oas_pct": [3.12, 3.48]})
        for window in ("5Y", "1Y", "6M", "3M", "1M"):
            fig = cds.build_cds_figure(window, payload, hy_oas=hy_oas)
            for adapter in (build_adaptive_echarts_option, build_safe_echarts_option):
                option = adapter(fig, window)
                self.assertEqual(len(option["series"]), 5)
                *companies, oas = option["series"]
                self.assertTrue(all(series["yAxisIndex"] == 0 for series in companies))
                self.assertEqual(oas["name"], cds.HY_OAS_NAME)
                self.assertEqual(oas["yAxisIndex"], 1)
                self.assertEqual(oas["data"], [["2026-10-24T00:00:00", 3.12], ["2026-10-29T00:00:00", 3.48]])
                self.assertEqual(option["yAxis"][1]["name"], "R1 · %")
                self.assertEqual(option["dataZoom"][0]["endValue"], "2026-10-29T00:00:00")
        missing = cds.build_cds_figure(payload=payload, hy_oas=hy_oas.iloc[:0])
        self.assertEqual(len(missing.data), len(cds.CREDIT_SERIES))
        self.assertEqual(missing.layout.meta["missing_series"], [cds.NVIDIA_1Y_NAME, cds.HY_OAS_NAME])

    def test_hy_oas_reads_validated_fred_observations_without_persisting(self):
        import data
        response = requests.Response()
        response.status_code = 200
        response._content = b"observation_date,BAMLH0A0HYM2\n2026-10-26,3.12\n2026-10-27,\n2026-10-28,3.48\n"
        with patch.object(data, "http_get", return_value=response) as fetch, \
             patch.object(data, "_save_fred_success") as save:
            frame = data.get_hy_oas.__wrapped__()
        self.assertEqual(fetch.call_args_list[0].kwargs["params"], {"id": "BAMLH0A0HYM2"})
        self.assertEqual(frame.observation_date.dt.strftime("%Y-%m-%d").tolist(), ["2026-10-26", "2026-10-28"])
        self.assertEqual(frame.oas_pct.tolist(), [3.12, 3.48])
        save.assert_not_called()
        with patch.object(data, "http_get", side_effect=requests.Timeout):
            self.assertTrue(data.get_hy_oas.__wrapped__().empty)

    def test_hy_oas_uses_the_official_vintage_export_when_fred_is_unavailable(self):
        import data
        response = requests.Response()
        response.status_code = 200
        response._content = b"observation_date,BAMLH0A0HYM2_20261109\n2026-11-06,3.42\n"
        with patch.object(data, "http_get", side_effect=[requests.Timeout(), response]) as fetch, \
             patch.object(data, "FRED_API_KEY", ""), patch.object(data, "_save_fred_success") as save:
            frame = data.get_hy_oas.__wrapped__()
        self.assertEqual(fetch.call_args.args[0], data.ALFRED_GRAPH_URL)
        self.assertEqual(frame.oas_pct.tolist(), [3.42])
        self.assertEqual(frame.observation_date.dt.strftime("%Y-%m-%d").tolist(), ["2026-11-06"])
        save.assert_not_called()

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
        for key, (label, _) in cds.CREDIT_SERIES.items():
            actual = [r for r in payload["series"][key]["records"] if r["spread_bps"] is not None]
            self.assertTrue(actual)
            reference = cds.nvidia_issuer_reference(payload) if key == "sn_nvidia" else None
            latest = reference or actual[-1]
            self.assertEqual(table.loc[label, "最新CDS（bp）"], latest["spread_bps"])
            self.assertEqual(table.loc[label, "实际观测日"], latest["observation_date"])
            self.assertLessEqual(actual[-1]["observation_date"], payload["source_asof"])

    def test_freshness_probe_uses_independent_source_and_omits_retired_tenors(self):
        from scripts import probe_all_sources as probe
        jobs = {j[0]: j for j in probe.jobs()}
        self.assertNotIn("NVIDIA_CDS_1Y", jobs)
        aggregate = type("Response", (), {"text": "", "json": lambda self: source()})()
        with patch.object(probe, "get", return_value=aggregate):
            row = probe.check(jobs["NVIDIA_CDS_5Y"])
        self.assertEqual(row["source_latest"], "2026-10-27")
        self.assertEqual(row["status"], "source_behind_repository")
        issuer = type("Response", (), {"text": ISSUER_HTML})()
        with patch.object(probe, "get", side_effect=lambda url: issuer if url == cds.NVIDIA_ISSUER_URL else aggregate):
            row = probe.check(jobs["NVIDIA_CDS_5Y"])
        self.assertEqual(row["source_latest"], "2026-11-25")
        self.assertEqual(row["source_url"], cds.NVIDIA_ISSUER_URL)


if __name__ == "__main__":
    unittest.main()
