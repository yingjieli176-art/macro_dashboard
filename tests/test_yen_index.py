import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from macro_platform.yen_index import load_yen_index, parse_bis_yen_csv
from scripts.update_yen_index import save_snapshot


CSV = """FREQ,EER_TYPE,EER_BASKET,REF_AREA,TIME_PERIOD,OBS_VALUE,UNIT_MEASURE
D,N,B,JP,2026-10-09,69.11,882
D,N,B,JP,2026-10-10,NaN,882
D,N,B,JP,2026-10-12,68.98,882
D,N,B,JP,2026-10-13,69.21,882
D,N,B,JP,2026-10-22,70,882
"""


class YenSourceTests(unittest.TestCase):
    def test_original_values_and_dates_no_weekend_or_future_observations(self):
        frame = parse_bis_yen_csv(CSV, today="2026-10-21")
        self.assertEqual(frame.observation_date.dt.strftime("%Y-%m-%d").tolist(),
                         ["2026-10-09", "2026-10-12", "2026-10-13"])
        self.assertEqual(frame.jpy_neer.tolist(), [69.11, 68.98, 69.21])

    def test_wrong_series_base_or_invalid_values_are_rejected(self):
        for old, new in (("D,N,B,JP", "M,N,B,JP"), ("D,N,B,JP", "D,R,B,JP"),
                         ("D,N,B,JP", "D,N,N,JP"), ("D,N,B,JP", "D,N,B,US"),
                         (",882", ",628"), ("69.11", "inf"), ("69.11", "-1")):
            with self.subTest(new=new), self.assertRaises(ValueError):
                parse_bis_yen_csv(CSV.replace(old, new), today="2026-10-21")

    def test_updater_preserves_last_good_file_on_truncation_or_regression(self):
        dates = pd.bdate_range("2021-01-01", periods=1400)
        frame = pd.DataFrame({"observation_date": dates, "jpy_neer": 90.12})
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "yen.json"
            self.assertTrue(save_snapshot(frame, path))
            original = path.read_bytes()
            self.assertFalse(save_snapshot(frame, path))
            for bad in (frame.iloc[:100], frame.iloc[:-1], frame.drop(index=500)):
                with self.assertRaises(ValueError):
                    save_snapshot(bad, path)
                self.assertEqual(path.read_bytes(), original)

    def test_committed_official_snapshot_reads_without_network(self):
        with patch("requests.get", side_effect=AssertionError("No render-time request")):
            load_yen_index.clear()
            frame = load_yen_index()
        self.assertGreater(len(frame), 1200)
        self.assertTrue(frame.jpy_neer.gt(0).all())
        self.assertTrue(frame.observation_date.is_unique)
        self.assertIn("D.N.B.JP", frame.attrs["source"])
