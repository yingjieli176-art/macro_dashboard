from datetime import datetime
from pathlib import Path
import json
import unittest
from unittest.mock import patch
import pandas as pd

from macro_platform.japan_corridor import build_corridor_figure, series_frame, REGIME_START
from macro_platform.dashboard_layout import MACRO_DISPLAY_ORDER, MACRO_DISPLAY_NUMBER
from scripts.update_japan_corridor import parse_api, parse_repo, merge_node, validate_rows, collect


class JapanCorridorTests(unittest.TestCase):
    def payload(self):
        return {'schema':'japan_corridor_v1','series':{
            'deposit': {'records':[{'date':'2024-03-21','value':.1},{'date':'2024-08-01','value':.25}], 'verified_through':'2024-08-05'},
            'loan': {'records':[{'date':'2024-03-21','value':.3},{'date':'2024-08-01','value':.5}], 'verified_through':'2024-08-05'},
            'tona': {'records':[{'date':'2024-08-01','value':.227},{'date':'2024-08-02','value':.228}]},
            'repo': {'records':[{'date':'2024-08-01','value':.23}]}}}

    def test_insert_at_japan_start_shifts_every_later_identity(self):
        self.assertEqual(MACRO_DISPLAY_NUMBER['japan_corridor'],9)
        self.assertEqual(MACRO_DISPLAY_NUMBER[15],10)
        self.assertEqual(MACRO_DISPLAY_NUMBER[16],11)
        self.assertEqual(MACRO_DISPLAY_NUMBER[12],22)
        self.assertEqual(len(set(MACRO_DISPLAY_ORDER)),22)

    def test_only_policy_settings_extend_to_publisher_verification_date(self):
        p=self.payload()
        self.assertEqual(series_frame(p,'deposit',now='2024-08-10').date.max(),pd.Timestamp('2024-08-05'))
        self.assertEqual(series_frame(p,'tona',now='2024-08-10').date.max(),pd.Timestamp('2024-08-02'))
        self.assertEqual(series_frame(p,'repo',now='2024-08-10').date.max(),pd.Timestamp('2024-08-01'))

    def test_pre_2024_tiers_are_not_drawn_as_a_uniform_floor(self):
        p=self.payload();p['series']['deposit']['records'].insert(0,{'date':'2023-01-01','value':-.1})
        self.assertEqual(series_frame(p,'deposit',now='2024-08-10').date.min(),pd.Timestamp(REGIME_START))

    def test_four_curves_share_percent_axis_without_fabricated_usage(self):
        fig=build_corridor_figure('1Y',self.payload(),now='2024-08-10')
        self.assertEqual(len(fig.data),4)
        self.assertTrue(all(t.type=='scatter' for t in fig.data))
        self.assertEqual([t.line.shape for t in fig.data[:2]],['hv','hv'])
        self.assertFalse(any('CLF' in t.name for t in fig.data))
        self.assertFalse(any(t.connectgaps for t in fig.data))

    def test_boj_identity_nulls_and_future_values_are_checked(self):
        p={'STATUS':200,'NEXTPOSITION':None,'RESULTSET':[{'SERIES_CODE':'STRDCLUCON','FREQUENCY':'DAILY',
           'UNIT':'percent per annum','VALUES':{'SURVEY_DATES':[20241101,20241102], 'VALUES':[.227,None]}}]}
        self.assertEqual(parse_api(p,'STRDCLUCON'),[{'date':'2024-11-01','value':.227}])
        with self.assertRaises(ValueError):parse_api(p,'OTHER')
        with self.assertRaises(ValueError):validate_rows([{'date':'2099-01-01','value':.1}])

    def test_repo_uses_t0_not_next_day_start(self):
        from io import BytesIO
        dates=pd.bdate_range('2021-01-01',periods=710)
        raw=[['Tokyo Repo Rate',None,None],['term','overnight',None],[None,'T+0','T+1']]
        raw += [[day,.2,.9] for day in dates]
        buffer=BytesIO();pd.DataFrame(raw).to_excel(buffer,index=False,header=False)
        rows=parse_repo(buffer.getvalue())
        self.assertEqual(len(rows),710)
        self.assertTrue(all(row['value']==.2 for row in rows))

    def test_older_export_cannot_replace_last_good_market_close(self):
        old={'records':[{'date':'2024-08-02','value':.228}]}
        with self.assertRaises(ValueError):merge_node(old,[{'date':'2024-08-01','value':.227}])

    def test_source_failure_retains_good_history_and_other_families_advance(self):
        p=self.payload()
        def boj(code,db):
            if db=='FM01':raise TimeoutError('BOJ outage')
            return [{'date':'2024-08-05','value':.5}]
        with patch('scripts.update_japan_corridor.fetch_boj',side_effect=boj), \
             patch('scripts.update_japan_corridor.fetch_admin',side_effect=TimeoutError()), \
             patch('scripts.update_japan_corridor.get',return_value=type('R',(),{'content':b''})()), \
             patch('scripts.update_japan_corridor.parse_repo',return_value=[{'date':'2024-08-05','value':.23}]), \
             patch('scripts.update_japan_corridor.fetch_tona_recent',return_value=[]):
            out,errors=collect(p)
        self.assertEqual(out['series']['tona'],p['series']['tona'])
        self.assertEqual(out['series']['repo']['records'][-1]['date'],'2024-08-05')
        self.assertIn('tona',errors)


if __name__=='__main__':unittest.main()
