"""Recent net-liquidity observations must never include 2022-era stale TGA."""
import ast
from pathlib import Path
import unittest

import pandas as pd
import plotly.graph_objects as go
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]


def load_us_liquidity_builder(sources):
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "build_fig4")
    ns = {"pd": pd, "go": go, "chart_height": lambda *a: 420,
          "apply_chart_style": lambda fig, *a: fig,
          "filter_range": lambda frame, period: frame,
          "_mark_missing_series": Mock()}
    for key, frame in sources.items():
        ns[key] = lambda frame=frame: frame.copy()
    def add_line(fig, frame, column, name, *args, **kwargs):
        if column not in frame:
            return
        valid = frame.dropna(subset=[column])
        if not valid.empty:
            fig.add_trace(go.Scatter(x=valid["observation_date"], y=valid[column],
                                    name=name))
    ns["add_line"] = add_line
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "app.py", "exec"), ns)
    return ns["build_fig4"], ns["_mark_missing_series"]


class TgaFreshnessRegression(unittest.TestCase):
    def _make(self, code, dates, values):
        frame = pd.DataFrame({"observation_date": pd.to_datetime(dates), code: values})
        return frame

    def test_2022_tga_cannot_produce_2026_net_liquidity(self):
        sources = {
            "get_walcl": self._make("WALCL",
                ["2026-09-30", "2026-10-07"], [6_650_000, 6_680_000]),
            "get_wresbal": self._make("WRESBAL",
                ["2026-09-30", "2026-10-07"], [3_100_000, 3_120_000]),
            "get_tga_daily": self._make("TGA_DAILY", ["2022-04-15"], [0.65]),
            "get_rrp_daily": self._make("RRPONTSYD",
                ["2026-10-01", "2026-10-07"], [7000, 6500]),
        }
        builder, missing = load_us_liquidity_builder(sources)
        fig = builder("5Y")
        net = [trace for trace in fig.data if trace.name == "Net Liquidity"]
        self.assertFalse(net, "2026 Net Liquidity must be absent with 2022 TGA")
        self.assertTrue(any("Net Liquidity" in str(call) for call in missing.call_args_list))
        self.assertIn("Reserve Balances (R1)", [trace.name for trace in fig.data])

    def test_recent_tga_is_allowed_only_within_short_known_age(self):
        sources = {
            "get_walcl": self._make("WALCL", ["2026-10-01", "2026-10-08"],
                                     [6_650_000, 6_680_000]),
            "get_wresbal": self._make("WRESBAL", ["2026-10-01"], [3_100_000]),
            "get_tga_daily": self._make("TGA_DAILY", ["2026-10-03"], [0.6]),
            "get_rrp_daily": self._make("RRPONTSYD", ["2026-10-04", "2026-10-08"],
                                       [5.0, 4.0]),
        }
        builder, _ = load_us_liquidity_builder(sources)
        fig = builder("1M")
        net = next(t for t in fig.data if t.name == "Net Liquidity")
        self.assertEqual(len(net.y), 2)
        self.assertAlmostEqual(float(net.y[-1]), 6.68 - 0.6 - 0.004)

    def test_treasury_request_prioritizes_latest_dates_to_avoid_truncated_2022_page(self):
        code = (ROOT / "data.py").read_text(encoding="utf-8")
        tree = ast.parse(code)
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                  and n.name == "get_tga_daily")
        src = ast.get_source_segment(code, fn)
        self.assertIn('"sort": "-record_date"', src)
        self.assertIn('"fields": "record_date,account_type,close_today_bal,open_today_bal"', src)


if __name__ == "__main__":
    unittest.main()
