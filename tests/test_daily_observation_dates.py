"""Completed daily bars keep source dates across session and UTC rollovers."""
import json
import ast
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from urllib.parse import quote

import pandas as pd
import requests

from macro_platform.market_history import completed_daily_closes


def bar(day, zone, next_day, instrument="ETF"):
    def epoch(value):
        return int(pd.Timestamp(value, tz=zone).timestamp())
    return {"meta": {"exchangeTimezoneName": zone, "instrumentType": instrument,
            "currentTradingPeriod": {"regular": {"start": epoch(next_day + " 09:30"),
                                                   "end": epoch(next_day + " 16:00")}}},
            "timestamp": [epoch(day + " 09:30")],
            "indicators": {"quote": [{"close": [123.45]}]}}


class DailyObservationDates(unittest.TestCase):
    def test_live_history_compares_hosts_instead_of_accepting_old_first_response(self):
        source = Path(__file__).resolve().parents[1] / "app.py"
        node = next(n for n in ast.parse(source.read_text()).body
                    if isinstance(n, ast.FunctionDef) and n.name == "get_yahoo_daily_history")
        node.decorator_list = []
        frames = [pd.DataFrame({"observation_date":pd.to_datetime([day]), "close":[value]})
                  for day,value in [("2026-11-04",7688.62),("2026-11-05",7353.73)]]
        ns={"pd":pd,"requests":requests,"quote":quote,"http_get":Mock(return_value=Mock(
            json=lambda:{"chart":{"result":[{}]}})),
            "completed_daily_closes":Mock(side_effect=frames)}
        exec(compile(ast.Module(body=[node],type_ignores=[]),str(source),"exec"),ns)
        result=ns["get_yahoo_daily_history"]("^GSPC")
        self.assertEqual(result.close.tolist(),[7353.73])
        self.assertEqual(ns["http_get"].call_count,2)

    def test_winter_us_postmarket_keeps_just_completed_session(self):
        node = bar("2026-11-05", "America/New_York", "2026-11-06")
        self.assertTrue(completed_daily_closes(node, "2026-11-05T20:00Z").empty)
        frame = completed_daily_closes(node, "2026-11-05T22:00Z")
        self.assertEqual(frame.observation_date.dt.strftime("%Y-%m-%d").tolist(), ["2026-11-05"])
        self.assertEqual(frame.close.tolist(), [123.45])

    def test_summer_us_uses_exchange_timezone(self):
        node = bar("2026-07-02", "America/New_York", "2026-07-06")
        self.assertTrue(completed_daily_closes(node, "2026-07-02T19:00Z").empty)
        self.assertEqual(len(completed_daily_closes(node, "2026-07-02T20:20Z")), 1)

    def test_explicit_short_session_takes_precedence(self):
        node = bar("2026-11-27", "America/New_York", "2026-11-30")
        node["tradingPeriods"] = {"regular": [[{
            "start": int(pd.Timestamp("2026-11-27T14:30Z").timestamp()),
            "end": int(pd.Timestamp("2026-11-27T18:00Z").timestamp())}]]}
        self.assertTrue(completed_daily_closes(node, "2026-11-27T17:00Z").empty)
        self.assertEqual(len(completed_daily_closes(node, "2026-11-27T18:10Z")), 1)

    def test_cash_markets_do_not_wait_until_local_midnight(self):
        for zone, now in [("Asia/Hong_Kong", "2026-11-05T08:20Z"),
                          ("Asia/Tokyo", "2026-11-05T06:50Z")]:
            with self.subTest(zone=zone):
                self.assertEqual(len(completed_daily_closes(bar("2026-11-05", zone, "2026-11-06"), now)), 1)

    def test_unknown_venue_and_futures_require_session_evidence(self):
        for zone, instrument in [("Europe/London", "ETF"), ("America/New_York", "FUTURE")]:
            node = bar("2026-11-05", zone, "2026-11-06", instrument)
            self.assertTrue(completed_daily_closes(node, "2026-11-05T23:00Z").empty)

    def test_crypto_daily_boundary_is_utc_even_with_local_metadata(self):
        node = bar("2026-11-05", "America/New_York", "2026-11-06", "CRYPTOCURRENCY")
        node["timestamp"] = [int(pd.Timestamp(day).timestamp()) for day in
                             ["2026-11-05T00:00Z", "2026-11-06T00:00Z"]]
        node["indicators"]["quote"][0]["close"] = [100., 90.]
        frame = completed_daily_closes(node, "2026-11-06T01:00Z")
        self.assertEqual(frame.observation_date.dt.strftime("%Y-%m-%d").tolist(), ["2026-11-05"])

    def test_rolling_nikkei_window_retains_old_verified_history(self):
        from scripts.update_nikkei225_snapshot import save_snapshot
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nikkei.json"
            path.write_text(json.dumps({"records": [{"date":"2020-11-04", "close":24000},
                                                     {"date":"2026-11-04", "close":50000}]}))
            frame = pd.DataFrame({"observation_date": pd.to_datetime(["2026-11-04", "2026-11-05"]),
                                  "close": [50000, 49000]})
            save_snapshot(frame, path)
            self.assertEqual([row["date"] for row in json.loads(path.read_text())["records"]],
                             ["2020-11-04", "2026-11-04", "2026-11-05"])
            broken = pd.DataFrame({"observation_date":pd.to_datetime(["2026-11-03", "2026-11-05"]),
                                   "close":[49000,49000]})
            with self.assertRaises(ValueError):
                save_snapshot(broken, path)


if __name__ == "__main__":
    unittest.main()
