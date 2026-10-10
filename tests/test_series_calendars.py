"""A different source's calendar must not split an observed series."""
import ast
from pathlib import Path
import unittest
from unittest.mock import patch

import pandas as pd
import plotly.graph_objects as go
import requests

import data
from macro_platform.chart_axes import RANGE_OFFSETS
from macro_platform.echarts_axes import build_adaptive_echarts_option
from macro_platform.us_equity_risk import load_vixeq_snapshot


def builders():
    source = Path(__file__).resolve().parents[1] / "app.py"
    names = {"add_line", "_mark_missing_series", "filter_range",
             "build_fig1", "build_fig9", "build_fig10", "build_fig11"}
    ns = {"pd": pd, "go": go, "RANGE_OFFSETS": RANGE_OFFSETS,
          "apply_chart_style": lambda fig, *args: fig,
          "chart_height": lambda *args: 420}
    nodes = [n for n in ast.parse(source.read_text()).body
             if isinstance(n, ast.FunctionDef) and n.name in names]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), ns)
    return ns


def frame(dates, column, values):
    return pd.DataFrame({"observation_date": pd.to_datetime(dates), column: values})


def values(trace):
    return pd.Series(trace.y, index=pd.DatetimeIndex(trace.x))


class SeriesCalendarIntegrity(unittest.TestCase):
    def test_real_policy_and_equity_sources_keep_exact_dates_in_all_windows(self):
        ns = builders()
        with patch.object(requests.sessions.Session, "request", side_effect=requests.Timeout("offline")):
            policy = {c: getter() for c, getter in (
                ("IORB", data.get_iorb), ("RRPONTSYAWARD", data.get_rrp_rate),
                ("EFFR", data.get_effr), ("SOFR", data.get_sofr))}
            risk = {c: data._fred_series(c) for c in ("VIXCLS", "VXVCLS", "SP500")}
        risk["VIXEQ"] = load_vixeq_snapshot()
        for c, getter in (("IORB", "get_iorb"), ("RRPONTSYAWARD", "get_rrp_rate"),
                          ("EFFR", "get_effr"), ("SOFR", "get_sofr")):
            ns[getter] = lambda c=c: policy[c].copy()
        ns["get_fred_series"] = lambda c: risk[c].copy()
        ns["load_vixeq_snapshot"] = lambda: risk["VIXEQ"].copy()
        for window in RANGE_OFFSETS:
            for number, sources, names in (
                (1, policy, {"IORB": "IORB", "RRPONTSYAWARD": "ON RRP", "EFFR": "EFFR", "SOFR": "SOFR"}),
                (9, risk, {"VIXCLS": "VIX", "VIXEQ": "VIXEQ", "SP500": "S&P 500 (R1)"}),
            ):
                fig = ns[f"build_fig{number}"](window)
                latest = max(f.observation_date.max() for f in sources.values())
                for column, name in names.items():
                    with self.subTest(chart=number, window=window, series=name):
                        original = sources[column]
                        expected = original.loc[original.observation_date >= latest - RANGE_OFFSETS[window]]
                        trace = next(t for t in fig.data if t.name == name)
                        pd.testing.assert_series_equal(values(trace), pd.Series(
                            expected[column].to_numpy(), index=pd.DatetimeIndex(expected.observation_date)),
                            check_names=False)

    def test_source_failure_and_true_missing_readings_remain_distinct(self):
        ns = builders()
        dates = ["2026-10-01", "2026-10-02", "2026-10-04"]
        ns["get_iorb"] = lambda: (_ for _ in ()).throw(requests.Timeout("IORB unavailable"))
        for getter, c in (("get_rrp_rate", "RRPONTSYAWARD"), ("get_effr", "EFFR"), ("get_sofr", "SOFR")):
            ns[getter] = lambda c=c: frame(dates, c, [4., None, 4.1])
        fig = ns["build_fig1"]("1M")
        self.assertEqual(len(fig.data), 3)
        self.assertIn("IORB", fig.layout.meta["missing_series"])
        self.assertTrue(pd.isna(fig.data[0].y[1]))
        risk = {"VIXCLS": frame(dates, "VIXCLS", [20., None, 21.]),
                "VXVCLS": frame(["2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04"],
                                 "VXVCLS", [22., 22., 22., 23.]),
                "SP500": frame(dates, "SP500", [6000., 6100., 6200.])}
        ns["get_fred_series"] = lambda c: risk[c].copy()
        ns["load_vixeq_snapshot"] = lambda: frame(dates, "VIXEQ", [40., 41., 42.])
        fig = ns["build_fig9"]("1M")
        trace = next(t for t in fig.data if t.name == "VIX")
        self.assertEqual(list(pd.to_datetime(trace.x)), list(pd.to_datetime(dates)))
        self.assertTrue(pd.isna(trace.y[1]))
        spread = next(t for t in fig.data if t.name == "VIX3M−VIX (R2)")
        self.assertEqual(list(pd.Series(spread.y).isna()), [False, True, True, False])
        rendered = next(s for s in build_adaptive_echarts_option(fig, "1M")["series"] if s["name"] == "VIX")
        self.assertIsNone(rendered["data"][1][1])
        self.assertFalse(rendered["connectNulls"])

    def test_metals_do_not_inherit_other_markets_dates_or_fabricate_ratios(self):
        ns = builders()
        dates = ["2026-10-01", "2026-10-02", "2026-10-03"]
        ns["_load_yahoo_histories"] = lambda symbols: {
            "GC=F": frame(dates, "close", [4000., None, 4100.]),
            "SI=F": frame([dates[0], dates[2]], "close", [50., 51.])}
        ns["get_fred_series"] = lambda c: frame([dates[0], "2026-10-04"], c, [20., 21.])
        fig = ns["build_fig10"]("1M")
        self.assertEqual(len(next(t for t in fig.data if t.name == "Gold").x), 3)
        self.assertEqual(len(next(t for t in fig.data if t.name == "Silver (R1)").x), 2)
        ratio = next(t for t in fig.data if t.name == "Gold/Silver Ratio (R2)")
        self.assertEqual(len(ratio.x), 3)
        self.assertTrue(pd.isna(ratio.y[1]))
        self.assertAlmostEqual(ratio.y[0], 80.)

    def test_eth_only_dates_cannot_change_btc_volatility(self):
        ns = builders()
        dates = pd.date_range("2026-08-01", periods=60)
        btc = pd.Series([100000. + i * 200 + (i % 3) * 300 for i in range(60)])
        eth_dates = dates.union(pd.DatetimeIndex([dates[20] + pd.Timedelta(hours=12)]))
        ns["_load_yahoo_histories"] = lambda symbols: {
            "BTC-USD": frame(dates, "close", btc),
            "ETH-USD": frame(eth_dates, "close", [4000.] * len(eth_dates))}
        fig = ns["build_fig11"]("3M")
        actual = next(t for t in fig.data if t.name == "BTC 30D 实际波动率 · R3")
        expected = btc.pct_change(fill_method=None).rolling(30, min_periods=20).std() * 365. ** .5 * 100.
        pd.testing.assert_series_equal(values(actual), pd.Series(expected.to_numpy(), index=dates), check_names=False, check_freq=False)
        self.assertEqual(len(next(t for t in fig.data if t.name == "BTC · USD").x), 60)


if __name__ == "__main__":
    unittest.main()
