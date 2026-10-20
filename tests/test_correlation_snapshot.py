"""Official correlation data admission, provenance and last-good behavior."""
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from macro_platform import us_equity_risk
from scripts.update_correlation_snapshot import parse_history, prepare_snapshot


NOW = datetime(2026, 10, 20, 7, 30, tzinfo=timezone.utc)


def csv_history(value="12.34", periods=220):
    dates = pd.bdate_range(end="2026-10-20", periods=periods)
    return "DATE,OPEN,HIGH,LOW,CLOSE\n" + "\n".join(
        f"{date:%m/%d/%Y},10,20,5,{value}" for date in dates)


class CorrelationAdmissionTests(unittest.TestCase):
    def test_only_completed_closes_and_original_points_are_admitted(self):
        records = parse_history(csv_history(), "COR1M", NOW)
        self.assertEqual(records[-1], {"observation_date": "2026-10-19", "close": 12.34})
        self.assertEqual(len(records), 219)
        after_close = datetime(2026, 10, 20, 21, tzinfo=timezone.utc)
        self.assertEqual(parse_history(csv_history(), "COR3M", after_close)[-1]["observation_date"],
                         "2026-10-20")

    def test_bad_columns_nonfinite_and_out_of_range_values_are_rejected(self):
        for text in ("DATE,OTHER\n10/19/2026,10", csv_history("inf"),
                     csv_history("NaN"), csv_history("101"), csv_history("-101"),
                     csv_history().replace("10/19/2026", "invalid")):
            with self.subTest(text=text[:60]), self.assertRaises(ValueError):
                parse_history(text, "COR1M", NOW)
        with self.assertRaises(ValueError):
            parse_history(csv_history(periods=20), "COR3M", NOW)

    def test_unchanged_or_older_export_cannot_refresh_or_erase_last_good(self):
        text = csv_history()
        prior = prepare_snapshot(text, "COR1M", {}, NOW)
        self.assertEqual(prior["source_url"],
                         "https://cdn.cboe.com/api/global/us_indices/daily_prices/COR1M_History.csv")
        self.assertIsNone(prepare_snapshot(text, "COR1M", prior, NOW))
        newer = dict(prior, coverage_end="2026-10-21")
        with self.assertRaises(ValueError):
            prepare_snapshot(text, "COR1M", newer, NOW)
        with self.assertRaises(ValueError):
            prepare_snapshot(csv_history(periods=210), "COR1M", prior, NOW)

    def test_disk_reader_rejects_wrong_symbol_bad_values_and_future_dates(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "data_snapshots"
            folder.mkdir()
            path = folder / "cor1m_daily.json"
            payload = {"symbol": "COR1M", "records": [
                {"observation_date": "2026-01-02", "close": 12.34},
                {"observation_date": "2026-01-03", "close": float("inf")},
                {"observation_date": "2026-01-04", "close": 101},
                {"observation_date": "2099-01-02", "close": 13},
            ]}
            path.write_text(json.dumps(payload))
            with patch.object(us_equity_risk, "ROOT", Path(temp)):
                result = us_equity_risk.load_correlation_snapshot("COR1M")
                self.assertEqual(result.COR1M.tolist(), [12.34])
                self.assertTrue(us_equity_risk.load_correlation_snapshot("COR3M").empty)
                payload["symbol"] = "COR3M"
                path.write_text(json.dumps(payload))
                self.assertTrue(us_equity_risk.load_correlation_snapshot("COR1M").empty)

    def test_bundled_snapshots_have_real_closes_and_consistent_coverage(self):
        for symbol in us_equity_risk.CORRELATION_SYMBOLS:
            path = us_equity_risk.ROOT / "data_snapshots" / f"{symbol.lower()}_daily.json"
            payload = json.loads(path.read_text())
            data = us_equity_risk.load_correlation_snapshot(symbol)
            self.assertGreater(len(data), 1000)
            self.assertEqual(payload["record_count"], len(data))
            self.assertEqual(payload["coverage_end"], data.observation_date.max().strftime("%Y-%m-%d"))
            self.assertEqual(payload["records"][-1]["close"], data[symbol].iloc[-1])


if __name__ == "__main__":
    unittest.main()
