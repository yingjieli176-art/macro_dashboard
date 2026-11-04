"""CDS curves must use actual, source-identified tenor spreads."""
import unittest
from unittest.mock import patch
import pandas as pd

from macro_platform import nvidia_cds


class NvidiaCdsTests(unittest.TestCase):
    def row(self):
        return dict(issuer="NVIDIA Corporation", currency="USD", seniority="SENIOR_UNSECURED",
                    observation_date="2026-10-01", tenor="1Y", quote_type="par_spread", spread_bps=35.,
                    source="Authorized test fixture", source_url="https://example.com/fixture")

    def test_rejects_prices_coupons_wrong_contracts_and_invalid_observations(self):
        self.assertEqual(nvidia_cds.validate_quote(self.row())["spread_bps"], 35.)
        for key, bad in (("quote_type", "settlement_price"), ("quote_type", "coupon"),
                         ("tenor", "3Y"), ("issuer", "Other Corp"), ("currency", "EUR"),
                         ("seniority", "SUBORDINATED"), ("spread_bps", float("nan")),
                         ("spread_bps", -1), ("observation_date", "2099-01-01"), ("source_url", "")):
            with self.subTest(key=key, bad=bad), self.assertRaises(ValueError):
                nvidia_cds.validate_quote({**self.row(), key: bad})

    def test_missing_data_does_not_create_estimated_tenors(self):
        empty = pd.DataFrame(columns=["observation_date", "tenor", "spread_bps"])
        with patch.object(nvidia_cds, "load_nvidia_cds", return_value=empty):
            fig = nvidia_cds.build_nvidia_cds_figure()
        self.assertEqual(len(fig.data), 0)
        self.assertEqual(fig.layout.meta["missing_series"], ["NVIDIA CDS 1Y", "NVIDIA CDS 5Y"])

    def test_unequal_tenor_calendars_remain_actual_observations(self):
        rows = [self.row(), {**self.row(), "tenor": "5Y", "observation_date": "2026-10-02", "spread_bps": 60.}]
        data = pd.DataFrame(rows); data["observation_date"] = pd.to_datetime(data.observation_date)
        with patch.object(nvidia_cds, "load_nvidia_cds", return_value=data):
            fig = nvidia_cds.build_nvidia_cds_figure()
        self.assertEqual([list(t.y) for t in fig.data], [[35.], [60.]])
        self.assertEqual([list(t.x)[0] for t in fig.data], [pd.Timestamp("2026-10-01"), pd.Timestamp("2026-10-02")])
        self.assertTrue(all(t.connectgaps is False for t in fig.data))


if __name__ == "__main__": unittest.main()
