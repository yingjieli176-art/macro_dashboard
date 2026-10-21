import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from macro_platform.yen_index import parse_yahoo_yen, yen_index_from_fx, load_yen_market_index
from macro_platform.echarts_axes import option_observation_health
from scripts.update_yen_market import save_market_snapshot
from scripts.audit_source_freshness import audit


def payload():
    dates = pd.to_datetime(["2026-10-19 00:00Z", "2026-10-20 00:00Z", "2026-10-21 12:00Z"])
    return {"chart": {"result": [{"meta": {"symbol": "JPY=X", "currency": "JPY",
        "instrumentType": "CURRENCY", "exchangeTimezoneName": "Europe/London"},
        "timestamp": [int(day.timestamp()) for day in dates],
        "indicators": {"quote": [{"close": [160., 125., 100.]}],
                       "adjclose": [{"adjclose": [1., 1., 1.]}]}}]}}


class YenMarketTests(unittest.TestCase):
    def test_uses_actual_closes_and_inverse_direction_excludes_running_bar(self):
        frame = parse_yahoo_yen(payload(), now="2026-10-21 13:00Z")
        self.assertEqual(frame.observation_date.dt.strftime("%Y-%m-%d").tolist(), ["2026-10-19", "2026-10-20"])
        self.assertEqual(frame.usd_jpy_close.tolist(), [160., 125.])
        self.assertEqual(frame.jpy_usd_index.tolist(), [62.5, 80.])

    def test_rejects_wrong_pair_and_measurement(self):
        for column, wrong in (("symbol", "JPYUSD=X"), ("currency", "USD"), ("instrumentType", "EQUITY")):
            data = copy.deepcopy(payload())
            data["chart"]["result"][0]["meta"][column] = wrong
            with self.subTest(column=column), self.assertRaises(ValueError):
                parse_yahoo_yen(data, now="2026-10-21 13:00Z")

    def test_updater_keeps_last_good_for_stale_truncated_or_incomplete_data(self):
        dates = pd.bdate_range("2021-10-21", "2026-10-20")
        frame = yen_index_from_fx(pd.DataFrame({"observation_date": dates, "usd_jpy_close": 160.}))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "yen.json"
            self.assertTrue(save_market_snapshot(frame, path, now="2026-10-21"))
            old = path.read_bytes()
            self.assertFalse(save_market_snapshot(frame, path, now="2026-10-21"))
            for bad, now in ((frame.iloc[:100], "2026-10-21"), (frame.iloc[:-5], "2026-10-21"),
                             (frame.drop(index=500), "2026-10-21"), (frame, "2026-10-27")):
                with self.assertRaises(ValueError):
                    save_market_snapshot(bad, path, now=now)
                self.assertEqual(path.read_bytes(), old)

    def test_snapshot_replacement_is_visible_without_waiting_for_ttl(self):
        import macro_platform.yen_index as source
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "yen.json"
            data = {"symbol": "JPY=X", "formula": "10000 / USDJPY", "records": [
                {"date": "2026-10-19", "usd_jpy_close": 160.}]}
            path.write_text(json.dumps(data))
            with patch.object(source, "MARKET_SNAPSHOT", path), patch("requests.get", side_effect=AssertionError):
                load_yen_market_index.clear()
                self.assertEqual(load_yen_market_index().jpy_usd_index.tolist(), [62.5])
                data["records"].append({"date": "2026-10-20", "usd_jpy_close": 125.})
                path.write_text(json.dumps(data))
                self.assertEqual(load_yen_market_index().jpy_usd_index.tolist(), [62.5, 80.])
                load_yen_market_index.clear()

    def test_fast_fx_has_two_business_day_budget_and_is_in_source_audit(self):
        option = {"series": [{"name": "JPY/USD Index (R3)", "data": [["2026-10-16", 63.]]}]}
        self.assertFalse(option_observation_health(option, now="2026-10-19")["stale_names"])
        self.assertEqual(option_observation_health(option, now="2026-10-21")["stale_names"], ["JPY/USD Index (R3)"])
        from macro_platform.yen_index import MARKET_SNAPSHOT
        latest = max(row["date"] for row in json.loads(MARKET_SNAPSHOT.read_text())["records"])
        reports = audit(now=pd.Timestamp(latest) + pd.offsets.BDay(1))
        yen = next(r for r in reports if r["file"] == "jpy_market_daily.json")
        self.assertEqual(yen["latest_by_name"]["usd_jpy_close"], latest)
        self.assertFalse(yen["stale_names"])
