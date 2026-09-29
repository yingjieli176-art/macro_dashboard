import unittest

import pandas as pd
import plotly.graph_objects as go

from macro_platform.asia_rates import _add_trace


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
            list(pd.to_datetime(["2026-01-02", "2026-01-06"])),
        )
        self.assertEqual(list(trace.y), [1.40, 1.42])
        self.assertFalse(trace.connectgaps)


if __name__ == "__main__":
    unittest.main()
