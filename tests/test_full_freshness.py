from pathlib import Path
import tempfile
import json
import unittest
from unittest.mock import Mock, patch
import ast
from types import SimpleNamespace
import time

import pandas as pd
import plotly.graph_objects as go

from macro_platform.freshness_overview import figure_rows, source_rows
from scripts.probe_all_sources import check, jobs, fred
from scripts import sync_fred_verified_cache as sync


class FullFreshness(unittest.TestCase):
    def test_reverse_repo_uses_only_completed_overnight_results_and_dollar_units(self):
        operations = [{"operationType": "Reverse Repo", "term": "Overnight", "auctionStatus": "Results",
                       "operationDate": f"2026-09-{day:02d}", "totalAmtAccepted": 237_000_000,
                       "details": [{"percentAwardRate": 3.75}]} for day in range(1,21)]
        for operation_type, term, status in (("Repo", "Overnight", "Results"),
                                              ("Reverse Repo", "Term", "Results"),
                                              ("Reverse Repo", "Overnight", "Announcement")):
            operations.append(dict(operations[0], operationType=operation_type, term=term, auctionStatus=status,
                                   operationDate="2026-10-01", totalAmtAccepted=999_000_000_000))
        payload={"repo":{"operations":operations}}
        amounts=sync._reverse_repo_frame(payload,"RRPONTSYD")
        rates=sync._reverse_repo_frame(payload,"RRPONTSYAWARD")
        self.assertEqual(amounts.date.max(),pd.Timestamp("2026-09-20"))
        self.assertAlmostEqual(amounts.value.iloc[-1],.237)
        self.assertEqual(rates.value.iloc[-1],3.75)
        payload["repo"]["operations"][0]["details"].append({"percentAwardRate":4.0})
        with self.assertRaises(ValueError):sync._reverse_repo_frame(payload,"RRPONTSYAWARD")

    def test_h41_reserve_balances_keeps_weekly_average_instead_of_wednesday_level(self):
        html="""<table><thead><tr><th rowspan="2">Reserve balances</th>
        <th>Averages of daily figures</th><th>Wednesday Oct 14, 2026</th></tr>
        <tr><th>Week ended Oct 14, 2026</th><th>Wednesday Oct 14, 2026</th></tr></thead>
        <tbody><tr><td>Reserve balances with Federal Reserve Banks</td><td>3022140</td><td>3030854</td></tr></tbody></table>
        <table><thead><tr><th>Assets, liabilities, and capital</th><th>Eliminations from consolidation</th>
        <th>Wednesday Oct 14, 2026</th></tr></thead>
        <tbody><tr><td>Total assets</td><td>0</td><td>6755639</td></tr></tbody></table>"""
        self.assertEqual(sync._h41_current_frame(html,"WRESBAL").value.iloc[0],3022140)
        self.assertEqual(sync._h41_current_frame(html,"WALCL").value.iloc[0],6755639)
        with self.assertRaises(ValueError):sync._h41_current_frame(html.replace("Week ended","Other"),"WRESBAL")

    def test_fred_api_fallback_keeps_dates_and_does_not_leak_request_details(self):
        frame=pd.DataFrame({"date":pd.to_datetime(["2026-10-20"]),"value":[4.]})
        with patch('scripts.probe_all_sources.get',side_effect=TimeoutError('export unavailable')), \
             patch.object(sync,'_fetch_api',return_value=frame):
            # A requests transport failure is handled, while arbitrary coding
            # errors must still remain errors rather than becoming success.
            import requests
            with patch('scripts.probe_all_sources.get',side_effect=requests.Timeout('export unavailable')):
                self.assertEqual(fred('T10YIE')[0],'2026-10-20')
        with patch('scripts.probe_all_sources.get',side_effect=requests.Timeout('export unavailable')), \
             patch.object(sync,'_fetch_api',side_effect=RuntimeError('secret-bearing-request-url')):
            row=check(('T10YIE',[2],'daily','2026-10-19',lambda:fred('T10YIE')))
        self.assertEqual(row['status'],'unverified')
        self.assertNotIn('secret-bearing',row['error'])

    def test_long_open_page_checks_revision_after_startup_window(self):
        source = Path(__file__).resolve().parents[1] / "app.py"
        node = next(n for n in ast.parse(source.read_text()).body
                    if isinstance(n,ast.FunctionDef) and n.name=="_poll_source_completion")
        node.decorator_list=[]
        state={"_source_watch_until":0,"_source_watch_revision":("old",),"_late_dashboard_jobs":{},
               "hk_5_range_time_window":"1M"}
        ui=SimpleNamespace(session_state=state,rerun=Mock())
        ns={"st":ui,"time":time,"_macro_snapshot_revision":lambda:("new",)}
        exec(compile(ast.Module(body=[node],type_ignores=[]),str(source),"exec"),ns)
        ns["_poll_source_completion"]()
        ui.rerun.assert_called_once()
        self.assertEqual(state["hk_5_range_time_window"],"1M")
        ns["_poll_source_completion"]()
        ui.rerun.assert_called_once()

    def test_long_open_live_feeds_expire_without_a_snapshot_change(self):
        from test_dashboard_loading import load_helpers
        ns=load_helpers()
        with patch.object(ns["time"],"time",return_value=3000):before=ns["_macro_snapshot_revision"]()
        with patch.object(ns["time"],"time",return_value=3299):same=ns["_macro_snapshot_revision"]()
        with patch.object(ns["time"],"time",return_value=3300):after=ns["_macro_snapshot_revision"]()
        self.assertEqual(before,same)
        self.assertNotEqual(before,after)

    def test_market_and_watchlist_have_automatic_refresh_fragments(self):
        source=Path(__file__).resolve().parents[1]/"app.py"
        tree=ast.parse(source.read_text())
        for name in ("render_market_overview","render_watchlists"):
            node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
            period=[kw.value.value for decorator in node.decorator_list if isinstance(decorator,ast.Call)
                    for kw in decorator.keywords if kw.arg=="run_every"]
            self.assertEqual(period,[60])

    def test_inventory_covers_every_chart_and_previously_omitted_live_sources(self):
        config = jobs()
        self.assertEqual({c for _, charts, _, _, _ in config for c in charts}, set(range(1,15)))
        self.assertTrue({"GC=F","SI=F","BTC-USD","ETH-USD","^N225","china_2y","japan_2y","GVZCLS"}
                        <= {row[0] for row in config})

    def test_transport_failure_is_unverified_and_newer_source_is_not_green(self):
        def fail(): raise TimeoutError("source unavailable")
        row = check(("X", [1], "daily", "2026-10-19", fail))
        self.assertEqual(row["status"], "unverified")
        row = check(("X", [1], "daily", "2026-10-19", lambda: ("2026-10-20", "official")))
        self.assertEqual(row["status"], "pipeline_lag")

    def test_every_curve_including_derived_and_missing_chart_is_listed(self):
        fig = go.Figure(go.Scatter(x=pd.to_datetime(["2026-10-19","2026-10-20"]),
                                 y=[4.,None], name="10Y−2Y (R1)"))
        monthly = go.Figure(go.Scatter(x=pd.to_datetime(["2026-09-30"]), y=[1.], name="Balance"))
        rows = figure_rows({3:fig,6:monthly}, now="2026-10-21")
        self.assertEqual(len(rows),14)
        self.assertEqual(next(r for r in rows if r["图表"]==3)["实际观测日"],"2026-10-19")
        self.assertEqual(next(r for r in rows if r["图表"]==6)["频率"],"月频")
        self.assertEqual(next(r for r in rows if r["图表"]==14)["状态"],"待恢复")

    def test_reference_guide_levels_are_not_dated_observations(self):
        fig=go.Figure(go.Scatter(x=["2026-10-20"],y=[7.8],name="USD/HKD"))
        for name in ("Strong-side CU 7.75","Linked Rate Center 7.80","Weak-side CU 7.85"):
            fig.add_trace(go.Scatter(x=["2026-10-21"],y=[7.8],name=name))
        rows=[r for r in figure_rows({8:fig}) if r["图表"]==8]
        self.assertEqual([r["指标"] for r in rows],["USD/HKD"])

    def test_gvz_original_export_uses_named_value_column(self):
        text="DATE,GVZ\n"+"\n".join(f"{d:%m/%d/%Y},21.5" for d in pd.date_range(end="2026-10-20",periods=20))
        session=Mock();session.get.return_value=Mock(text=text)
        frame=sync._fetch_primary(session,"GVZCLS")
        self.assertEqual(frame.date.max(),pd.Timestamp("2026-10-20"))
        self.assertEqual(frame.value.iloc[-1],21.5)

    def test_hk_independent_series_do_not_drop_a_newer_completed_close(self):
        from macro_platform import hk_liquidity as hk
        def market(symbol,label,window):
            dates=pd.to_datetime(["2026-10-19","2026-10-20"]+([] if symbol=="HSTECH" else ["2026-10-21"]))
            return pd.DataFrame({"observation_date":dates,label:range(100,100+len(dates))})
        with patch.object(hk,"_market_history",side_effect=market):
            figures=hk.build_hk_liquidity_figures("1Y")
        for fig in (figures[0],figures[3]):
            for trace in fig.data:
                if trace.name.startswith("Tencent Price"):
                    self.assertEqual(max(pd.to_datetime(trace.x)),pd.Timestamp("2026-10-21"))
                if trace.name.startswith("HSTECH Index"):
                    # Outer calendar rows must not create an observation.
                    actual=[pd.Timestamp(d) for d,v in zip(trace.x,trace.y) if pd.notna(v)]
                    self.assertEqual(max(actual),pd.Timestamp("2026-10-20"))
