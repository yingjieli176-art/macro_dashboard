"""Copper context observations, matching-date ratio and independent axes."""
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from macro_platform import copper
from macro_platform.echarts_axes import build_adaptive_echarts_option, build_safe_echarts_option
from scripts import update_copper_snapshot as collector


class CopperContextTests(unittest.TestCase):
    def test_ratio_uses_only_same_date_closes_and_preserves_five_units(self):
        rows = []
        for day, cu, oil, vvix in (("2026-11-01", 4, 80, 100),
                                  ("2026-11-02", None, 90, 110),
                                  ("2026-11-03", 5, None, 105)):
            rows.append(dict(date=day, comex_price_usd_lb=cu, wti_usd_bbl=oil,
                             vvix=vvix, lme_3m_usd_t=9000, lme_cash_usd_t=8900,
                             lme_stock_t=200000, comex_stock_t=300000))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "copper.json"
            path.write_text(json.dumps({"records": rows}))
            with patch.object(copper, "SNAPSHOT_PATH", path), patch.object(copper, "load_tcrc_snapshot", return_value=pd.DataFrame()):
                for period in ("5Y", "1Y", "6M", "3M", "1M"):
                    fig = copper.build_copper_flow_spread_figure(period)
                    ratio = next(t for t in fig.data if t.name == "铜油比 (R4)")
                    self.assertEqual(list(ratio.x), [pd.Timestamp("2026-11-01")])
                    self.assertAlmostEqual(ratio.y[0], 4 * copper.LB_PER_METRIC_TONNE / 80)
                    for adapter in (build_adaptive_echarts_option, build_safe_echarts_option):
                        option = adapter(fig, period)
                        self.assertEqual(len(option["yAxis"]), 5)
                        mapped = {s["name"]: s["yAxisIndex"] for s in option["series"]}
                        self.assertEqual(mapped["WTI 原油 (R3)"], 3)
                        self.assertEqual(mapped["铜油比 (R4)"], 4)
                        self.assertNotIn("VVIX (R5)", mapped)
                        self.assertIn("USD/bbl", option["yAxis"][3]["name"])
                        self.assertIn("bbl/t", option["yAxis"][4]["name"])

                        json.dumps(option, allow_nan=False)

    def test_vvix_rejects_invalid_future_and_nonfinite_observations(self):
        text = "DATE,VVIX\n11/02/2026,107.4\n11/03/2026,0\n11/04/2026,inf\n11/05/2026,90\nbad,100\n11/01/2026,-1\n"
        frame = collector._parse_vvix(text, today=date(2026, 11, 4))
        self.assertEqual(frame.vvix.tolist(), [107.4])
        with self.assertRaises(ValueError):
            collector._parse_vvix("DATE,CLOSE\n11/02/2026,100\n")

    def test_context_outage_or_short_history_preserves_last_good(self):
        old = [{"date": "2026-11-02", "wti_usd_bbl": 96.46, "vvix": 110.47}]
        base = pd.DataFrame({"date": pd.to_datetime(["2026-11-02", "2026-11-03"]),
                             "comex_price_usd_lb": [5.0, 5.1]})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.json"
            path.write_text(json.dumps({"records": old}))
            short = pd.DataFrame({"date": pd.to_datetime(["2026-11-03"]), "wti_usd_bbl": [1.0]})
            with patch.object(collector, "OUT", path), patch.object(collector, "_fetch_wti", return_value=short), \
                    patch.object(collector, "_fetch_vvix", side_effect=RuntimeError("outage")):
                result = collector._merge_context(base).set_index("date")
            self.assertEqual(result.loc["2026-11-02", "wti_usd_bbl"], 96.46)
            self.assertEqual(result.loc["2026-11-02", "vvix"], 110.47)
            self.assertTrue(pd.isna(result.loc["2026-11-03", "wti_usd_bbl"]))
            self.assertEqual(result.loc["2026-11-03", "comex_price_usd_lb"], 5.1)

    def test_first_boot_outage_leaves_missing_context(self):
        base = pd.DataFrame({"date": pd.to_datetime(["2026-11-02"])})
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(collector, "OUT", Path(directory) / "missing.json"), \
                patch.object(collector, "_fetch_wti", side_effect=RuntimeError("outage")), \
                patch.object(collector, "_fetch_vvix", side_effect=RuntimeError("outage")):
            result = collector._merge_context(base)
        self.assertTrue(result[list(collector.CONTEXT_FIELDS)].isna().all().all())


if __name__ == "__main__":
    unittest.main()
