"""Regression tests for verified Hong Kong chart data and US source freshness."""
import unittest
from unittest.mock import patch
import pandas as pd
from macro_platform import hk_liquidity as hk

class RealHkChartSmoke(unittest.TestCase):
    def test_hk_snapshot_retains_banking_and_funding_observations(self):
        base = hk.load_hk_liquidity()
        self.assertFalse(base.empty)
        banking = hk.load_hk_banking_liquidity_monthly()
        funding = hk.load_hk_funding_monthly()
        daily = hk.load_hk_funding_daily()
        self.assertGreater(banking["Closing Aggregate Balance"].notna().sum(), 12)
        self.assertGreater(banking["Outstanding EFBN"].notna().sum(), 12)
        self.assertGreater(funding["HIBOR O/N"].notna().sum(), 12)
        self.assertGreater(funding["HIBOR 3M"].notna().sum(), 12)
        self.assertGreater(daily["HIBOR O/N"].notna().sum(), 12)

    def test_independent_recovery_from_real_hkma_snapshots(self):
        banking, funding = hk.build_hk_core_snapshot_figures("5Y")
        for number, fig in ((6, banking), (7, funding)):
            finite = [trace for trace in fig.data if
                      pd.to_numeric(pd.Series(trace.y), errors="coerce").notna().sum() > 12]
            self.assertTrue(finite, f"Chart {number} snapshot recovery failed")
            self.assertTrue(all(pd.notna(pd.to_datetime(t.x)).all() for t in finite))

    def test_full_hk_builder_has_nonempty_figures_6_and_7(self):
        with patch.object(hk, "_market_history", return_value=pd.DataFrame(
                columns=["observation_date"])), patch.object(
                hk, "_fred_daily_series", return_value=pd.DataFrame(
                columns=["observation_date", "USD/HKD"])):
            all_figs = hk.build_hk_liquidity_figures("5Y", market_mode="Raw")
        self.assertEqual(len(all_figs), 4)
        for number in (1, 2):
            fig = all_figs[number]
            good = [trace for trace in fig.data
                    if getattr(trace, "y", None) is not None and
                    pd.to_numeric(pd.Series(trace.y), errors="coerce").notna().sum() > 3]
            self.assertTrue(good, f"HK chart {number+5} has no real curves")


if __name__ == "__main__":
    unittest.main()
