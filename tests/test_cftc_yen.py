import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

import pandas as pd

from macro_platform.cftc_yen import parse_cftc_yen, read_cftc_yen, SNAPSHOT
from macro_platform.yen_carry import POSITION_NAME, build_yen_carry_figure
from macro_platform.echarts_axes import option_observation_health
from macro_platform.freshness_overview import figure_rows
from scripts.update_cftc_yen import fetch_cftc_yen, save_cftc_yen


def row(day="2026-10-20", long=250, short=400):
    return {"market_and_exchange_names": "JAPANESE YEN - CHICAGO MERCANTILE EXCHANGE",
            "cftc_contract_market_code": "097741", "futonly_or_combined": "FutOnly",
            "report_date_as_yyyy_mm_dd": day, "noncomm_positions_long_all": str(long),
            "noncomm_positions_short_all": str(short), "open_interest_all": "1000"}


class CFTCJPYTests(unittest.TestCase):
    def test_net_is_noncommercial_long_minus_short_and_uses_position_date(self):
        frame = parse_cftc_yen([row()], now="2026-10-23")
        self.assertEqual(frame.net_contracts.tolist(), [-150])
        self.assertEqual(frame.observation_date.iloc[0], pd.Timestamp("2026-10-20"))

    def test_wrong_instrument_report_type_bad_counts_and_future_are_rejected(self):
        for patch in ({"cftc_contract_market_code": "099741"}, {"futonly_or_combined": "Combined"},
                      {"market_and_exchange_names": "EURO FX"}, {"noncomm_positions_long_all": "nan"},
                      {"noncomm_positions_short_all": "-1"}, {"noncomm_positions_long_all": "1.5"},
                      {"open_interest_all": "10"}, {"report_date_as_yyyy_mm_dd": "2099-01-01"}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                parse_cftc_yen([row() | patch], now="2026-10-23")
        with self.assertRaises(ValueError):
            parse_cftc_yen([row(), row()], now="2026-10-23")

    def test_official_endpoint_query_validates_identity_and_parses_response(self):
        get = Mock(return_value=Mock(json=lambda: [row()]))
        self.assertEqual(fetch_cftc_yen(now="2026-10-23", get=get).net_contracts.tolist(), [-150])
        kwargs = get.call_args.kwargs
        self.assertIn("097741", kwargs["params"]["$where"])
        self.assertIn("futonly_or_combined", kwargs["params"]["$select"])

    def test_snapshot_roundtrip_and_failed_refresh_preserve_last_good(self):
        days = pd.date_range("2020-01-07", "2026-10-20", freq="W-TUE")
        frame = parse_cftc_yen([row(day.strftime("%Y-%m-%d")) for day in days], now="2026-10-23")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"positions.json"
            self.assertTrue(save_cftc_yen(frame, path, now="2026-10-23"))
            before = path.read_bytes()
            self.assertFalse(save_cftc_yen(frame, path, now="2026-10-23"))
            self.assertEqual(read_cftc_yen(path, now="2026-10-23").net_contracts.tolist(), frame.net_contracts.tolist())
            for bad in (frame.iloc[-10:], frame.iloc[:-1], frame.drop(index=20)):
                with self.assertRaises(ValueError):
                    save_cftc_yen(bad, path, now="2026-10-23")
                self.assertEqual(path.read_bytes(), before)
            payload = json.loads(before)
            payload["records"][0]["net_contracts"] = 999
            path.write_text(json.dumps(payload))
            self.assertTrue(read_cftc_yen(path, now="2026-10-23").empty)

    def test_real_bundled_observations_and_weekly_cadence_reach_chart(self):
        frame = read_cftc_yen(SNAPSHOT)
        self.assertGreaterEqual(len(frame), 240)
        self.assertTrue(frame.net_contracts.eq(frame.noncommercial_long-frame.noncommercial_short).all())
        fig = build_yen_carry_figure("5Y", us=None, japan=None, fx=None, positions=frame)
        self.assertEqual(len(fig.data), 1)
        self.assertEqual(fig.data[0].name, POSITION_NAME)
        self.assertEqual(fig.data[0].yaxis, "y4")
        self.assertAlmostEqual(fig.data[0].y[-1], frame.net_contracts.iloc[-1]/10000)
        self.assertLessEqual(len(fig.data[0].x), len(frame))
        health = option_observation_health({"series": [{"name": POSITION_NAME,
            "data": [["2026-10-20", -1.5]]}]}, now="2026-10-26")
        self.assertEqual(health["cadence_by_name"][POSITION_NAME], "周频")
        self.assertFalse(health["stale_names"])
        self.assertEqual(figure_rows({18: fig})[-1]["频率"], "周频")


if __name__ == "__main__":
    unittest.main()
