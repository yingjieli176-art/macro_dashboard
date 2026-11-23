"""Regression coverage for four distinct implied-volatility sources."""
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from macro_platform import cross_asset_volatility as cross
from macro_platform.echarts_axes import build_adaptive_echarts_option


class CrossAssetVolatilityTests(unittest.TestCase):
    def test_three_sources_get_independent_axes_and_correct_units(self):
        days = ["2026-10-12", "2026-10-13", "2026-10-14"]
        ovx = pd.DataFrame({"observation_date":days, "OVXCLS":[42., 41., 45.]})
        move = pd.DataFrame({"observation_date":days, "MOVE":[75., 76., 79.]})
        rows = [{"observation_date":"2026-10-14",
                 "observation_timestamp":"2026-10-14T12:30:00+00:00", "value":7.5}]
        yen = [{"observation_date":"2026-10-14",
                "observation_timestamp":"2026-10-14T12:30:00+00:00", "value":9.25}]
        figure = cross.build_figure("5Y", ovx=ovx, move=move,
                                    eurusd_records=rows, usdjpy_records=yen)
        assert [trace.yaxis or "y" for trace in figure.data] == ["y", "y2", "y3", "y4"]
        assert float(figure.data[2].y[0]) == 7.5
        assert float(figure.data[3].y[0]) == 9.25
        option = build_adaptive_echarts_option(figure, "1M")
        assert [line["yAxisIndex"] for line in option["series"]] == [0,1,2,3]
        assert len(option["yAxis"]) == 4
        assert all(axis["scale"] for axis in option["yAxis"])
        assert not figure.layout.meta["missing_series"]

    def test_unavailable_eurusd_not_faked_from_spot_or_evz(self):
        days = ["2026-10-12", "2026-10-13"]
        ovx = pd.DataFrame({"observation_date":days, "OVXCLS":[42., 41.]})
        move = pd.DataFrame({"observation_date":days, "MOVE":[75., 76.]})
        figure = cross.build_figure("5Y", ovx=ovx, move=move,
                                    eurusd_records=[], usdjpy_records=[])
        assert len(figure.data) == 2
        assert any("EUR/USD" in value for value in figure.layout.meta["missing_series"])
        assert any("USD/JPY" in value for value in figure.layout.meta["missing_series"])

    def test_real_saxo_1m_quote_is_not_spot_3m_or_risk_reversal(self):
        report = """<html><div class="blogTitle">20 Nov 2026, 1230 GMT</div>
        <div class="mainTitle">ATM VOLATILITIES</div>
        <div class="volSection"><table>
          <tr><th>Pair</th><th>Spot</th><th>1m</th><th>3m</th></tr>
          <tr><td>EURUSD</td><td>1.0967 (-0.17%)</td>
              <td>6.17 (+0.17)</td><td>6.19 (+0.1)</td></tr>
          <tr><td>USDJPY</td><td>158.90</td><td>8.30 (+0.1)</td><td>8.60 (+0.2)</td></tr>
        </table><span>Change from 2026-11-19 12:30 to 2026-11-20 12:30 UTC</span></div></html>"""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "saxo.json"
            records = cross.accept_saxo_report(report, path, now="2026-11-23T00:00Z")
            assert len(records) == 1
            assert records[0]["observation_date"] == "2026-11-20"
            assert records[0]["value"] == 6.17
            assert cross.load_eurusd_snapshot(path)[0]["value"] == 6.17

    def test_usdjpy_saxo_one_month_quote_is_independent_of_three_month(self):
        report = """<html><div class="blogTitle">20 Nov 2026, 1230 GMT</div>
        <div class="mainTitle">ATM VOLATILITIES</div>
        <div class="volSection"><table>
          <tr><th>Pair</th><th>Spot</th><th>1m</th><th>3m</th></tr>
          <tr><td>EURUSD</td><td>1.0967</td><td>6.17 (+0.17)</td><td>6.19 (+0.1)</td></tr>
          <tr><td>USDJPY</td><td>158.90</td><td>8.30 (+0.1)</td><td>8.60 (+0.2)</td></tr>
        </table><span>Change from 2026-11-19 12:30 to 2026-11-20 12:30 UTC</span></div></html>"""
        with tempfile.TemporaryDirectory() as folder:
            yen_path = Path(folder) / "usdjpy.json"
            euro_path = Path(folder) / "eurusd.json"
            yen = cross.accept_usdjpy_report(report, yen_path, now="2026-11-23T00:00Z")
            euro = cross.accept_saxo_report(report, euro_path, now="2026-11-23T00:00Z")
            assert yen[0]["value"] == 8.30
            assert euro[0]["value"] == 6.17
            assert cross.load_usdjpy_snapshot(yen_path)[0]["value"] == 8.30
            assert cross.load_eurusd_snapshot(euro_path)[0]["value"] == 6.17
            assert cross.load_usdjpy_snapshot(euro_path) == []
            assert cross.load_eurusd_snapshot(yen_path) == []

    def test_invalid_snapshot_identity_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "eurusd.json"
            path.write_text('{"symbol":"EVZ","records":[]}', encoding="utf-8")
            assert cross.load_eurusd_snapshot(path) == []

    def test_realized_20_sessions_and_annualization(self):
        dates = pd.bdate_range("2026-09-01", periods=26)
        # Daily 10Y yield changes alternate +1bp/-1bp.
        yields = [4.0]
        for index in range(1, 26):
            yields.append(yields[-1] + (0.01 if index % 2 else -0.01))
        frame = pd.DataFrame({"observation_date":dates, "DGS10":yields})
        result = cross.twenty_day_realized_volatility(
            frame, "DGS10", yield_basis_points=True)
        assert len(result) == 6  # 21 first observations make 20 returns
        import math
        expected = math.sqrt(20/19) * math.sqrt(252)
        assert abs(result.rv20.iloc[0]-expected) < 1e-10

        # Oil annualization is on log returns rather than raw price deltas.
        from numpy import exp
        log_changes = [0.01 if i % 2 else -0.01 for i in range(1,26)]
        prices = [80.0]
        for change in log_changes:
            prices.append(prices[-1] * exp(change))
        oil = pd.DataFrame({"observation_date":dates, "DCOILWTICO":prices})
        oil_result = cross.twenty_day_realized_volatility(oil, "DCOILWTICO")
        assert len(oil_result) == 6
        assert abs(oil_result.rv20.iloc[0] - expected) < 1e-9

    def test_invalid_oil_price_breaks_return_window_without_filling(self):
        dates = pd.bdate_range("2026-09-01", periods=42)
        values = [80.0+i*.1 for i in range(42)]
        values[20] = -37.0
        frame = pd.DataFrame({"observation_date":dates, "DCOILWTICO":values})
        result = cross.twenty_day_realized_volatility(frame, "DCOILWTICO")
        # The outlier must invalidate both crossing returns and the 20D window.
        assert not result.observation_date.isin([dates[20], dates[21]]).any()
        assert result.observation_date.max() == dates[-1]

    def test_new_realized_vol_traces_share_commodity_percent_axis(self):
        dates = pd.bdate_range("2026-09-01", periods=30)
        bases = {"DGS10":[4.0+i*.01 for i in range(30)],
                 "DCOILBRENTEU":[70.0+(i%4)*2+i*.2 for i in range(30)],
                 "DCOILWTICO":[65.0+(i%5)*2+i*.3 for i in range(30)]}
        treasury = pd.DataFrame({"observation_date":dates, "DGS10":bases["DGS10"]})
        brent = pd.DataFrame({"observation_date":dates, "DCOILBRENTEU":bases["DCOILBRENTEU"]})
        wti = pd.DataFrame({"observation_date":dates, "DCOILWTICO":bases["DCOILWTICO"]})
        ovx = pd.DataFrame({"observation_date":dates, "OVXCLS":[35.0]*30})
        move = pd.DataFrame({"observation_date":dates, "MOVE":[90.0]*30})
        figure = cross.build_figure(
            "5Y", ovx=ovx, move=move, treasury10y=treasury, brent=brent,
            wti=wti, eurusd_records=[], usdjpy_records=[])
        names = [item.name for item in figure.data]
        assert any("US10Y 20D" in name for name in names)
        assert any("Brent 20D" in name for name in names)
        assert any("WTI 20D" in name for name in names)
        assert [item.yaxis for item in figure.data[-3:]] == ["y5","y6","y6"]
        option = build_adaptive_echarts_option(figure, "1M")
        assert len(option["yAxis"]) == 6
        assert [item["yAxisIndex"] for item in option["series"][-3:]] == [4,5,5]
        assert all(axis["scale"] for axis in option["yAxis"])

    def test_source_daily_series_not_forward_filled(self):
        ovx = pd.DataFrame({"observation_date":["2026-10-12","2026-10-14"],
                            "OVXCLS":[42.,45.]})
        move = pd.DataFrame({"observation_date":["2026-10-13","2026-10-14"],
                             "MOVE":[75.,79.]})
        figure = cross.build_figure("1M", ovx=ovx, move=move, eurusd_records=[])
        assert len(figure.data[0].x) == 2
        assert len(figure.data[1].x) == 2


if __name__ == "__main__":
    unittest.main()
