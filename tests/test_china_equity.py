import copy
import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from macro_platform.china_equity import (
    SERIES, SNAPSHOT, parse_csindex_history, build_china_drawdown_figure,
)
from macro_platform.echarts_axes import build_adaptive_echarts_option
from scripts.update_china_equity_snapshot import save_snapshot


def payload(code="932000"):
    return {"success": True, "data": [
        {"indexCode": code, "indexNameCn": SERIES[code]["name"], "tradeDate": day, "close": close}
        for day, close in [("19900101", 1000), ("20131231", 1000),
                           ("20150612", 4000), ("20261026", 2000), ("20261027", 2200)]]}


class ChinaEquityTests(unittest.TestCase):
    def test_official_identity_base_date_and_completed_session(self):
        frame = parse_csindex_history(payload(), "932000", now="2026-10-27 06:00Z")
        self.assertEqual(frame.observation_date.min(), pd.Timestamp("2013-12-31"))
        self.assertEqual(frame.observation_date.max(), pd.Timestamp("2026-10-26"))
        closed = parse_csindex_history(payload(), "932000", now="2026-10-27 08:00Z")
        self.assertEqual(closed.close.iloc[-1], 2200)
        bad = payload(); bad["data"][0]["indexCode"] = "399303"
        with self.assertRaises(ValueError): parse_csindex_history(bad, "932000")
        bad = payload(); bad["data"][0]["indexNameCn"] = "国证2000"
        with self.assertRaises(ValueError): parse_csindex_history(bad, "932000")

    def test_old_peak_survives_every_viewport_for_all_three_indices(self):
        history = pd.DataFrame({"observation_date": pd.to_datetime(["2015-06-12", "2026-10-26"]),
                                "close": [4000., 2000.]})
        figure = build_china_drawdown_figure({code: history for code in SERIES})
        self.assertEqual([trace.name for trace in figure.data], [config["name"] for config in SERIES.values()])
        for row in figure.layout.meta["drawdown_summary"]:
            self.assertEqual(row["peak_date"], "2015-06-12")
            self.assertEqual(row["decline_pct"], 50)
        for period in ("5Y", "1Y", "6M", "3M", "1M"):
            option = build_adaptive_echarts_option(figure, period)
            self.assertEqual([series["data"][-1][1] for series in option["series"]], [-50., -50., -50.])

    def test_missing_index_is_explicit_without_removing_good_legs(self):
        frame = parse_csindex_history(payload(), "932000", now="2026-10-27 08:00Z")
        figure = build_china_drawdown_figure({"932000": frame})
        self.assertEqual(len(figure.data), 1)
        self.assertEqual(figure.layout.meta["missing_series"], ["沪深300", "中证1000"])

    def test_atomic_snapshot_rejects_lost_dates_partial_pair_and_stale_data(self):
        histories = {code: pd.DataFrame({"observation_date": pd.bdate_range(config["base_date"], "2026-10-26"),
                                         "close": 1000.}) for code, config in SERIES.items()}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "prices.json"
            self.assertTrue(save_snapshot(histories, path, now="2026-10-27 08:00Z"))
            original = path.read_bytes()
            self.assertFalse(save_snapshot(histories, path, now="2026-10-27 08:00Z"))
            bad = copy.deepcopy(histories); bad["932000"] = bad["932000"].drop(index=100)
            with self.assertRaises(ValueError): save_snapshot(bad, path, now="2026-10-27 08:00Z")
            self.assertEqual(path.read_bytes(), original)
            with self.assertRaises(ValueError): save_snapshot(histories, path, now="2026-11-10 08:00Z")
            self.assertEqual(path.read_bytes(), original)
            with self.assertRaises(KeyError): save_snapshot({"000300": histories["000300"]}, path)
            self.assertEqual(path.read_bytes(), original)

    def test_committed_snapshot_is_official_daily_history_including_old_highs(self):
        data = json.loads(SNAPSHOT.read_text())
        self.assertEqual(set(data["series"]), set(SERIES))
        figure = build_china_drawdown_figure()
        self.assertEqual(len(figure.data), 3)
        for row in figure.layout.meta["drawdown_summary"]:
            self.assertLessEqual(row["history_start"], "2014-01-10")
            self.assertGreater(row["close"], 0)
            self.assertGreaterEqual(row["decline_pct"], 0)


if __name__ == "__main__":
    unittest.main()
