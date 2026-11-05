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

    def test_chart_preserves_daily_series_and_weekly_units_dates_both_adapters(self):
        fig = copper.build_copper_flow_spread_figure("1Y")
        self.assertEqual(len(fig.data), 9)
        self.assertFalse(any("VVIX" in trace.name for trace in fig.data))
        for adapter in (build_adaptive_echarts_option, build_safe_echarts_option):
            for period in ("1M", "3M", "6M", "1Y", "5Y"):
                option = adapter(fig, period)
                self.assertEqual(len(option["yAxis"]), 7)
                tc = next(s for s in option["series"] if s["name"].startswith("TC "))
                rc = next(s for s in option["series"] if s["name"].startswith("RC "))
                self.assertEqual(tc["yAxisIndex"], 5)
                self.assertEqual(rc["yAxisIndex"], 6)
                self.assertEqual(tc["observation_cadence"], "weekly")
                self.assertTrue(tc["showSymbol"])
                self.assertFalse(tc["connectNulls"])
                self.assertEqual([p[0][:10] for p in tc["data"]], ["2026-10-16", "2026-10-23", "2026-10-30"])
                self.assertAlmostEqual(tc["data"][-1][1], -245.33)
                self.assertAlmostEqual(rc["data"][-1][1], -24.533)
                self.assertIn("USD/dmt", option["yAxis"][5]["name"])
                self.assertIn("US cents/lb", option["yAxis"][6]["name"])
                health = option_observation_health({"series": [tc, rc]}, now="2026-11-05")
                self.assertFalse(health["stale_names"])
                json.dumps(option, allow_nan=False)
        rows = [r for r in figure_rows({17: fig}, now="2026-11-05") if r["指标"].startswith(("TC ", "RC "))]
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r["频率"] == "周频" and r["实际观测日"] == "2026-10-30" for r in rows))

    def test_missing_charges_do_not_remove_copper_oil_and_table_date_is_observation(self):
        with patch.object(copper, "load_tcrc_snapshot", return_value=pd.DataFrame()):
            fig = copper.build_copper_flow_spread_figure("1Y")
        self.assertEqual(len(fig.data), 7)
        self.assertEqual(len(fig.layout.meta["missing_series"]), 2)
        rows = copper_tcrc.latest_tcrc_rows()
        self.assertEqual(rows[0]["实际报价日"], "2026-10-30")
        self.assertEqual(rows[0]["最新值"], -245.33)
        self.assertEqual(rows[1]["单位"], "美分/磅")


if __name__ == "__main__":
    unittest.main()
