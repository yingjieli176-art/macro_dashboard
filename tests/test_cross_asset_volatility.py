"""Regression coverage for three distinct implied-volatility sources."""
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
        figure = cross.build_figure("5Y", ovx=ovx, move=move, eurusd_records=rows)
        assert [trace.yaxis or "y" for trace in figure.data] == ["y", "y2", "y3"]
        assert float(figure.data[2].y[0]) == 7.5
        option = build_adaptive_echarts_option(figure, "1M")
        assert [line["yAxisIndex"] for line in option["series"]] == [0,1,2]
        assert len(option["yAxis"]) == 3
        assert all(axis["scale"] for axis in option["yAxis"])
        assert not figure.layout.meta["missing_series"]

    def test_unavailable_eurusd_not_faked_from_spot_or_evz(self):
        days = ["2026-10-12", "2026-10-13"]
        ovx = pd.DataFrame({"observation_date":days, "OVXCLS":[42., 41.]})
        move = pd.DataFrame({"observation_date":days, "MOVE":[75., 76.]})
        figure = cross.build_figure("5Y", ovx=ovx, move=move, eurusd_records=[])
        assert len(figure.data) == 2
        assert any("EUR/USD" in value for value in figure.layout.meta["missing_series"])

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

    def test_invalid_snapshot_identity_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "eurusd.json"
            path.write_text('{"symbol":"EVZ","records":[]}', encoding="utf-8")
            assert cross.load_eurusd_snapshot(path) == []

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
