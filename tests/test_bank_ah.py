import json
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
import pandas as pd
from macro_platform.bank_ah import BANKS, SNAPSHOT, calculate_premium, add_bank_premiums
from macro_platform.hk_liquidity import build_hk_core_snapshot_figures, load_hk_funding_daily
from macro_platform.echarts_axes import build_adaptive_echarts_option


class BankAHTests(unittest.TestCase):
    def test_currency_direction_and_common_trading_dates(self):
        def frame(days, prices):
            return pd.DataFrame({"observation_date": pd.to_datetime(days), "close": prices})
        a = frame(["2026-11-10", "2026-11-11"], [6, 8])
        h = frame(["2026-11-10", "2026-11-12"], [5, 5])
        fx = frame(["2026-11-10", "2026-11-11"], [.9, .9])
        result = calculate_premium(a, h, fx)
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result.premium_pct.iloc[0], (6 / (5 * .9) - 1) * 100)

    def test_real_snapshots_keep_auditable_inputs(self):
        payload = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        self.assertEqual(payload["price_basis"], "raw_close")
        for key in BANKS:
            rows = payload["series"][key]["records"]
            self.assertGreater(len(rows), 1000)
            self.assertEqual(len({r['observation_date'] for r in rows}), len(rows))
            for r in rows:
                self.assertAlmostEqual(r["premium_pct"], (r["a_cny"] / (r["h_hkd"] * r["cny_per_hkd"]) - 1) * 100)

    def test_recovered_chart_has_independent_ah_axis_and_one_month_funding(self):
        _, fig = build_hk_core_snapshot_figures("5Y")
        self.assertEqual(len(fig.data), 7)
        self.assertEqual([t.name for t in fig.data[:4]],
            ["1M HIBOR", "3M HIBOR", "HKMA Base Rate", "1M−3M Spread (R1)"])
        self.assertTrue(all(t.yaxis == "y3" for t in fig.data[-3:]))
        option = build_adaptive_echarts_option(fig, "1Y")
        self.assertEqual(len(option["yAxis"]), 3)
        self.assertTrue(all(t["yAxisIndex"] == 2 for t in option["series"][-3:]))
        funding = load_hk_funding_daily().dropna(subset=["HIBOR 1M", "HIBOR 3M"])
        self.assertGreater(len(funding), 200)
        self.assertTrue(((funding["HIBOR 1M"] - funding["HIBOR 3M"]) == funding["1M-3M Spread"]).all())

    def test_missing_bank_source_keeps_funding_visible(self):
        import plotly.graph_objects as go
        with patch('macro_platform.bank_ah.SNAPSHOT') as path:
            path.read_text.side_effect = OSError("missing")
            fig = go.Figure(go.Scatter(x=['2026-11-10'], y=[3]))
            self.assertEqual(len(add_bank_premiums(fig).data), 1)

    def test_failed_refresh_preserves_all_three_banks(self):
        from scripts import update_bank_ah as updater
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'bank.json'
            original = SNAPSHOT.read_bytes()
            target.write_bytes(original)
            with patch.object(updater, 'SNAPSHOT', target), patch.object(
                    updater, 'fetch', side_effect=RuntimeError('provider unavailable')):
                with self.assertRaises(RuntimeError):
                    updater.main()
            self.assertEqual(target.read_bytes(), original)

    def test_live_audit_shares_fx_and_never_substitutes_saved_premiums(self):
        from scripts import probe_all_sources as probe
        probe.reset_probe_cache()
        raw = pd.DataFrame({'observation_date': pd.to_datetime(['2026-11-10']), 'close': [5.]})
        with patch('scripts.update_bank_ah.fetch', return_value=raw) as fetch:
            jobs = [j for j in probe.jobs() if j[0].startswith('BANK_AH_')]
            self.assertEqual(len(jobs), 3)
            for job in jobs:
                self.assertEqual(job[4]()[0], '2026-11-10')
            self.assertEqual(fetch.call_count, 7)
        probe.reset_probe_cache()


if __name__ == "__main__":
    unittest.main()
