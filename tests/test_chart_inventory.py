"""Regional positions, headings and source evidence must identify the same chart."""
import ast
import json
from pathlib import Path
import re
import tempfile
import unittest

import plotly.graph_objects as go

from macro_platform.chart_inventory import DISPLAY_ORDER, DISPLAY_NUMBER, NUMBERING, REGION_HEADERS
from macro_platform.freshness_overview import source_rows, figure_rows
from scripts.probe_all_sources import jobs


class RegionalChartInventory(unittest.TestCase):
    def test_regions_are_contiguous_and_every_chart_appears_once(self):
        self.assertEqual(DISPLAY_ORDER[:10], (1,2,3,4,"us_drawdown",9,10,11,13,12))
        self.assertEqual(DISPLAY_ORDER[10:12], (15,16))
        self.assertEqual(DISPLAY_ORDER[12:16], (5,6,7,8))
        self.assertEqual(DISPLAY_ORDER[16:], (14,"cn_drawdown"))
        self.assertEqual(len(set(DISPLAY_ORDER)),18)
        self.assertEqual(list(REGION_HEADERS),[1,15,5,14])
        self.assertEqual(DISPLAY_NUMBER[8],16)

    def test_visible_headings_match_stable_builder_identities(self):
        source=ast.parse((Path(__file__).resolve().parents[1]/"app.py").read_text())
        functions={node.name:node for node in source.body if isinstance(node,ast.FunctionDef)}
        for key in (*range(1,5), *range(9,17), "us_drawdown", "cn_drawdown"):
            name=("render_macro_chart_"+str(key) if isinstance(key,int) else
                  "_render_equity_drawdown" if key=="us_drawdown" else "_render_china_drawdown")
            titles=[match for node in ast.walk(functions[name])
                    if isinstance(node,ast.Constant) and isinstance(node.value,str)
                    for match in re.findall(r'section-title">(\d+)\. ',node.value)]
            self.assertEqual(titles,[str(DISPLAY_NUMBER[key])],name)
        config=next(node.value for node in source.body if isinstance(node,ast.Assign)
                    and any(isinstance(t,ast.Name) and t.id=="HK_CHART_CONFIGS" for t in node.targets))
        for key,row in zip(range(5,9),ast.literal_eval(config)):
            self.assertIn(f'>{DISPLAY_NUMBER[key]}. ',row[0])

    def test_archived_source_reports_remap_without_redating_or_double_remapping(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"report.json"
            report={"checked_at":"2026-11-02T01:00:00Z", "chart_numbering":"display_18",
                    "sources":[{"id":"X","charts":[5,8,14,18],"status":"at_source_latest",
                    "checked_at":"2026-11-02T01:00:00Z","repository_latest":"2026-10-30",
                    "source_latest":"2026-10-30"}]}
            path.write_text(json.dumps(report));stamp,rows=source_rows(path)
            self.assertEqual(rows[0]["图表"],"11,12,13,16")
            self.assertEqual(rows[0]["本地数据日期"],"2026-10-30")
            self.assertEqual(rows[0]["本次核对时间"],stamp)
            report["chart_numbering"]=NUMBERING;report["sources"][0]["charts"]=[11,12,13,16]
            path.write_text(json.dumps(report))
            self.assertEqual(source_rows(path),(stamp,rows))

    def test_browser_numbered_title_selectors_match_actual_headings(self):
        root = Path(__file__).resolve().parents[1]
        titles = set(re.findall(r'section-title">([^<]+)</div>', (root / "app.py").read_text()))
        browser = ast.parse((root / "scripts/check_browser_release.py").read_text())
        checked = []
        for node in ast.walk(browser):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "get_by_text" and node.args):
                continue
            argument = node.args[0]
            if not isinstance(argument, (ast.Constant, ast.JoinedStr)):
                continue
            title = eval(compile(ast.Expression(argument), "browser-title", "eval"),
                         {"__builtins__": {}, "DISPLAY_NUMBER": DISPLAY_NUMBER})
            if isinstance(title, str) and re.match(r"^\d+\. ", title):
                exact = any(keyword.arg == "exact" and isinstance(keyword.value, ast.Constant)
                            and keyword.value.value is True for keyword in node.keywords)
                if exact:
                    self.assertIn(title, titles)
                else:
                    self.assertTrue(any(title in heading for heading in titles), title)
                checked.append(title)
        self.assertGreaterEqual(len(checked), 5)

    def test_banking_keeps_monthly_cadence_at_its_new_position(self):
        monthly=go.Figure(go.Scatter(x=["2026-09-30"],y=[54.108],name="Closing Aggregate Balance"))
        daily=go.Figure(go.Scatter(x=["2026-10-30"],y=[53.999],name="Closing Aggregate Balance (R3)"))
        rows=figure_rows({14:monthly,16:daily},now="2026-11-02")
        self.assertEqual(next(r for r in rows if r["图表"]==14)["频率"],"月频")
        self.assertEqual(next(r for r in rows if r["图表"]==16)["频率"],"日频")

    def test_live_source_inventory_uses_current_visible_numbers(self):
        charts={key:ids for key,ids,*_ in jobs()}
        self.assertEqual(charts["SPX"],[5])
        self.assertEqual(charts["m2_hkd"],[13])
        self.assertEqual(charts["closing_balance"],[16])
        self.assertEqual(charts["japan_2y"],[11,12])
        self.assertEqual(charts["000300"],[18])


if __name__=="__main__":
    unittest.main()
