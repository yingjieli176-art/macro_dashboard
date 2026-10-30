import unittest

import numpy as np
import pandas as pd

from macro_platform.yen_carry import (
    FX_NAME, PRESSURE_NAME, SPREAD_NAME, build_yen_carry_figure, carry_observations,
)


class YenCarryTests(unittest.TestCase):
    def setUp(self):
        self.days = pd.bdate_range("2026-06-01", periods=90)
        self.fx = pd.DataFrame({"observation_date": self.days, "usd_jpy_close": np.linspace(160, 140, 90)})
        self.us = pd.DataFrame({"observation_date": self.days, "DGS2": 4.0})
        self.jp = pd.DataFrame({"observation_date": self.days, "japan_2y": 0.75})

    def test_same_date_spread_does_not_fill_cross_market_holidays(self):
        us = self.us.drop(index=10)
        japan = self.jp.drop(index=11)
        rates, _ = carry_observations(us, japan, self.fx)
        self.assertAlmostEqual(rates.spread_pp.iloc[0], 3.25)
        self.assertTrue(rates.spread_pp.iloc[10:12].isna().all())
        fig = build_yen_carry_figure("1Y", us=us, japan=japan, fx=self.fx)
        self.assertFalse(fig.data[0].connectgaps)

    def test_exact_yen_repayment_cost_formula_and_lookback(self):
        _, fx = carry_observations(self.us, self.jp, self.fx)
        self.assertTrue(fx.yen_appreciation_pct.iloc[:20].isna().all())
        expected = (160 / self.fx.usd_jpy_close.iloc[20] - 1) * 100
        self.assertAlmostEqual(fx.yen_appreciation_pct.iloc[20], expected)
        fig = build_yen_carry_figure("1M", us=self.us, japan=self.jp, fx=self.fx)
        pressure = next(trace for trace in fig.data if trace.name == PRESSURE_NAME)
        first_day = pd.Timestamp(pressure.x[0])
        self.assertAlmostEqual(pressure.y[0], fx.loc[fx.observation_date.eq(first_day), "yen_appreciation_pct"].iloc[0])
        self.assertGreater(pressure.y[0], 0)

    def test_invalid_quotes_and_duplicate_dates_do_not_become_returns(self):
        self.fx.loc[30, "usd_jpy_close"] = np.inf
        self.fx.loc[31, "usd_jpy_close"] = -1
        self.fx = pd.concat([self.fx.iloc[::-1], self.fx.iloc[[40]].assign(usd_jpy_close=150)])
        _, fx = carry_observations(self.us, self.jp, self.fx)
        self.assertEqual(len(fx), 90)
        self.assertTrue(fx.loc[30:31, "yen_appreciation_pct"].isna().all())
        self.assertEqual(fx.usd_jpy_close.iloc[40], 150)
        self.assertAlmostEqual(fx.yen_appreciation_pct.iloc[32], (self.fx.loc[10, "usd_jpy_close"] / fx.usd_jpy_close.iloc[32] - 1) * 100)

    def test_depreciation_has_negative_pressure_and_missing_rates_keep_fx(self):
        self.fx["usd_jpy_close"] = np.linspace(140, 160, 90)
        fig = build_yen_carry_figure("5Y", us=pd.DataFrame(), japan=self.jp, fx=self.fx)
        self.assertEqual([t.name for t in fig.data], [FX_NAME, PRESSURE_NAME])
        self.assertIn(SPREAD_NAME, fig.layout.meta["missing_series"])
        self.assertLess(fig.data[-1].y[-1], 0)
        empty = build_yen_carry_figure("1Y", us=None, japan=None, fx=None)
        self.assertFalse(empty.data)
        self.assertEqual(len(empty.layout.meta["missing_series"]), 4)

    def test_three_distinct_axes_and_all_supported_windows(self):
        for window in ("5Y", "1Y", "6M", "3M", "1M"):
            fig = build_yen_carry_figure(window, us=self.us, japan=self.jp, fx=self.fx)
            self.assertEqual([t.name for t in fig.data], [SPREAD_NAME, FX_NAME, PRESSURE_NAME])
            self.assertEqual([t.yaxis for t in fig.data], ["y", "y2", "y3"])
            self.assertTrue(all(len(t.x) == len(t.y) for t in fig.data))


if __name__ == "__main__":
    unittest.main()
