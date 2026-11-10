import unittest
from unittest.mock import patch

import pandas as pd

from macro_platform.japan_short_rates import auction_result_urls, clean_observations, parse_auction_result
from macro_platform.yen_carry import build_yen_carry_figure, JPY_3M_NAME, JPY_10Y_NAME, JPY_CURVE_NAME
from macro_platform.echarts_axes import build_adaptive_echarts_option, build_safe_echarts_option
from scripts.update_japan_3m import read_archive


class JapanShortRateTests(unittest.TestCase):
    def test_calendar_selects_three_month_results_and_average_not_high_yield(self):
        url = "https://www.mof.go.jp/jgbs/auction/calendar/tbill/tbill_nyusatsu/resul20261106.htm"
        calendar = f'<table><tr><td>国庫短期証券（3ヶ月）</td><td><a href="{url}">結果</a></td></tr>'
        calendar += f'<tr><td>国庫短期証券（6ヶ月）</td><td><a href="{url.replace("1106", "1109")}">結果</a></td></tr></table>'
        self.assertEqual(auction_result_urls(calendar), [url])
        result = '<table><tr><td>募入最高利回り</td><td>1.2481％</td></tr><tr><td>募入平均利回り</td><td>（1.2410％）</td></tr></table>'
        self.assertEqual(parse_auction_result(result, url), {"observation_date": "2026-11-06", "japan_3m": 1.241})

    def test_archive_excludes_six_and_twelve_month_bills(self):
        raw = pd.DataFrame([[None]*9 for _ in range(9)])
        raw.iloc[2, 1], raw.iloc[3, 8] = "入札日", "平均利回"
        for row, maturity, value in ((6, "2026-09-14", -.1), (7, "2026-12-14", 2.), (8, "2027-06-14", 3.)):
            raw.iloc[row, 1:4] = [pd.Timestamp("2026-06-12"), pd.Timestamp("2026-06-15"), pd.Timestamp(maturity)]
            raw.iloc[row, 8] = value
        with patch("scripts.update_japan_3m.pd.ExcelFile") as book, patch("scripts.update_japan_3m.pd.read_excel", return_value=raw):
            book.return_value.sheet_names = ["令和８年度"]
            frame = read_archive(b"", pd.Timestamp("2021-01-01"))
        self.assertEqual(frame.japan_3m.tolist(), [-.1])

    def test_invalid_and_future_observations_are_rejected(self):
        frame = clean_observations(pd.DataFrame({"observation_date": ["2026-06-01", "2026-06-02", "2099-01-01"],
                                                "japan_3m": [-.1, float("inf"), 1.]}))
        self.assertEqual(frame.japan_3m.tolist(), [-.1])

    def test_same_day_curve_and_renderers_in_all_windows(self):
        days = pd.bdate_range("2021-01-01", "2026-10-30")
        short = pd.DataFrame({"observation_date": days[::5], "japan_3m": .5})
        long = pd.DataFrame({"observation_date": days, "japan_10y": 2.})
        missing_day = short.observation_date.iloc[-2]
        long = long.loc[long.observation_date.ne(missing_day)]
        for window in ("5Y", "1Y", "6M", "3M", "1M"):
            fig = build_yen_carry_figure(window, us=None, japan=long, fx=None, japan_short=short)
            traces = {t.name: t for t in fig.data}
            self.assertEqual(set(traces), {JPY_3M_NAME, JPY_10Y_NAME, JPY_CURVE_NAME})
            curve = traces[JPY_CURVE_NAME]
            self.assertEqual(curve.y[-1], 1.5)
            self.assertTrue(pd.isna(curve.y[list(curve.x).index(missing_day)]))
            self.assertFalse(curve.connectgaps)
            for adapter in (build_adaptive_echarts_option, build_safe_echarts_option):
                option = adapter(fig, window)
                self.assertEqual({s["name"] for s in option["series"]}, set(traces))
                self.assertTrue(all(s["yAxisIndex"] == 0 for s in option["series"]))
                self.assertIn("pp", option["yAxis"][0]["name"])

    def test_short_feed_outage_keeps_long_yield(self):
        long = pd.DataFrame({"observation_date": pd.to_datetime(["2026-10-30"]), "japan_10y": [2.]})
        fig = build_yen_carry_figure("1Y", us=None, japan=long, fx=None, japan_short=pd.DataFrame())
        self.assertEqual([t.name for t in fig.data], [JPY_10Y_NAME])
        self.assertIn(JPY_3M_NAME, fig.layout.meta["missing_series"])
        self.assertIn(JPY_CURVE_NAME, fig.layout.meta["missing_series"])
