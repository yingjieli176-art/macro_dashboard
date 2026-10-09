"""Check financial-series truthfulness, viewport density and Y-axis readability."""
import unittest
from unittest.mock import patch

import pandas as pd
import plotly.graph_objects as go

from macro_platform.echarts_axes import (
    build_adaptive_echarts_option,
    option_observation_health,
)
from macro_platform.hk_liquidity import (
    _market_snapshot_history,
    load_hk_liquidity,
    load_hk_funding_monthly,
    load_hk_funding_daily,
    build_hk_liquidity_figures,
)
from macro_platform.asia_rates import build_asia_rates_figure, load_china_gov_yields


class FinancialChartIntegrity(unittest.TestCase):
    def test_monthly_hk_series_use_actual_month_end(self):
        core = load_hk_liquidity()
        self.assertFalse(core.empty)
        self.assertTrue(core["observation_date"].dt.is_month_end.all())
        funding = load_hk_funding_monthly()
        self.assertFalse(funding.empty)
        self.assertTrue(funding["observation_date"].dt.is_month_end.all())

    def test_hk_five_year_market_preserves_last_month_daily_points(self):
        frame = _market_snapshot_history("0700.HK", "Tencent", "5Y")
        self.assertFalse(frame.empty)
        last = frame["observation_date"].max()
        recent = frame.loc[frame["observation_date"] >= last - pd.DateOffset(months=1)]
        # A week-sampled figure has <= 6 points in 1M; a genuine daily
        # window must have many more than that.
        self.assertGreaterEqual(len(recent), 12)
        self.assertTrue(frame["observation_date"].is_unique)
        self.assertTrue(frame["observation_date"].is_monotonic_increasing)

    def test_five_year_hk_funding_includes_recent_daily_rate_observations(self):
        figures = build_hk_liquidity_figures("5Y")
        self.assertEqual(len(figures), 4)
        funding = figures[2]
        overnight = next(trace for trace in funding.data if trace.name == "O/N HIBOR")
        dates = pd.to_datetime(overnight.x)
        nonnull = pd.DataFrame({"date": dates, "value": overnight.y}).dropna()
        latest = nonnull["date"].max()
        observations = nonnull.loc[nonnull["date"] >= latest - pd.DateOffset(months=1)]
        self.assertGreaterEqual(len(observations), 10)
        # The five-year source contains both genuine daily and monthly history.
        self.assertTrue(load_hk_funding_daily()["observation_date"].notna().any())

    def test_echarts_axes_show_clear_units_without_fixing_y(self):
        dates = pd.date_range("2026-09-01", periods=21)
        fig = go.Figure([
            go.Scatter(x=dates, y=[3.5 + i * 0.02 for i in range(21)],
                       name="Fed rate", hovertemplate="Fed: %{y:.3f}%<extra></extra>"),
            go.Scatter(x=dates, y=[0.05 + i * 0.002 for i in range(21)],
                       yaxis="y2", name="Spread",
                       hovertemplate="Spread: %{y:.3f} pp<extra></extra>"),
        ])
        fig.update_layout(yaxis=dict(title="Rate (%)"),
                          yaxis2=dict(overlaying="y", side="right", title=""))
        option = build_adaptive_echarts_option(fig, "1M")
        self.assertEqual(option["yAxis"][0]["name"], "Rate (%)")
        self.assertEqual(option["yAxis"][1]["name"], "R1 · pp")
        self.assertTrue(all(axis["scale"] for axis in option["yAxis"]))
        self.assertTrue(all(axis["axisLabel"]["hideOverlap"] for axis in option["yAxis"]))
        self.assertTrue(all("min" not in axis and "max" not in axis
                            for axis in option["yAxis"]))
        self.assertEqual(option["xAxis"]["splitNumber"], 6)

    def test_stale_vixeq_is_flagged_but_monthly_release_is_not(self):
        options = {"series": [
            {"name": "VIXEQ", "data": [["2026-09-10", 36.37]]},
            {"name": "VIX", "data": [["2026-10-08", 16.3]]},
        ]}
        health = option_observation_health(
            options, chart_key="us_equity_risk", now="2026-10-09"
        )
        self.assertEqual(health["stale_names"], ["VIXEQ"])
        self.assertEqual(health["latest_by_name"]["VIXEQ"], "2026-09-10")
        monthly = option_observation_health(
            {"series": [{"name": "M2 YoY", "data": [["2026-08-31", 5.2]]}]},
            chart_key="hk_5_range", now="2026-10-09"
        )
        self.assertFalse(monthly["stale_names"])

    def test_asia_curve_spread_has_its_own_percentage_point_axis(self):
        china = pd.DataFrame({
            "observation_date": pd.to_datetime(["2026-09-29", "2026-09-30"]),
            "china_2y": [1.4, 1.5],
            "china_10y": [2.0, 2.1],
            "china_10y_2y_pct": [0.6, 0.6],
        })
        japan = pd.DataFrame({
            "observation_date": pd.to_datetime(["2026-09-29", "2026-09-30"]),
            "japan_2y": [1.0, 1.1],
            "japan_10y": [2.0, 2.2],
            "japan_10y_2y_pct": [1.0, 1.1],
        })
        with patch("macro_platform.asia_rates.load_china_gov_yields", return_value=china), \\
             patch("macro_platform.asia_rates.load_japan_gov_yields", return_value=japan):
            fig = build_asia_rates_figure("1M")
        spread = [trace for trace in fig.data if "10Y−2Y" in trace.name]
        self.assertEqual(len(spread), 2)
        self.assertTrue(all(trace.yaxis == "y2" for trace in spread))
        self.assertIn("pp", fig.layout.yaxis2.title.text)

    def test_eastmoney_yield_spread_matches_displayed_components(self):
        class Response:
            def raise_for_status(self):
                return None
            def json(self):
                return {"result": {"data": [
                    {"SOLAR_DATE": "2026-10-07",
                     "EMM00588704": "1.50", "EMM00166466": "2.10",
                     "EMM01276014": "0.90"}
                ], "pages": 1}}
        # The source spread intentionally disagrees; the chart should use
        # 2.10-1.50=0.60 rather than 0.90.
        with patch("macro_platform.asia_rates.requests.get", return_value=Response()):
            data = load_china_gov_yields.__wrapped__() if hasattr(
                load_china_gov_yields, "__wrapped__"
            ) else load_china_gov_yields()
        self.assertAlmostEqual(float(data.iloc[-1]["china_10y_2y_pct"]), 0.6)


if __name__ == "__main__":
    unittest.main()
