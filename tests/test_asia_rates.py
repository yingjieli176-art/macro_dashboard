import unittest

import pandas as pd
import plotly.graph_objects as go

from macro_platform.asia_rates import _add_trace, build_asia_rates_figure


class AsiaRatesTraceTests(unittest.TestCase):
    def test_null_calendar_rows_do_not_break_line(self):
        frame = pd.DataFrame(
            {
                "observation_date": pd.to_datetime(
                    ["2026-01-02", "2026-01-05", "2026-01-06"]
                ),
                "china_2y": [1.40, float("nan"), 1.42],
            }
        )
        fig = go.Figure()

        _add_trace(
            fig,
            frame,
            "china_2y",
            "China 2Y",
            width=2.1,
        )

        self.assertEqual(len(fig.data), 1)
        trace = fig.data[0]
        self.assertEqual(
            list(pd.to_datetime(trace.x)),
            list(pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06"])),
        )
        values = list(trace.y)
        self.assertEqual(values[0], 1.40)
        self.assertTrue(pd.isna(values[1]))
        self.assertEqual(values[2], 1.42)
        self.assertTrue(trace.connectgaps)


    def test_final_figure_contains_all_six_rate_series(self):
        import macro_platform.asia_rates as asia_rates

        china = pd.DataFrame(
            {
                "observation_date": pd.to_datetime(["2026-01-02", "2026-01-05"]),
                "china_2y": [1.40, 1.41],
                "china_10y": [1.85, 1.86],
                "china_10y_2y_pct": [0.45, 0.45],
            }
        )
        japan = pd.DataFrame(
            {
                "observation_date": pd.to_datetime(["2026-01-02", "2026-01-05"]),
                "japan_2y": [1.05, 1.06],
                "japan_10y": [1.95, 1.97],
                "japan_10y_2y_pct": [999.0, 999.0],
            }
        )

        old_china = asia_rates.load_china_gov_yields
        old_japan = asia_rates.load_japan_gov_yields
        try:
            asia_rates.load_china_gov_yields = lambda: china.copy()
            asia_rates.load_japan_gov_yields = lambda: japan.copy()
            fig = build_asia_rates_figure("1Y")
        finally:
            asia_rates.load_china_gov_yields = old_china
            asia_rates.load_japan_gov_yields = old_japan

        names = [trace.name for trace in fig.data]
        self.assertEqual(
            names,
            [
                "China 2Y",
                "China 10Y",
                "China 10Y−2Y",
                "Japan 2Y",
                "Japan 10Y",
                "Japan 10Y−2Y",
            ],
        )
        japan_spread = fig.data[-1]
        self.assertEqual(list(japan_spread.y), [0.90, 0.91])


if __name__ == "__main__":
    unittest.main()
