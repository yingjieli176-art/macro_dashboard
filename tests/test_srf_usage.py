import ast
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
import plotly.graph_objects as go

from macro_platform.srf_usage import parse_operations, load_srf_usage
from macro_platform.chart_axes import RANGE_OFFSETS
from macro_platform.echarts_axes import build_adaptive_echarts_option, build_safe_echarts_option
from scripts.update_srf_usage import refresh


def operation(close="13:45", amount=5_000_000, day="2026-11-03", **extra):
    return dict(operationId=f"RP {day} {close}", operationDate=day, settlementDate=day,
        operationType="Repo", term="Overnight", auctionStatus="Results", settlementType="Same Day",
        closeTime=close, totalAmtAccepted=amount, details=[
            dict(securityType=security, amtAccepted=amount if security == "Mortgage-Backed" else 0)
            for security in ("Treasury", "Agency", "Mortgage-Backed")], **extra)


def payload(rows):
    return {"repo": {"operations": rows}}


class SrfUsageTests(unittest.TestCase):
    def test_am_pm_all_collateral_zero_and_deduplication(self):
        am, pm = operation("08:30", 2_000_000), operation()
        zero = [operation("08:30", 0, "2026-11-04"), operation("13:45", 0, "2026-11-04")]
        result = parse_operations(payload([am, pm, copy.deepcopy(pm), *zero]), today="2026-11-05")
        self.assertEqual([r["accepted_usd"] for r in result["records"]], [7_000_000, 0])
        self.assertEqual(result["records"][0]["mbs_usd"], 7_000_000)
        self.assertEqual(len(result["records"][0]["operation_ids"]), 2)

    def test_partial_day_and_exercises_do_not_become_zero_or_daily_amount(self):
        rows = [operation(day="2026-11-02"), operation("08:30", 0), operation(),
                dict(operation("10:15", 99_000_000), note="Small Value Exercise (SVE)"),
                dict(operation("10:45", 99_000_000), term="Term"),
                dict(operation("12:45", 99_000_000), operationType="Reverse Repo"),
                dict(operation("08:30", 0, "2026-11-04"), auctionStatus="Announcement")]
        result = parse_operations(payload(rows), today="2026-11-05")
        self.assertEqual([r["observation_date"] for r in result["records"]], ["2026-11-03"])
        self.assertEqual(result["records"][0]["accepted_usd"], 5_000_000)
        self.assertEqual(result["incomplete_dates"], ["2026-11-02"])
        historical = parse_operations(payload([operation(day="2025-06-25")]), today="2026-11-05")
        self.assertEqual(historical["records"][0]["morning_accepted_usd"], None)

    def test_invalid_future_negative_totals_conflicting_duplicates_are_rejected(self):
        for bad in (operation(amount=-1), operation(amount=float("inf")), operation(day="2099-01-01"),
                    dict(operation(), totalAmtAccepted=42), dict(operation(), details=[])):
            with self.assertRaises(ValueError):
                parse_operations(payload([operation("08:30", 0), bad]), today="2026-11-05")
        with self.assertRaises(ValueError):
            parse_operations(payload([operation("08:30", 0), operation(), operation(amount=10)]))

    def test_atomic_refresh_preserves_history_on_outage_partial_or_truncated_source(self):
        rows = [operation("08:30", 0), operation(), operation("08:30", 0, "2026-11-04"), operation("13:45", 0, "2026-11-04")]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"srf.json"
            refresh(payload(rows), path, today="2026-11-05")
            stored = path.read_bytes()
            for failed in ([], [operation("08:30", 0)], [operation("08:30", 0), operation()]):
                with self.assertRaises(ValueError):
                    refresh(payload(failed), path, today="2026-11-05")
                self.assertEqual(path.read_bytes(), stored)
            frame = load_srf_usage(path)
            self.assertEqual(frame.SRF_USAGE_BN.tolist(), [.005, 0])

    def test_usage_has_its_own_calendar_amount_axis_and_zero_based_bars_in_both_adapters(self):
        source = Path(__file__).resolve().parents[1]/"app.py"
        names = {"build_fig1", "add_line", "filter_range", "_mark_missing_series"}
        nodes = [n for n in ast.parse(source.read_text()).body if isinstance(n, ast.FunctionDef) and n.name in names]
        ns = dict(pd=pd, go=go, RANGE_OFFSETS=RANGE_OFFSETS, chart_height=lambda *a:420,
                  apply_chart_style=lambda fig,*a:fig)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), ns)
        def rates(name):
            return pd.DataFrame({"observation_date":pd.to_datetime(["2026-11-02"]), name:[4.]})
        ns.update(get_iorb=lambda:rates("IORB"), get_rrp_rate=lambda:rates("RRPONTSYAWARD"),
            get_effr=lambda:rates("EFFR"), get_sofr=lambda:rates("SOFR"), get_fred_series=lambda name:rates(name),
            load_srf_usage=lambda:pd.DataFrame({"observation_date":pd.to_datetime(["2026-11-03", "2026-11-04"]), "SRF_USAGE_BN":[.005,0]}))
        fig = ns["build_fig1"]("1M")
        self.assertEqual(len(fig.data), 6)
        for adapter in (build_adaptive_echarts_option, build_safe_echarts_option):
            option = adapter(fig, "1M")
            usage = next(s for s in option["series"] if s["name"] == "SRF 实际用量 (R1)")
            self.assertEqual(usage["type"], "bar")
            self.assertEqual(usage["yAxisIndex"], 1)
            self.assertEqual([p[1] for p in usage["data"]], [.005, 0])
            self.assertEqual([p[0][:10] for p in usage["data"]], ["2026-11-03", "2026-11-04"])
            self.assertFalse(option["yAxis"][1]["scale"])
            self.assertIn("USD bn", option["yAxis"][1]["name"])
            self.assertTrue(option["yAxis"][0]["scale"])
        self.assertEqual(list(fig.data[0].x), [pd.Timestamp("2026-11-02")])


if __name__ == "__main__":
    unittest.main()
