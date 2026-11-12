from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from macro_platform import dealer_gamma as gex
from macro_platform.echarts_axes import build_adaptive_echarts_option
from app_test_helpers import builders, frame

NOW = datetime(2026, 11, 12, 12, tzinfo=timezone.utc)
CSV = 'date,price,dix,gex\n2026-11-09,7500,.4,-2000000000\n2026-11-10,7520,.4,0\n2026-11-11,7619,.4,10272903558.04\n'


class DealerGammaTests(unittest.TestCase):
    def test_source_dollars_convert_once_and_preserve_signed_observations(self):
        payload = gex.prepare_snapshot(CSV, now=NOW)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'gex.json'
            path.write_text(json.dumps(payload))
            rows = gex.load_gex_snapshot(path, NOW)
        for actual, expected in zip(rows.GEX_BN, [-2, 0, 10.27290355804]):
            self.assertAlmostEqual(actual, expected)
        self.assertEqual(list(rows.observation_date.dt.strftime('%Y-%m-%d')),
                         ['2026-11-09', '2026-11-10', '2026-11-11'])
        self.assertIsNone(gex.prepare_snapshot(CSV, payload, NOW))

    def test_bad_dates_nonfinite_values_wrong_exports_and_units_are_rejected(self):
        for bad in (CSV.replace('gex', 'G'), CSV.replace('-2000000000', 'inf'),
                    CSV.replace('2026-11-10', '2026-11-09'), CSV.replace('2026-11-11', '2099-01-01')):
            with self.assertRaises(ValueError): gex.prepare_snapshot(bad, now=NOW)
        prior = gex.prepare_snapshot(CSV, now=NOW)
        for key, value in [('symbol', 'SPY'), ('unit', 'USD per 1% move')]:
            bad = deepcopy(prior); bad[key] = value
            with self.assertRaises(ValueError): gex.prepare_snapshot(CSV, bad, NOW)
        with self.assertRaises(ValueError):
            gex.prepare_snapshot('\n'.join(CSV.splitlines()[:-1]), prior, NOW)

    def test_reduced_export_keeps_verified_history_and_accepts_source_corrections(self):
        prior = gex.prepare_snapshot(CSV, now=NOW)
        revised = gex.prepare_snapshot('date,price,dix,gex\n2026-11-11,7619,.4,9000000000\n', prior, NOW)
        self.assertEqual(revised['record_count'], 3)
        self.assertEqual(revised['records'][0], prior['records'][0])
        self.assertEqual(revised['records'][-1]['gex_usd'], 9e9)

    def test_chart_five_uses_independent_dollar_axis_and_real_dates(self):
        ns = builders()
        ns['get_fred_series'] = lambda key: frame(['2026-11-09','2026-11-11'], key, [20,21])
        ns['_dealer_gamma'].load_gex_snapshot = lambda: frame(['2026-11-09','2026-11-11'], 'GEX_BN', [-2,10.27])
        fig = ns['build_fig10']('1Y')
        option = build_adaptive_echarts_option(fig)
        series = next(s for s in option['series'] if s['name'] == gex.SERIES_NAME)
        self.assertEqual([v for _,v in series['data']], [-2,10.27])
        self.assertFalse(series['connectNulls'])
        axis = option['yAxis'][series['yAxisIndex']]
        self.assertIn('十亿美元', axis['name'])
        self.assertTrue(axis['scale'])
