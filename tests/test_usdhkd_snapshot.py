import unittest

import pandas as pd

from scripts.update_usdhkd_snapshot import _weekdays_only


class UsdHkdSnapshotTests(unittest.TestCase):
    def test_weekend_carry_labels_are_not_saved_as_trading_observations(self):
        frame = pd.DataFrame({
            "observation_date": pd.to_datetime([
                "2026-10-30", "2026-10-31", "2026-11-01"
            ]),
            "value": [7.8457, 7.8442, 7.8442],
        })
        result = _weekdays_only(frame)
        self.assertEqual(result.observation_date.dt.strftime("%Y-%m-%d").tolist(),
                         ["2026-10-30"])


if __name__ == "__main__":
    unittest.main()
