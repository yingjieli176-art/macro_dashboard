"""Cboe tail-risk provenance, failure retention and independent chart axes."""
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from macro_platform import tail_risk
from macro_platform.echarts_axes import build_adaptive_echarts_option, build_safe_echarts_option
from scripts.update_tail_risk_snapshot import prepare_snapshot
from test_series_calendars import builders, frame


class TailRiskTests(unittest.TestCase):
    def test_new_indicators_keep_original_calendars_and_independent_scales(self):
        ns = builders()
        sources = {
            "VIXCLS": frame(["2026-10-01", "2026-10-02", "2026-10-05"], "VIXCLS", [20., None, 24.]),
            "VXVCLS": frame(["2026-10-01", "2026-10-05"], "VXVCLS", [22., 21.]),
            "SKEW": frame(["2026-10-02", "2026-10-06"], "SKEW", [145., 150.]),
            "VVIX": frame(["2026-10-01", "2026-10-05"], "VVIX", [100., 108.]),
        }
        ns["get_fred_series"] = lambda s: sources[s].copy()
        ns["load_tail_risk_snapshot"] = lambda s: sources[s].copy()
        for period in ("5Y", "1Y", "6M", "3M", "1M"):
            fig = ns["build_fig10"](period)
            self.assertEqual([t.name for t in fig.data],
                             ["VIX", "VIX3M", "VIX/VIX3M (R1)", "SKEW (R2)", "VVIX (R3)", "VVIX/VIX (R1)"])
            for i, s in ((0, "VIXCLS"), (1, "VXVCLS"), (3, "SKEW"), (4, "VVIX")):
                self.assertEqual(list(pd.to_datetime(fig.data[i].x)), list(sources[s].observation_date))
            self.assertEqual(list(pd.Series(fig.data[2].y).dropna()), [20./22., 24./21.])
            self.assertEqual(list(pd.Series(fig.data[5].y).dropna()), [5., 4.5])
            for adapter in (build_adaptive_echarts_option, build_safe_echarts_option):
                option = adapter(fig, period)
                self.assertEqual([s["yAxisIndex"] for s in option["series"]], [0, 0, 1, 2, 3, 1])
                self.assertEqual(len(option["yAxis"]), 4)
                self.assertTrue(all(a["scale"] for a in option["yAxis"]))
                self.assertTrue(all(not s["connectNulls"] for s in option["series"]))
                json.dumps(option, allow_nan=False)

    def test_tail_failure_does_not_hide_vix_or_fabricate_values(self):
        ns = builders()
        ns["get_fred_series"] = lambda s: frame(["2026-10-01"], s, [20.])
        ns["load_tail_risk_snapshot"] = lambda s: (_ for _ in ()).throw(OSError("outage"))
        fig = ns["build_fig10"]("1M")
        self.assertEqual([t.name for t in fig.data], ["VIX", "VIX3M", "VIX/VIX3M (R1)"])
        self.assertEqual(set(fig.layout.meta["missing_series"]), {"SKEW (R2)", "VVIX (R3)", "VVIX/VIX (R1)", "9D/30D (R4)", "SPX P/C (R4)"})

    def history(self, symbol="SKEW", stop="2026-11-03", value=150):
        dates = pd.bdate_range("2022-01-03", stop)
        return "DATE," + symbol + "\n" + "\n".join(f"{d:%m/%d/%Y},{value}" for d in dates)

    def test_snapshot_rejects_stale_short_invalid_and_wrong_symbol_exports(self):
        now = datetime(2026, 11, 4, 12, tzinfo=timezone.utc)
        good = prepare_snapshot(self.history(), "SKEW", {}, now)
        self.assertEqual(good["coverage_end"], "2026-11-03")
        self.assertIsNone(prepare_snapshot(self.history(), "SKEW", good, now))
        for text in (self.history(stop="2026-11-02"), "DATE,SKEW\n11/03/2026,150",
                     self.history().replace("11/03/2026,150", "11/03/2026,inf"),
                     self.history(symbol="VVIX")):
            with self.assertRaises(ValueError):
                prepare_snapshot(text, "SKEW", good, now)

    def test_running_or_future_session_cannot_enter_snapshot(self):
        text = self.history(stop="2026-11-05")
        before_close = datetime(2026, 11, 4, 18, tzinfo=timezone.utc)
        out = prepare_snapshot(text, "SKEW", {}, before_close)
        self.assertEqual(out["coverage_end"], "2026-11-03")
        after_close = datetime(2026, 11, 4, 23, tzinfo=timezone.utc)
        out = prepare_snapshot(text, "SKEW", {}, after_close)
        self.assertEqual(out["coverage_end"], "2026-11-04")

    def test_vix9d_uses_official_ohlc_close_column(self):
        raw = self.history(symbol="CLOSE", value=18).replace("DATE,CLOSE", "DATE,OPEN,HIGH,LOW,CLOSE")
        raw = "\n".join(line if i == 0 else line.replace(",18", ",15,20,14,18") for i, line in enumerate(raw.splitlines()))
        out = prepare_snapshot(raw, "VIX9D", {}, datetime(2026, 11, 4, 12, tzinfo=timezone.utc))
        self.assertEqual(out["symbol"], "VIX9D")
        self.assertEqual(out["records"][-1]["close"], 18)

    def test_loader_checks_identity_and_filters_invalid_observations(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "data_snapshots").mkdir()
            path = root / "data_snapshots/skew_daily.json"
            rows = [{"observation_date": "2026-10-01", "close": 150},
                    {"observation_date": "2026-10-02", "close": 0},
                    {"observation_date": "2099-01-01", "close": 151}]
            with patch.object(tail_risk, "ROOT", root):
                path.write_text(json.dumps(dict(symbol="SKEW", records=rows)))
                self.assertEqual(tail_risk.load_tail_risk_snapshot("SKEW").SKEW.tolist(), [150])
                path.write_text(json.dumps(dict(symbol="VVIX", records=rows)))
                self.assertTrue(tail_risk.load_tail_risk_snapshot("SKEW").empty)


if __name__ == "__main__":
    unittest.main()
