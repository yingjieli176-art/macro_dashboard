"""Source integrity: never disguise missing/estimated data as observations.

Official cross-checks:
- COCHILCO Jul 7 2026 prints a single suspect zero COMEX inventory
  between two ~600k-t readings; preserve the raw file for audit, hide 0
  from the chart rather than interpolating.
- HKMA's Jan 2021 announcement confirms 17.3% HKD M2 and M3 MoM,
  caused partly by IPO-funded deposits. Large true changes must survive.
- US Treasury DTS has different open_today_bal and close_today_bal fields.
"""
import ast
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import pandas as pd

from macro_platform.copper import (
    SNAPSHOT_PATH as COPPER_PATH, load_copper_snapshot,
    build_copper_flow_spread_figure,
)
from macro_platform.asia_rates import load_china_gov_yields
from macro_platform.treasury_cash import parse_dts_tga_rows


ROOT = Path(__file__).resolve().parents[1]


def undecorated(file, function_name, ns):
    tree = ast.parse((ROOT / file).read_text(encoding="utf-8"))
    func = next(node for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name == function_name)
    func.decorator_list = []
    if "requests" in ns:
        ns.setdefault("http_get", ns["requests"].get)
    exec(compile(ast.Module(body=[func], type_ignores=[]), file, "exec"), ns)
    return ns[function_name]


