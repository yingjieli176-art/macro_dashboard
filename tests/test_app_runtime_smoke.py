"""Offline end-to-end Streamlit script smoke check.

Network is deliberately disabled so a failing external market-data provider does
not mask a dashboard startup or widget-rendering regression.
"""
import unittest
import json
from pathlib import Path
from unittest.mock import patch

import requests
import re
from streamlit.testing.v1 import AppTest


def chart_specs(app):
    return [json.dumps(json.loads(chart.proto.json)["option"], sort_keys=True)
            for chart in app.get("bidi_component")
            if chart.proto.component_name.endswith("macro_linked_chart")]


class DashboardBootSmoke(unittest.TestCase):
    def test_fresh_session_can_render_warmed_shared_chart_caches(self):
        from scripts.benchmark_runtime import offline_http, offline_urlopen
        app = Path(__file__).resolve().parents[1] / 'app.py'
        with patch.object(requests.sessions.Session, 'request', new=offline_http), \
             patch('urllib.request.urlopen', new=offline_urlopen):
            first = AppTest.from_file(str(app), default_timeout=90).run()
            second = AppTest.from_file(str(app), default_timeout=90).run()
        self.assertFalse(first.exception)
        self.assertFalse(second.exception)
        self.assertEqual(len(second.get('button_group')), 22)
        self.assertGreaterEqual(len(chart_specs(second)), 8)
        self.assertEqual(chart_specs(first), chart_specs(second))

    def test_full_dashboard_completes_when_sources_are_offline(self):
        app = Path(__file__).resolve().parents[1] / "app.py"
        with patch.object(requests.sessions.Session, "request", side_effect=requests.Timeout("offline CI")), \
             patch("urllib.request.urlopen", side_effect=OSError("offline CI")):
            instance = AppTest.from_file(str(app), default_timeout=90).run()
        self.assertFalse(
            instance.exception,
            msg="Streamlit app crashed during full script execution: "
                + "; ".join(str(error.message) for error in instance.exception),
        )
        self.assertEqual(len(instance.get("button_group")), 22)
        titles = [match.group(1) for element in instance.markdown
                  if (match := re.search(r'class="section-title">(\d+)\.', element.value))]
        self.assertEqual(titles, [str(number) for number in range(1, 23)])
        title_text = " ".join(element.value for element in instance.markdown)
        self.assertIn('4. US Equity Risk', title_text)
        self.assertIn('6. SPX / RSP', title_text)
        self.assertIn('7. AI Credit · 公司CDS信用风险', title_text)
        self.assertIn('8. 标普500 / 日经225', title_text)
        self.assertIn('9. 日本利率走廊', title_text)
        self.assertIn('10. Japan Government Yields', title_text)
        self.assertIn('11. 日元套息分析', title_text)
        self.assertIn('12. 日本美债持仓与机构外债', title_text)
        self.assertIn('日本寿险与养老金 · 机构披露', title_text)
        self.assertIn('13. China Government Yields', title_text)
        source_rows = [element.value for element in instance.markdown
                       if element.value.startswith('<div class="source-text">Source: ')]
        self.assertEqual(len(source_rows), 22)
        for url in ("https://irates.today/chart_data.json", "https://irates.today/capex.html#method",
                    "https://fred.stlouisfed.org/series/BAMLH0A0HYM2", "https://fred.stlouisfed.org/series/BAMLC0A0CM"):
            self.assertIn(url, source_rows[6])
        self.assertNotIn("term-premia-tabs", source_rows[6])
        parameter_rows = [element.value for element in instance.markdown
                          if element.value.startswith('<div class="chart-parameters">')]
        self.assertEqual(len(parameter_rows), 22)
        for label in ("公司 5Y CDS", "实际观测与覆盖率", "HY OAS（右轴1）", "IG OAS（右轴1）"):
            self.assertIn(label, parameter_rows[6])
        for unrelated in ("资本开支", "期限溢价与美联储", "韩国股市"):
            self.assertNotIn(unrelated, parameter_rows[6])
        self.assertFalse(any(caption.value.startswith("来源：Open-Sourced") for caption in instance.caption))
        self.assertEqual([control.key for control in instance.get("button_group")[6:9]],
                         ["nvidia_cds_time_window", "sp500_nikkei_ratio_time_window", "japan_corridor_time_window"])
        specs = chart_specs(instance)
        # AppTest does not execute browser JavaScript. This assertion proves
        # the real Streamlit renderer emitted native chart messages, rather
        # than merely surviving with missing data or Plotly fallbacks.
        self.assertGreaterEqual(len(specs), 8)
        self.assertEqual(len(instance.get("plotly_chart")), 0)
        for spec in specs:
            option = json.loads(spec)
            self.assertTrue(option["series"])
            self.assertTrue(any(point[1] is not None for series in option["series"]
                                for point in series["data"]))
            for index, axis in enumerate(option["yAxis"]):
                bars = any(s["type"] == "bar" and s["yAxisIndex"] == index for s in option["series"])
                self.assertEqual(axis["scale"], not bars)
            self.assertTrue(all(zoom["filterMode"] == "filter" for zoom in option["dataZoom"]))
        self.assertEqual(len(instance.radio), 0)
        drawdown = next(json.loads(spec) for spec in specs
                        if any(s['name'] == 'SPX（标普500市值加权）' for s in json.loads(spec)['series']))
        self.assertEqual([series["name"] for series in drawdown["series"]],
                         ["SPX（标普500市值加权）", "RSP（标普500等权ETF）"])
        china = next(json.loads(spec) for spec in specs
                     if any(series["name"] == "沪深300" for series in json.loads(spec)["series"]))
        self.assertEqual([series["name"] for series in china["series"]], ["沪深300", "中证1000", "中证2000"])
        self.assertFalse(any("距前高跌幅" in element.value.columns for element in instance.dataframe))
        # Market assets retain their original unit and independent price axes.
        spec_text = " ".join(specs)
        options = [json.loads(spec) for spec in specs]
        yen_vol = next(option for option in options
                       if any(s["name"] == "BOJ 政策利率（右轴）" for s in option["series"]))
        policy = next(s for s in yen_vol["series"] if s["name"] == "BOJ 政策利率（右轴）")
        self.assertEqual(policy["step"], "end")
        self.assertEqual(policy["yAxisIndex"], 0)
        removed = {"JPY 20-session appreciation (R2)", "USD/JPY 20日实际波动率", "USD/JPY 60日实际波动率"}
        self.assertTrue(removed.isdisjoint(s["name"] for s in yen_vol["series"]))
        for series_name in ("GPIF 美债票据与长期债券", "九家主要寿险 · 外债对冲率"):
            institutional = next(s for option in options for s in option["series"] if s["name"] == series_name)
            self.assertEqual(len(institutional["data"]), 6)
            self.assertTrue(institutional["showSymbol"])
        yen_tic = next(option for option in options
                       if any(s["name"] == "日本美债总持仓" for s in option["series"]))
        self.assertEqual([s["yAxisIndex"] for s in yen_tic["series"][:5]], [0, 0, 0, 1, 1])
        self.assertTrue(all(s["observation_cadence"] == "monthly" for s in yen_tic["series"][:5]))
        moved_names = {s["name"] for s in yen_tic["series"]}
        self.assertEqual(len(moved_names), 9)
        self.assertTrue(moved_names.isdisjoint(s["name"] for s in yen_vol["series"]))
        self.assertEqual(instance.get("button_group")[11].key, "japan_holdings_time_window")
        corridor = next(json.loads(spec) for spec in specs if '"SRF"' in spec)
        self.assertEqual({series["name"] for series in corridor["series"]},
                         {"IORB", "ON RRP", "EFFR", "SOFR", "SRF", "SRF 实际用量 (R1)"})
        usage = next(series for series in corridor["series"] if series["name"] == "SRF 实际用量 (R1)")
        self.assertEqual(usage["type"], "bar")
        self.assertEqual(usage["yAxisIndex"], 1)
        self.assertIn("十亿美元", corridor["yAxis"][1]["name"])
        self.assertFalse(corridor["yAxis"][1]["scale"])
        self.assertTrue(any(point[1] == 0 for point in usage["data"]))
        ten_year = next(json.loads(spec) for spec in specs
                        if any(s['name'] == '10年期实际收益率（TIPS · DFII10，右轴）' for s in json.loads(spec)['series']))
        self.assertEqual([s["name"] for s in ten_year["series"]],
                         ["10年期名义收益率（DGS10）", "10年期实际收益率（TIPS · DFII10，右轴）", "10年期盈亏平衡通胀率（BEI · T10YIE，右轴）"])
        srf = next(series for series in corridor["series"] if series["name"] == "SRF")
        self.assertEqual(srf["lineStyle"]["type"], "dashed")
        self.assertTrue(any(point[1] is not None for point in srf["data"]))
        treasury = next(json.loads(spec) for spec in specs if '"30Y"' in spec)
        thirty = next(series for series in treasury["series"] if series["name"] == "30Y")
        self.assertEqual(thirty["yAxisIndex"], 0)
        self.assertTrue(any(point[1] is not None for point in thirty["data"]))
        risk = next(json.loads(spec) for spec in specs if 'COR3M (R3)' in spec)
        risk_series = {series["name"]: series for series in risk["series"]}
        self.assertEqual(len(risk["yAxis"]), 7)
        move = risk_series["MOVE 债市波动率（R4）"]
        self.assertEqual(move["yAxisIndex"], 4)
        self.assertTrue(any(point[1] is not None for point in move["data"]))
        ratio = risk_series["MOVE/VIX (R5)"]
        self.assertEqual(ratio["yAxisIndex"], 5)
        self.assertTrue(any(point[1] is not None for point in ratio["data"]))
        gex_option = next(json.loads(spec) for spec in specs
                          if any(s["name"].startswith("GEX 做市商伽马") for s in json.loads(spec)["series"]))
        gex = next(s for s in gex_option["series"] if s["name"].startswith("GEX 做市商伽马"))
        self.assertEqual(gex["yAxisIndex"], 5)
        self.assertEqual(len(gex_option["yAxis"]), 6)
        self.assertIn("十亿美元", gex_option["yAxis"][5]["name"])
        self.assertFalse(any("COR1M" in name or "VIXEQ−VIX" in name for name in risk_series))
        for name in ("COR3M (R3)", "VIXEQ/VIX (R2)"):
            self.assertIn(name, risk_series)
            self.assertTrue(any(point[1] is not None for point in risk_series[name]["data"]))
        self.assertNotIn("Rebased", spec_text)
        japan = next(json.loads(spec) for spec in specs
                     if any(series["name"] == "Japan 30Y−10Y (R1)"
                            for series in json.loads(spec)["series"]))
        japan_series = {series["name"]: series for series in japan["series"]}
        self.assertEqual(len(japan_series), 7)
        self.assertEqual(japan_series["Nikkei 225 (R2)"]["yAxisIndex"], 2)
        self.assertEqual(japan_series["USD/JPY (R3)"]["yAxisIndex"], 3)
        self.assertEqual(japan_series["Japan 30Y"]["yAxisIndex"], 0)
        self.assertEqual(japan_series["Japan 30Y−10Y (R1)"]["yAxisIndex"], 1)
        self.assertTrue(any(point[1] is not None for point in japan_series["Japan 30Y"]["data"]))
        self.assertTrue(any(point[1] is not None for point in japan_series["Japan 30Y−10Y (R1)"]["data"]))
        carry = yen_vol
        self.assertEqual(len(carry["yAxis"]), 6)
        self.assertEqual([series["name"] for series in carry["series"][:8]],
                         ["US 10Y - Japan 10Y", "USD/JPY (R1)",
                          "CFTC JPY speculative net (R2)", "TOPIX（东证指数） (R3)", "美元指数 DXY (R4)",
                          "JPY 3M", "JPY 10Y", "JPY 10Y - JPY 3M"])
        self.assertEqual([series["yAxisIndex"] for series in carry["series"][:8]], [0, 1, 2, 3, 4, 0, 0, 0])
        self.assertIn("阳轴", carry["yAxis"][1]["name"])
        self.assertFalse(carry["yAxis"][1]["inverse"])
        self.assertEqual(len(carry["series"]), 10)
        self.assertEqual(len(carry["series"]) + len(yen_tic["series"]), 19)
        iv = next(s for s in carry["series"] if s["name"] == "USD/JPY 3M ATM 隐含波动率（Saxo，R5）")
        self.assertEqual(iv["yAxisIndex"], 5)
        self.assertTrue(iv["showSymbol"])
        from macro_platform.jpy_implied_vol import load_snapshot
        self.assertEqual(iv["data"][-1][1], load_snapshot()["records"][-1]["value"])
        self.assertIn("https://fxowebtools.saxobank.com/otc.html", source_rows[10])
        self.assertIn("https://finance.yahoo.com/quote/DX-Y.NYB/history/", source_rows[10])
        self.assertEqual(carry["series"][2]["type"], "bar")
        money = next(json.loads(spec) for spec in specs if '"M2 MoM"' in spec)
        self.assertEqual(next(s for s in money["series"] if s["name"] == "M2 MoM")["type"], "bar")
        self.assertTrue(all(any(point[1] is not None for point in series["data"]) for series in carry["series"]))
        self.assertNotIn("起点100", spec_text)



if __name__ == "__main__":
    unittest.main()



