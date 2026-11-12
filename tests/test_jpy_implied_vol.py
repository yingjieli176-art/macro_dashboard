import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from macro_platform import jpy_implied_vol as iv
from macro_platform.yen_carry import combine_yen_carry_figures
import plotly.graph_objects as go

NOW = '2026-11-12T04:00Z'


def report(day=11, quote='7.27 (+0.07)'):
    return f'''<html><div class="blogTitle">{day} Nov 2026, 1230 GMT</div>
    <div class="mainTitle">ATM VOLATILITIES</div><div class="volSection"><table>
    <tr><th></th><th>Pair</th><th>Spot</th><th>1m</th><th>3m</th><th></th></tr>
    <tr><td></td><td>EURUSD</td><td>1.11</td><td>5.1 (+0.1)</td><td>5.8 (+0.2)</td></tr>
    <tr><td></td><td>USDJPY</td><td>159.16 (+0.6%)</td><td>6.64 (+0.04)</td><td>{quote}</td></tr>
    </table><span>Change from 2026-11-{day-1:02d} 12:30 to 2026-11-{day:02d} 12:30 UTC</span></div>
    <div class="mainTitle">25-DELTA RISK REVERSAL</div><div><table>
    <tr><th>Pair</th><th>3m</th></tr><tr><td>USDJPY</td><td>-1.74 (+0.06)</td></tr>
    </table></div></html>'''


class SaxoImpliedVolTests(unittest.TestCase):
    def test_exact_atm_pair_tenor_and_source_time_not_spot_rr_or_change(self):
        row = iv.parse_quote(report(), NOW)
        self.assertEqual(row, {'observation_date': '2026-11-11',
                              'observation_timestamp': '2026-11-11T12:30:00+00:00', 'value': 7.27})

    def test_rejects_future_mismatched_dates_missing_identity_and_invalid_quotes(self):
        bad_reports = [report(day=12), report().replace('11 Nov 2026', '10 Nov 2026'),
                       report().replace('ATM VOLATILITIES', '25-DELTA RISK REVERSAL'),
                       report().replace('USDJPY', 'EURJPY'), report(quote='-1.74 (+0.06)'),
                       report(quote='101 (+0.1)'), report(quote='NaN (+0.1)'),
                       report().replace('<th>3m</th>', '<th>6m</th>')]
        for text in bad_reports:
            with self.subTest(text=text[-80:]), self.assertRaises(ValueError):
                iv.parse_quote(text, NOW)

    def test_append_revisions_keep_history_and_unchanged_time_is_not_refreshed(self):
        first = iv.prepare_snapshot(report(day=10), now=NOW)
        second = iv.prepare_snapshot(report(), first, NOW)
        self.assertEqual([r['observation_date'] for r in second['records']], ['2026-11-10', '2026-11-11'])
        self.assertIsNone(iv.prepare_snapshot(report(), second, NOW))
        revised = iv.prepare_snapshot(report(quote='7.28 (+0.08)'), second, NOW)
        self.assertEqual(revised['records'][0], first['records'][0])
        self.assertEqual(revised['records'][-1]['value'], 7.28)
        with self.assertRaises(ValueError):
            iv.prepare_snapshot(report(day=10), second, NOW)
        with self.assertRaises(ValueError):
            iv.validated_records(dict(second, tenor='1M'), NOW)

    def test_failed_fetch_validation_leaves_original_snapshot_bytes_intact(self):
        from scripts import update_jpy_implied_vol as update
        payload = iv.prepare_snapshot(report(), now=NOW)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'quote.json'
            original = json.dumps(payload).encode()
            path.write_bytes(original)
            with patch.object(update, 'SNAPSHOT', path), \
                 patch.object(update.requests, 'get', return_value=Mock(text='<html>Unavailable</html>')):
                with self.assertRaises(ValueError):
                    update.main()
            self.assertEqual(path.read_bytes(), original)

    def test_single_real_observation_is_visible_without_backfilled_dates(self):
        payload = iv.prepare_snapshot(report(), now=NOW)
        figure = iv.build_figure(payload=payload)
        self.assertEqual(list(figure.data[0].x), ['2026-11-11'])
        self.assertEqual(list(figure.data[0].y), [7.27])
        self.assertEqual(figure.data[0].mode, 'lines+markers')
        combined = combine_yen_carry_figures(go.Figure(), volatility=go.Figure(), implied=figure)
        self.assertEqual(combined.data[0].name, iv.SERIES_NAME)
        self.assertEqual(combined.data[0].yaxis, 'y6')
        self.assertEqual(list(combined.data[0].y), [7.27])