class TruthAndProvenanceChecks(unittest.TestCase):
    def test_copper_single_day_published_zero_is_not_a_market_crash(self):
        original = json.loads(COPPER_PATH.read_text(encoding="utf-8"))["records"]
        row = next(x for x in original if x["date"] == "2026-07-07")
        # Legacy snapshots contain the published zero; refreshed snapshots
        # explicitly quarantine it as null. Either is valid input here,
        # but the plotted chart must never show a physical stock collapse.
        self.assertIn(row["comex_stock_t"], (0, None))
        cleaned = load_copper_snapshot().set_index("observation_date")
        t = pd.Timestamp("2026-07-07")
        self.assertTrue(pd.isna(cleaned.loc[t, "comex_stock_t"]))
        self.assertGreater(cleaned.loc[pd.Timestamp("2026-07-06"), "comex_stock_t"], 600000)
        self.assertGreater(cleaned.loc[pd.Timestamp("2026-07-08"), "comex_stock_t"], 600000)
        fig = build_copper_flow_spread_figure("5Y")
        stock = next(trace for trace in fig.data if trace.name == "COMEX 库存")
        xs = set(pd.to_datetime(stock.x))
        self.assertNotIn(t, xs)
        self.assertGreater(min(stock.y), 0)
        self.assertTrue(fig.layout.meta.get("data_quality_notes"))

    def test_hkma_real_m2_surge_is_not_arbitrarily_smoothed(self):
        snap = json.loads((ROOT / "data_snapshots/hkma_monetary_statistics.json").read_text(encoding="utf-8"))
        records = {r["end_of_month"]: r for r in snap["records"]}
        jan = records["2021-01"]
        dec = records["2020-12"]
        m2_mom = (jan["m2_hkd"] / dec["m2_hkd"] - 1) * 100
        m3_mom = (jan["m3_hkd"] / dec["m3_hkd"] - 1) * 100
        self.assertAlmostEqual(m2_mom, 17.3, delta=0.15)
        self.assertAlmostEqual(m3_mom, 17.3, delta=0.15)

    def test_us_tga_requires_actual_closing_balance(self):
        response = Mock()
        response.json.return_value = {"data": [
            {"record_date": "2026-10-06", "account_type": "Treasury General Account closing",
             "open_today_bal": "500000", "close_today_bal": None},
            {"record_date": "2026-10-06", "account_type": "Total Operating Balance",
             "open_today_bal": "650000", "close_today_bal": "700000"},
            {"record_date": "2026-10-07", "account_type": "Treasury General Account closing",
             "open_today_bal": "700000", "close_today_bal": "600000"},
        ]}
        response.raise_for_status.return_value = None
        requests = Mock()
        requests.get.return_value = response
        getter = undecorated("data.py", "get_tga_daily", {
            "pd": pd, "requests": requests,
            "_fred_series": Mock(side_effect=AssertionError("unexpected WTREGEN fallback")),
            "read_verified_tga_snapshot": lambda path: pd.DataFrame(),
            "TGA_SNAPSHOT_PATH": Path("not-present"),
            "parse_dts_tga_rows": parse_dts_tga_rows,
        })
        out = getter().set_index("observation_date")
        self.assertAlmostEqual(out.loc[pd.Timestamp("2026-10-06"), "TGA_DAILY"], 0.5)
        self.assertAlmostEqual(out.loc[pd.Timestamp("2026-10-07"), "TGA_DAILY"], 0.6)
        self.assertEqual(len(out), 2)

    def test_us_tga_unlabeled_opening_balance_uses_named_weekly_fallback(self):
        response = Mock()
        response.json.return_value = {"data": [
            {"record_date": "2026-10-06", "account_type": "Treasury General Account Opening Balance",
             "open_today_bal": "500000", "close_today_bal": None},
        ]}
        response.raise_for_status.return_value = None
        get_weekly = Mock(return_value=pd.DataFrame({
            "observation_date": [pd.Timestamp("2026-10-05")], "WTREGEN": [500000.0],
        }))
        requests = Mock()
        requests.get.return_value = response
        getter = undecorated("data.py", "get_tga_daily", {
            "pd": pd, "requests": requests, "_fred_series": get_weekly,
            "read_verified_tga_snapshot": lambda path: pd.DataFrame(),
            "TGA_SNAPSHOT_PATH": Path("not-present"),
            "parse_dts_tga_rows": parse_dts_tga_rows,
        })
        frame = getter()
        get_weekly.assert_called_once_with("WTREGEN")
        self.assertAlmostEqual(frame["TGA_DAILY"].iloc[0], 0.5)
        self.assertTrue(frame.attrs["is_fallback"])
        self.assertEqual(frame.attrs["frequency"], "weekly")

    def test_dgs10_missing_leg_is_tracked_as_derived(self):
        sources = {
            "DGS10": pd.DataFrame({
                "observation_date": pd.to_datetime(["2026-10-05"]),
                "DGS10": [4.15],
            }),
            "DFII10": pd.DataFrame({
                "observation_date": pd.to_datetime(["2026-10-05", "2026-10-06"]),
                "DFII10": [1.8, 1.83],
            }),
            "T10YIE": pd.DataFrame({
                "observation_date": pd.to_datetime(["2026-10-05", "2026-10-06"]),
                "T10YIE": [2.35, 2.34],
            }),
        }
        getter = undecorated("data.py", "get_dgs10", {
            "pd": pd, "_fred_series": lambda series_id: sources[series_id],
        })
        result = getter().set_index("observation_date")
        self.assertAlmostEqual(result.loc[pd.Timestamp("2026-10-05"), "DGS10"], 4.15)
        self.assertAlmostEqual(result.loc[pd.Timestamp("2026-10-06"), "DGS10"], 4.17)
        self.assertEqual(result.attrs["identity_derived_dates"], ["2026-10-06"])
        self.assertTrue(result.attrs["identity_backfill"])

    def test_china_2y_is_not_derived_when_primary_quote_missing(self):
        response = Mock()
        response.json.return_value = {"result": {"data": [{
            "SOLAR_DATE": "2026-10-07", "EMM00588704": None,
            "EMM00166466": "2.10", "EMM01276014": "0.90",
        }], "pages": 1}}
        response.raise_for_status.return_value = None
        with patch("macro_platform.asia_rates.requests.get", return_value=response):
            getter = load_china_gov_yields.__wrapped__ if hasattr(load_china_gov_yields, "__wrapped__") else load_china_gov_yields
            frame = getter()
        self.assertTrue(pd.isna(frame["china_2y"].iloc[0]))
        self.assertAlmostEqual(frame["china_10y_2y_pct"].iloc[0], 0.9)


if __name__ == "__main__":
    unittest.main()

