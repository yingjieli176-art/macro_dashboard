"""Price-basis, historical-peak, completed-bar and viewport regression tests."""
import ast
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from macro_platform.equity_drawdown import (
    PRICE_BASIS, SERIES, build_drawdown_figure, calculate_drawdown,
    load_equity_history, parse_yahoo_history,
)
from macro_platform.echarts_axes import build_adaptive_echarts_option
from scripts.update_us_equity_snapshot import save_snapshot

ROOT = Path(__file__).resolve().parents[1]


def prices(values, dates=None):
    return pd.DataFrame({"observation_date": pd.to_datetime(dates or pd.bdate_range("2026-10-19", periods=len(values))),
                         "close": values})


def yahoo_payload():
    days = pd.to_datetime(["2026-10-23 13:30Z", "2026-10-26 13:30Z"])
    return {"chart": {"result": [{"meta": {
        "symbol": "RSP", "currency": "USD", "instrumentType": "ETF", "dataGranularity": "1d",
        "exchangeTimezoneName": "America/New_York", "currentTradingPeriod": {"regular": {
            "start": int(days[-1].timestamp()), "end": int(pd.Timestamp("2026-10-26 20:00Z").timestamp())}}},
        "timestamp": [int(day.timestamp()) for day in days],
        "indicators": {"quote": [{"close": [100., 90.]}], "adjclose": [{"adjclose": [50., 48.]}]}}]}}


class EquityDrawdownTests(unittest.TestCase):
    def test_running_peak_recovers_and_never_looks_ahead(self):
        frame = calculate_drawdown(prices([100, 120, 90, 110, 125, 100]))
        self.assertEqual(frame.peak.tolist(), [100, 120, 120, 120, 125, 125])
        for got, expected in zip(frame.drawdown_pct, [0, 0, -25, -100/12, 0, -20]):
            self.assertAlmostEqual(got, expected)
        self.assertEqual(frame.drop_amount.tolist(), [0, 0, 30, 10, 0, 25])

    def test_invalid_prices_are_gaps_not_filled_or_false_peaks(self):
        frame = calculate_drawdown(prices([100, None, -1, float("inf"), 80]))
        self.assertTrue(frame.drawdown_pct.iloc[1:4].isna().all())
        self.assertEqual(frame.peak.iloc[-1], 100)
        self.assertAlmostEqual(frame.drawdown_pct.iloc[-1], -20)

    def test_duplicate_dates_and_repeated_highs_keep_a_consistent_peak_date(self):
        frame = calculate_drawdown(prices([100, 90, 80, 100], ["2026-10-19", "2026-10-20", "2026-10-20", "2026-10-21"]))
        self.assertEqual(frame.close.tolist(), [100, 80, 100])
        self.assertEqual(frame.peak_date.iloc[-1], pd.Timestamp("2026-10-19"))

    def test_daily_quote_close_not_dividend_adjusted_and_no_running_session(self):
        payload = yahoo_payload()
        frame = parse_yahoo_history(payload, "RSP", now="2026-10-26 19:00Z")
        self.assertEqual(frame.close.tolist(), [100.])
        frame = parse_yahoo_history(payload, "RSP", now="2026-10-26 20:20Z")
        self.assertEqual(frame.close.tolist(), [100., 90.])

    def test_wrong_symbol_currency_instrument_and_monthly_max_are_rejected(self):
        for field, value in [("symbol", "SPY"), ("currency", "HKD"),
                             ("instrumentType", "INDEX"), ("dataGranularity", "1mo")]:
            payload = yahoo_payload()
            payload["chart"]["result"][0]["meta"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                parse_yahoo_history(payload, "RSP", now="2026-10-27 10:00Z")

    def test_peak_precedes_display_window_and_summary_uses_latest_actual_close(self):
        history = prices([200., 100., 160.], ["2010-01-04", "2026-09-25", "2026-10-26"])
        fig = build_drawdown_figure({"SPX": history, "RSP": history.copy()})
        self.assertEqual(len(fig.data[0].x), 2)
        self.assertAlmostEqual(fig.data[0].y[-1], -20)
        row = fig.layout.meta["drawdown_summary"][0]
        self.assertEqual(row["peak_date"], "2010-01-04")
        self.assertEqual(row["drop_amount"], 40)
        self.assertAlmostEqual(row["decline_pct"], 20)
        for period in ("5Y", "1Y", "6M", "3M", "1M"):
            option = build_adaptive_echarts_option(fig, period)
            self.assertEqual(len(option["series"]), 2)
            self.assertAlmostEqual(option["series"][0]["data"][-1][1], -20)
            self.assertTrue(all(zoom["filterMode"] == "filter" for zoom in option["dataZoom"]))
            self.assertTrue(option["yAxis"][0]["scale"])

    def test_missing_leg_is_explicit_and_does_not_remove_good_series(self):
        fig = build_drawdown_figure({"SPX": prices([100, 90])})
        self.assertEqual(len(fig.data), 1)
        self.assertIn(SERIES["RSP"]["name"], fig.layout.meta["missing_series"])
        self.assertEqual(len(fig.layout.meta["drawdown_summary"]), 1)

    def test_updater_is_atomic_and_rejects_stale_future_and_truncated_history(self):
        dates = pd.bdate_range("2003-05-01", "2026-10-26")
        histories = {key: pd.DataFrame({"observation_date": dates, "close": 100.}) for key in SERIES}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "observations.json"
            self.assertTrue(save_snapshot(histories, path, now="2026-10-27 10:00Z"))
            original = path.read_bytes()
            self.assertFalse(save_snapshot(histories, path, now="2026-10-27 10:00Z"))
            bad = copy.deepcopy(histories)
            bad["RSP"] = bad["RSP"].drop(index=100)
            with self.assertRaises(ValueError):
                save_snapshot(bad, path, now="2026-10-27 10:00Z")
            self.assertEqual(path.read_bytes(), original)
            with self.assertRaises(ValueError):
                save_snapshot(histories, path, now="2026-10-20 10:00Z")
            self.assertEqual(path.read_bytes(), original)
            with self.assertRaises(ValueError):
                save_snapshot(histories, path, now="2026-11-04 10:00Z")
            self.assertEqual(path.read_bytes(), original)

    def test_snapshot_updates_visible_without_waiting_for_cache_and_no_network(self):
        import macro_platform.equity_drawdown as module
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "observations.json"
            payload = {"price_basis": PRICE_BASIS, "series": {"SPX": {
                "symbol": "^GSPC", "frequency": "1d", "records": [{"date": "2020-01-02", "close": 100.}]}}}
            path.write_text(json.dumps(payload))
            with patch.object(module, "SNAPSHOT", path), patch("requests.get", side_effect=AssertionError):
                load_equity_history.clear()
                self.assertEqual(load_equity_history("SPX").close.tolist(), [100.])
                payload["series"]["SPX"]["records"].append({"date": "2020-01-03", "close": 90.})
                path.write_text(json.dumps(payload))
                self.assertEqual(load_equity_history("SPX").close.tolist(), [100., 90.])
                load_equity_history.clear()

    def test_app_calls_panel_with_independent_range_and_summary_table(self):
        source = (ROOT / "app.py").read_text()
        tree = ast.parse(source)
        render = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "render_macro_chart_9")
        self.assertIn("_render_equity_drawdown()", ast.get_source_segment(source, render))
        self.assertIn('"us_equity_drawdown", standard=True', source)
        self.assertIn('"前高－当前"', source)
        self.assertIn('"距前高跌幅"', source)


if __name__ == "__main__":
    unittest.main()
