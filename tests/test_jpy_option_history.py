from copy import deepcopy
import unittest
from unittest.mock import Mock

import plotly.graph_objects as go

from macro_platform import jpy_option_history as history
from macro_platform import jpy_risk_reversal as rr
from macro_platform.yen_carry import combine_yen_carry_figures
from macro_platform.echarts_axes import build_adaptive_echarts_option, option_observation_health

URL = 'https://q-cam.com/wp-content/uploads/2026/11/QCAM-MONTHLY-November-2026.pdf'
PAGE = '''FX Volatility
Source: QCAM Currency Asset Management, as of November 4th, 2026
Historical Volatility 1 Implied Volatility 2
Current 1M 12M average Current 1M 12M average
USDJPY 158.290 7.57% 9.87% 8.41% 10.01% 7.42% 8.84% 8.65% 9.80%
GBPUSD 1.347
1 Realised 3-month volatility (annualised)
2 Market implied 3-month volatility (annualised)
'''
NOW = '2026-11-16T12:00Z'
REPORT = '''<div class="blogTitle">16 Nov 2026, 0700 GMT</div>
<div class="mainTitle">25-DELTA RISK REVERSAL</div><div><table>
<tr><th>Pair</th><th>Spot</th><th>1w</th><th>1m</th><th>3m</th></tr>
<tr><td>EURUSD</td><td>1.1 (-0.5%)</td><td>-.1 (+.1)</td><td>-0.56 (+0.1)</td><td>-0.62 (+0.01)</td></tr>
<tr><td>USDJPY</td><td>159.54 (-0.14%)</td><td>-1.56 (-0.01)</td><td>-1.74 (+0.01)</td><td>-1.58 (+0.07)</td></tr>
</table>Change from 2026-11-13 07:00 to 2026-11-16 07:00 UTC</div>'''


class OptionHistoryTests(unittest.TestCase):
    def test_selects_current_implied_column_and_actual_table_date(self):
        row = history.parse_page(PAGE, URL, 9, NOW)
        self.assertEqual(row['value'], 7.42)
        self.assertEqual(row['observation_date'], '2026-11-04')
        self.assertEqual(row['issue_month'], '2026-11')
        self.assertEqual(row['source_page'], 9)
        self.assertNotIn('ATM', history.SERIES_NAME)
        row['source_sha256'] = 'a'*64
        payload = dict(history.IDENTITY, records=[row])
        fig = history.build_figure(payload=payload)
        self.assertEqual(list(fig.data[0].x), ['2026-11-04'])
        self.assertEqual(list(fig.data[0].y), [7.42])
        self.assertEqual(fig.data[0].meta['observation_cadence'], 'monthly')
        option = build_adaptive_echarts_option(fig)
        current = option_observation_health(option, now='2026-11-16')
        self.assertFalse(current['stale_names'])
        self.assertEqual(current['due_by_name'][history.SERIES_NAME], '2026-12-15')
        self.assertIn(history.SERIES_NAME, option_observation_health(option, now='2026-12-16')['stale_names'])

    def test_rejects_wrong_definition_columns_dates_and_duplicate_dates(self):
        for page in [PAGE.replace('Market implied', 'Historical'),
                     PAGE.replace('7.42%', ''), PAGE.replace('USDJPY', 'EURJPY'),
                     PAGE.replace('November 4th, 2026', 'November 4th, 2027')]:
            with self.subTest(page=page), self.assertRaises(ValueError):
                history.parse_page(page, URL, 9, NOW)
        row = dict(history.parse_page(PAGE, URL, 9, NOW), source_sha256='a'*64)
        with self.assertRaises(ValueError):
            history.validated_records(dict(history.IDENTITY, records=[row,row]), NOW)

    def test_report_index_prefers_original_month_over_misnamed_reupload(self):
        proper = 'https://q-cam.com/wp-content/uploads/2024/01/QCAM-MONTHLY-January-2024.pdf'
        wrong = proper.replace('/2024/01/', '/2025/01/')
        get = Mock(return_value=Mock(json=lambda:[{'source_url':wrong},{'source_url':proper}]))
        self.assertEqual(history.discover_reports(get)['2024-01'], proper)

    def test_rr_keeps_sign_and_uses_requested_pair_tenor_delta(self):
        row = rr.parse_quote(REPORT, NOW)
        self.assertEqual(row['value'], -1.74)
        self.assertEqual(row['observation_timestamp'], '2026-11-16T07:00:00+00:00')
        self.assertEqual(rr.parse_quote(REPORT.replace('-1.74 (+0.01)', '0 (+0.01)'), NOW)['value'], 0)
        self.assertEqual(rr.parse_quote(REPORT.replace('-1.74 (+0.01)', '1.74 (+0.01)'), NOW)['value'], 1.74)
        payload = rr.prepare_snapshot(REPORT, now=NOW)
        self.assertIsNone(rr.prepare_snapshot(REPORT,payload,NOW))
        with self.assertRaises(ValueError):
            rr.validated_records(dict(payload, convention='JPY_call_minus_JPY_put'), NOW)
        with self.assertRaises(ValueError):
            rr.parse_quote(REPORT.replace('1m','6m'), NOW)
        with self.assertRaises(ValueError):
            rr.parse_quote(REPORT, '2026-11-15T12:00Z')

    def test_monthly_iv_and_daily_rr_keep_separate_axes_and_original_dates(self):
        monthly = history.build_figure(payload=dict(history.IDENTITY, records=[
            dict(history.parse_page(PAGE, URL, 9, NOW), source_sha256='a'*64)]))
        daily_rr = rr.build_figure(payload=rr.prepare_snapshot(REPORT, now=NOW))
        base = go.Figure()
        # Populate existing axes in their stable order, as the actual carry chart does.
        for n in range(5):
            base.add_scatter(x=['2026-11-13'],y=[n+1],name='Base '+str(n),yaxis='y' if n==0 else 'y'+str(n+1))
        combined = combine_yen_carry_figures(base,volatility=go.Figure(),implied=monthly,risk_reversal=daily_rr)
        option = build_adaptive_echarts_option(combined)
        self.assertNotEqual(option['series'][-1]['yAxisIndex'],option['series'][-2]['yAxisIndex'])
        self.assertEqual(option['series'][-1]['data'],[['2026-11-16T00:00:00',-1.74]])
        self.assertEqual(option['series'][-2]['data'],[['2026-11-04T00:00:00',7.42]])

    def test_failed_monthly_parse_cannot_publish_partial_history(self):
        from scripts import update_jpy_option_history as update
        from unittest.mock import patch
        with patch.object(update,'discover_reports',return_value={'2026-11':URL}), \
             patch.object(update,'get',return_value=Mock(content=b'not a PDF')):
            with self.assertRaises(Exception):
                update.collect()
