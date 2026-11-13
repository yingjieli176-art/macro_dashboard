import unittest
import pandas as pd
from app_test_helpers import builders, frame
from macro_platform.echarts_axes import build_adaptive_echarts_option, build_safe_echarts_option


class VxnSpread(unittest.TestCase):
    def test_same_date_difference_signed_pp_and_missing_legs(self):
        ns = builders()
        dates = ['2026-11-02','2026-11-03','2026-11-04','2026-11-05']
        samples = {
            'VIXCLS': frame(dates,'VIXCLS',[20,25,0,30]),
            'VXNCLS': frame(dates[:3]+['2026-11-06'],'VXNCLS',[27,22,15,32]),
            'SP500': frame(dates,'SP500',[6000]*4),
        }
        ns['get_fred_series'] = lambda key: samples[key].copy()
        ns['load_vixeq_snapshot'] = lambda: frame([], 'VIXEQ', [])
        fig = ns['build_fig9']('1Y')
        spread = next(t for t in fig.data if t.name=='VXN−VIX (R6)')
        self.assertEqual(list(spread.y[:2]), [7,-3])
        self.assertTrue(all(pd.isna(v) for v in spread.y[2:]))
        self.assertEqual(spread.yaxis,'y7')
        self.assertFalse(spread.connectgaps)
        for adapter in (build_adaptive_echarts_option,build_safe_echarts_option):
            option=adapter(fig,'1Y')
            s=next(t for t in option['series'] if t['name']==spread.name)
            self.assertIn('pp',option['yAxis'][s['yAxisIndex']]['name'])
            self.assertEqual([p[1] for p in s['data'][:2]],[7,-3])
            self.assertTrue(all(p[1] is None for p in s['data'][2:]))


if __name__=='__main__': unittest.main()
