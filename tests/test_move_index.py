from copy import deepcopy
from datetime import datetime, timezone
import unittest
import pandas as pd

from macro_platform.move_index import parse_yahoo, prepare_snapshot, SERIES_NAME
from macro_platform.echarts_axes import build_adaptive_echarts_option, build_safe_echarts_option
from app_test_helpers import builders, frame

NOW = datetime(2026,11,12,15,tzinfo=timezone.utc)


class MoveIndexTests(unittest.TestCase):
    def test_move_vix_only_divides_same_date_positive_finite_legs(self):
        ns = builders()
        dates = ['2026-11-02', '2026-11-03', '2026-11-04', '2026-11-05', '2026-11-06', '2026-11-09']
        ns['get_fred_series'] = lambda key: frame(dates, key, [20, 0, 25, -1, float('inf'), 30])
        ns['load_vixeq_snapshot'] = lambda: frame([], 'VIXEQ', [])
        ns['_move_index'].load_move_snapshot = lambda: frame(
            dates[:5] + ['2026-11-10'], 'MOVE', [100, 90, None, 80, 110, 120])
        fig = ns['build_fig9']('1Y')
        trace = next(t for t in fig.data if t.name == 'MOVE/VIX (R5)')
        self.assertEqual(trace.yaxis, 'y6')
        self.assertEqual(trace.y[0], 5)
        self.assertTrue(all(pd.isna(v) for v in trace.y[1:]))
        self.assertFalse(trace.connectgaps)
        for adapter in (build_adaptive_echarts_option, build_safe_echarts_option):
            option = adapter(fig, '1Y')
            ratio = next(s for s in option['series'] if s['name'] == trace.name)
            move = next(s for s in option['series'] if s['name'] == SERIES_NAME)
            self.assertNotEqual(ratio['yAxisIndex'], move['yAxisIndex'])
            self.assertFalse(ratio['connectNulls'])
            self.assertEqual(ratio['data'][0][1], 5)
            self.assertTrue(all(p[1] is None for p in ratio['data'][1:]))

    def payload(self):
        return {'chart':{'result':[{'meta':{'symbol':'^MOVE','instrumentType':'INDEX',
            'exchangeTimezoneName':'America/New_York'},
            'timestamp':[1794321000,1794407400,1794493800],
            'indicators':{'quote':[{'close':[92.43,None,93.]}], 'adjclose':[{'adjclose':[9,9,9]}]}}], 'error':None}}

    def test_completed_index_closes_ignore_adjusted_data_nulls_and_live_bar(self):
        rows = parse_yahoo(self.payload(), NOW)
        self.assertEqual(rows, [{'observation_date':'2026-11-10','close':92.43}])
        self.assertIsNone(prepare_snapshot(self.payload(), prepare_snapshot(self.payload(),now=NOW), NOW))
        for symbol in ['MOVE','^VIX','NTRS']:
            bad=self.payload();bad['chart']['result'][0]['meta']['symbol']=symbol
            with self.assertRaises(ValueError): parse_yahoo(bad,NOW)

    def test_regressing_source_does_not_replace_verified_close(self):
        previous=prepare_snapshot(self.payload(),now=NOW)
        bad=self.payload();bad['chart']['result'][0]['timestamp'][0]=1794234600
        with self.assertRaises(ValueError): prepare_snapshot(bad,previous,NOW)

    def test_chart_four_gives_move_its_own_axis_and_keeps_points(self):
        ns=builders()
        ns['get_fred_series']=lambda key:frame(['2026-11-10'],key,[20])
        ns['_move_index'].load_move_snapshot=lambda:frame(['2026-11-10'],'MOVE',[92.43])
        fig=ns['build_fig9']('1Y')
        option=build_adaptive_echarts_option(fig)
        move=next(s for s in option['series'] if s['name']==SERIES_NAME)
        vix=next(s for s in option['series'] if s['name']=='VIX')
        self.assertNotEqual(move['yAxisIndex'],vix['yAxisIndex'])
        self.assertEqual(move['data'][0][1],92.43)
        self.assertIn('pts',option['yAxis'][move['yAxisIndex']]['name'])
