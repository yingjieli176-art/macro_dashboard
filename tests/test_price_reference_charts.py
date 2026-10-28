"""Original prices and annotations must stay separate from observations."""
import unittest

import pandas as pd

from macro_platform.equity_drawdown import build_price_figure
from macro_platform.china_equity import build_china_price_figure, SERIES as CHINA_SERIES
from macro_platform.echarts_axes import build_adaptive_echarts_option, build_safe_echarts_option, summarize_series_dates


def history(values):
    return pd.DataFrame({"observation_date": pd.to_datetime(["2010-01-04", "2026-09-25", "2026-10-26"]),
                         "close": values})


class PriceReferenceTests(unittest.TestCase):
    def test_prices_are_unchanged_and_distinct_units_have_separate_axes(self):
        figure = build_price_figure({"SPX": history([9999, 8000, 7600]),
                                    "RSP": history([999, 230, 220])}, split_axes=True)
        self.assertEqual(list(figure.data[0].y), [8000, 7600])
        self.assertEqual(list(figure.data[1].y), [230, 220])
        self.assertEqual([trace.yaxis for trace in figure.data], ["y", "y2"])
        self.assertEqual(len(figure.layout.shapes), 4)
        self.assertEqual([row["peak"] for row in figure.layout.meta["price_summary"]], [8000, 230])

    def test_native_and_recovery_guides_survive_every_range_without_fake_points(self):
        figure = build_price_figure({"SPX": history([9999, 8000, 7600]),
                                    "RSP": history([999, 230, 220])}, split_axes=True)
        for build in (build_adaptive_echarts_option, build_safe_echarts_option):
            for period in ("5Y", "1Y", "6M", "3M", "1M"):
                option = build(figure, period)
                self.assertEqual(len(option["series"]), 2)
                self.assertEqual([series["yAxisIndex"] for series in option["series"]], [0, 1])
                self.assertEqual([line["yAxis"] for line in option["series"][0]["markLine"]["data"]], [7600 if period == "1M" else 8000, 7600])
                self.assertEqual([line["yAxis"] for line in option["series"][1]["markLine"]["data"]], [220 if period == "1M" else 230, 220])
                self.assertEqual([len(series["data"]) for series in option["series"]], [2, 2])
                self.assertTrue(all(line["label"]["show"] for series in option["series"]
                                    for line in series["markLine"]["data"]))
        dates = summarize_series_dates(figure, now=pd.Timestamp("2026-10-27"))
        self.assertEqual(len(dates["latest_by_name"]), 2)
        self.assertEqual(set(dates["latest_by_name"].values()), {"2026-10-26"})

    def test_new_high_updates_both_lines_and_missing_index_stays_missing(self):
        figure = build_price_figure({"SPX": history([100, 110, 120])})
        refs = figure.layout.meta["price_reference_lines"]
        self.assertEqual([row["value"] for row in refs], [120, 120])
        self.assertEqual(figure.layout.meta["missing_series"], ["RSP（标普500等权ETF）"])

    def test_china_prices_share_one_points_axis_with_six_independent_guides(self):
        histories = {code: history([15000 + i, 6000 + i, 6500 + i]) for i, code in enumerate(CHINA_SERIES)}
        figure = build_china_price_figure(histories)
        self.assertEqual([trace.y[-1] for trace in figure.data], [6500, 6501, 6502])
        option = build_adaptive_echarts_option(figure)
        self.assertEqual(len(option["yAxis"]), 1)
        self.assertEqual(sum(len(series["markLine"]["data"]) for series in option["series"]), 6)
        self.assertEqual([row["peak_date"] for row in figure.layout.meta["price_summary"]], ["2026-10-26"] * 3)


if __name__ == "__main__":
    unittest.main()
