import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from macro_platform import copper, copper_tcrc
from macro_platform.echarts_axes import build_adaptive_echarts_option, build_safe_echarts_option, option_observation_health
from macro_platform.freshness_overview import figure_rows
from scripts.update_copper_tcrc import parse_article, refresh

URL = "https://youse.mysteel.com/a/26110208/7DCD2C67E671022B.html"


def row(day="2026-10-30", tc=-245.33):
    return dict(observation_date=day, tc_usd_dmt=tc, rc_cents_lb=round(tc / 10, 6), source_url=URL)


class CopperTcrcTests(unittest.TestCase):
    def test_signed_zero_values_and_future_nonfinite_wrong_pair(self):
        for tc in (-245.33, 0, 80):
            self.assertEqual(copper_tcrc.validate_record(row(tc=tc), today="2026-11-05")["tc_usd_dmt"], tc)
        for bad in (row("2099-01-01"), row(tc=float("inf")),
                    dict(row(), rc_cents_lb=-245.33), dict(row(), source_url="https://example.com")):
            with self.assertRaises(ValueError):
                copper_tcrc.validate_record(bad, today="2026-11-05")

    def test_parser_uses_index_date_not_article_date_bid_or_annual_benchmark(self):
        article = """<h1>2026年11月2日铜产业早读</h1><p>铜精矿：10月30日，进口铜精矿TC指数为-245.33美元/干吨，较上周下跌4.26美元/干吨。有矿山以-248出售货物。2027年长单基准为0。</p>"""
        records = parse_article(article, URL, today="2026-11-05")
        self.assertEqual(records, [row()])
        self.assertEqual(parse_article("11月2日，固定TC主流在-240美元/干吨", URL), [])
        self.assertEqual(parse_article(article.replace("10月30", "11月3"), URL), [])
        self.assertEqual(parse_article(article.replace("10月30", "9月30"), URL), [])
        pair = "10月23日，Mysteel进口铜精矿TC/RC指数分别为-241.07美元/干吨、−24.107美分/磅"
        self.assertEqual(parse_article(pair, URL)[0]["rc_cents_lb"], -24.107)

    def test_refresh_keeps_history_and_outages_never_replace_good_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "charges.json"
            path.write_text(json.dumps({"records": [row("2026-10-23", -241.07)]}))
            result = refresh([row()], path, today="2026-11-05")
            self.assertEqual(len(result["records"]), 2)
            saved = path.read_bytes()
            for bad in ([], [row("2026-10-16", -240.83)], [row(tc=float("nan"))]):
                with self.assertRaises(ValueError):
                    refresh(bad, path, today="2026-11-05")
                self.assertEqual(path.read_bytes(), saved)

    def test_chart_has_no_charge_traces_axes_or_missing_charge_warnings(self):
        fig = copper.build_copper_flow_spread_figure("1Y")
        self.assertEqual(len(fig.data), 7)
        self.assertFalse(any(trace.name.startswith(("TC ", "RC ")) for trace in fig.data))
        self.assertIsNone(fig.layout.yaxis6 if "yaxis6" in fig.layout else None)
        self.assertFalse(any(str(name).startswith(("TC ", "RC "))
                             for name in (fig.layout.meta or {}).get("missing_series", [])))
        for adapter in (build_adaptive_echarts_option, build_safe_echarts_option):
            for period in ("1M", "3M", "6M", "1Y", "5Y"):
                option = adapter(fig, period)
                self.assertEqual(len(option["yAxis"]), 5)
                self.assertTrue(any(series["name"] == "铜油比 (R4)" for series in option["series"]))
                self.assertFalse(any(series["name"].startswith(("TC ", "RC ")) for series in option["series"]))
                json.dumps(option, allow_nan=False)

    def test_history_table_filters_calendar_months_preserves_signed_values_and_dates(self):
        dates = ["2026-05-05", "2026-05-06", "2026-06-18", "2026-10-30"]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "charges.json"
            path.write_text(json.dumps({"records": [row(day, tc) for day, tc in zip(dates, [-80, 0, -120.5, -245.33])]}))
            with patch.object(copper_tcrc, "SNAPSHOT_PATH", path):
                rows = copper_tcrc.tcrc_history_rows(now="2026-11-06T01:00:00+00:00")
        self.assertEqual([r["报价日期"] for r in rows], ["2026-10-30", "2026-06-18", "2026-05-06"])
        self.assertEqual(rows[0]["TC 粗炼费（美元/干吨）"], -245.33)
        self.assertEqual(rows[0]["RC 精炼费（美分/磅，TC÷10）"], -24.533)
        self.assertEqual(rows[-1]["TC 粗炼费（美元/干吨）"], 0)
        self.assertEqual(rows[0]["来源"], URL)

    def test_backfill_sources_remain_same_provider_and_snapshot_has_no_filled_dates(self):
        for url in ("https://list1.mysteel.com/zhishi/tjkTCjg.html",
                    "https://youse.m.mysteel.com/a/26052218/5E58782A6DC333C9_abc.html"):
            self.assertEqual(copper_tcrc.validate_record(dict(row(), source_url=url))["source_url"], url)
        for url in ("https://youse.mysteel.com.evil.example/a/article", "https://list1.mysteel.com/other", "https://hq.smm.cn/copper"):
            with self.assertRaises(ValueError):
                copper_tcrc.validate_record(dict(row(), source_url=url))
        rows = copper_tcrc.tcrc_history_rows(now="2026-11-06")
        self.assertGreaterEqual(len(rows), 21)
        self.assertEqual(rows[-1]["报价日期"], "2026-05-08")
        self.assertNotIn("2026-09-24", [r["报价日期"] for r in rows])


if __name__ == "__main__":
    unittest.main()
