"""Same-date implied-volatility ratios and SPX-specific volume provenance."""
from copy import deepcopy
from datetime import datetime, timezone
import unittest

import pandas as pd

from macro_platform.spx_options import PRODUCT, parse_daily
from macro_platform.echarts_axes import build_adaptive_echarts_option, build_safe_echarts_option
from test_series_calendars import builders, frame


class SpxSentimentTests(unittest.TestCase):
    def payload(self):
        return {"ratios": [{"name": PRODUCT + " PUT/CALL RATIO", "value": "1.13"}],
                PRODUCT: [{"name": "VOLUME", "call": 2296438, "put": 2597825, "total": 4894263},
                          {"name": "OPEN INTEREST", "call": 1, "put": 7, "total": 8}]}

    def test_published_spx_volume_ratio_reconciles_and_does_not_use_open_interest(self):
        row = parse_daily(self.payload(), "2026-11-03", datetime(2026, 11, 4, tzinfo=timezone.utc))
        self.assertEqual(row["ratio"], 1.13)
        self.assertEqual(row["put_volume"], 2597825)
        self.assertIn("2026-11-03_daily_options", row["source_url"])

    def test_rejects_other_products_bad_totals_zero_calls_and_uncompleted_dates(self):
        cases = []
        bad = self.payload(); bad["ratios"][0]["name"] = "TOTAL PUT/CALL RATIO"; cases.append(bad)
        bad = self.payload(); bad[PRODUCT][0]["name"] = "OPEN INTEREST"; cases.append(bad)
        for key, value in (("call", 0), ("put", -1), ("total", 123)):
            bad = self.payload(); bad[PRODUCT][0][key] = value; cases.append(bad)
        bad = self.payload(); bad["ratios"][0]["value"] = 2; cases.append(bad)
        now = datetime(2026, 11, 4, 12, tzinfo=timezone.utc)
        for bad in cases:
            with self.assertRaises(ValueError): parse_daily(bad, "2026-11-03", now)
        for day in ("2026-11-04", "2026-11-07", "2099-01-01"):
            with self.assertRaises(ValueError): parse_daily(self.payload(), day, now)

    def test_ratios_keep_direction_gaps_and_shared_sentiment_axis(self):
        ns = builders()
        dates = ["2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06"]
        sources = {"VIXCLS": frame(dates, "VIXCLS", [20., 0., 24., None]),
                   "VXVCLS": frame(dates, "VXVCLS", [25., 25., 0., 21.])}
        tail = {"SKEW": frame(pd.bdate_range(end=dates[0], periods=5), "SKEW", [150.] * 5),
                "VVIX": frame(dates[:1], "VVIX", [100.]),
                "VIX9D": frame(dates, "VIX9D", [18., 19., None, 20.])}
        ns["get_fred_series"] = lambda key: sources[key].copy()
        ns["load_tail_risk_snapshot"] = lambda key: tail[key].copy()
        ns["load_spx_put_call_snapshot"] = lambda: frame(pd.bdate_range(end="2026-10-02", periods=63), "SPX_PCR", [1.13] * 63)
        fig = ns["build_fig10"]("1M")
        traces = {t.name: t for t in fig.data}
        self.assertEqual(list(pd.Series(traces["VIX/VIX3M (R1)"].y).dropna()), [.8, 0.])
        self.assertEqual(list(pd.Series(traces["9D/30D (R1)"].y).dropna()), [.9])
        self.assertEqual(list(pd.Series(traces["VVIX/VIX (R4)"].y).dropna()), [5.])
        self.assertEqual(list(pd.Series(traces["SPX P/C 63D MA (R1)"].y).dropna()), [1.13])
        for adapter in (build_adaptive_echarts_option, build_safe_echarts_option):
            option = adapter(fig, "1M")
            self.assertEqual(len(option["yAxis"]), 5)
            axes = {series["name"]: series["yAxisIndex"] for series in option["series"]}
            self.assertEqual(axes["VIX/VIX3M (R1)"], 1)
            self.assertEqual(axes["VVIX/VIX (R4)"], 4)
            self.assertEqual(axes["9D/30D (R1)"], 1)
            self.assertEqual(axes["SPX P/C 63D MA (R1)"], 1)
            self.assertTrue(all(axis["scale"] for axis in option["yAxis"]))
            self.assertFalse(any("VIX3M−VIX" in name for name in axes))

    def test_means_use_full_history_and_connect_observations_in_both_renderers(self):
        ns = builders()
        dates = pd.bdate_range("2026-06-01", periods=90)
        ns["get_fred_series"] = lambda key: frame(dates, key, [20.] * len(dates))
        ns["load_spx_put_call_snapshot"] = lambda: frame(dates[::-1], "SPX_PCR", list(range(90, 0, -1)))
        ns["load_tail_risk_snapshot"] = lambda key: frame(dates, key, list(range(100, 190)))
        full = ns["build_fig10"]("5Y")
        traces = {t.name: t for t in full.data}
        pc = traces["SPX P/C 63D MA (R1)"]
        skew = traces["SKEW 5D MA (R2)"]
        self.assertTrue(pd.Series(pc.y).iloc[:62].isna().all())
        self.assertEqual(pc.y[62], 32.)
        self.assertEqual(pc.y[-1], 59.)
        self.assertTrue(pd.Series(skew.y).iloc[:4].isna().all())
        self.assertEqual(skew.y[4], 102.)
        self.assertEqual(skew.y[-1], 187.)
        cropped = ns["build_fig10"]("1M")
        for name in (pc.name, skew.name):
            trace = next(t for t in cropped.data if t.name == name)
            expected = pd.Series(traces[name].y, index=pd.DatetimeIndex(traces[name].x))
            self.assertEqual(list(trace.y), list(expected.loc[pd.DatetimeIndex(trace.x)]))
            self.assertTrue(pd.notna(trace.y[0]))
        for adapter in (build_adaptive_echarts_option, build_safe_echarts_option):
            option = adapter(cropped, "1M")
            self.assertTrue(all(s["connectNulls"] for s in option["series"]))
        self.assertTrue(all(t.connectgaps and t.line.dash == "solid" for t in cropped.data))

    def test_vvix_ratio_keeps_gaps_and_never_reuses_another_days_vix(self):
        ns = builders()
        dates = ["2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06", "2026-10-07"]
        ns["get_fred_series"] = lambda key: frame(dates, key, [20., 0., None, 25., 30.])
        def load(symbol):
            if symbol == "VVIX":
                return frame(dates[:4] + ["2026-10-08"], symbol, [100., 110., 120., None, 130.])
            return frame([], symbol, [])
        ns["load_tail_risk_snapshot"] = load
        for period in ("5Y", "1Y", "6M", "3M", "1M"):
            fig = ns["build_fig10"](period)
            trace = next(t for t in fig.data if t.name == "VVIX/VIX (R4)")
            self.assertEqual(list(pd.Series(trace.y).dropna()), [5.])
            self.assertEqual(list(pd.Series(trace.y).isna()), [False, True, True, True, True, True])
            self.assertEqual(trace.yaxis, "y5")
            option = build_adaptive_echarts_option(fig, period)
            series = next(s for s in option["series"] if s["name"] == trace.name)
            self.assertTrue(series["connectNulls"])


if __name__ == "__main__": unittest.main()
