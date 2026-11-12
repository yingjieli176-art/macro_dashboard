from copy import deepcopy
from datetime import datetime, timezone
import unittest

from macro_platform.move_index import parse_yahoo, prepare_snapshot, SERIES_NAME
from macro_platform.echarts_axes import build_adaptive_echarts_option
from app_test_helpers import builders, frame

NOW = datetime(2026,11,12,15,tzinfo=timezone.utc)


class MoveIndexTests(unittest.TestCase):
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
