from copy import deepcopy
import unittest

from macro_platform.parameter_guide import compact_parameter_labels, short_parameter_label, HINTS, readable_chart_option


class ReadableLabels(unittest.TestCase):
    def test_volatility_units_and_numbered_axes_are_plain_language(self):
        names = ['VIX', 'VIXEQ', 'S&P 500 (R1)', 'VIXEQ/VIX (R2)', 'COR3M (R3)',
                 'MOVE 债市波动率（R4）', 'MOVE/VIX (R5)', 'VXN−VIX (R6)']
        option = {'yAxis': [{'name': 'VIX'}] + [{'name': f'R{i} · {unit}'}
                  for i, unit in enumerate(['pts', '×', 'pts', 'pts', '×', 'pp'], 1)],
                  'series': [{'name': name, 'yAxisIndex': axis} for name, axis in zip(names, [0,0,1,2,3,4,5,6])]}
        labels = compact_parameter_labels(option)
        self.assertIn('〔左轴 · 年化波动率（%）〕', labels['VIX'])
        self.assertIn('〔左轴 · 年化波动率（%）〕', labels['VIXEQ'])
        for name, text in zip(names[2:], ['右轴1 · 指数点','右轴2 · 倍数','右轴3 · 指数点',
                                         '右轴4 · 指数点','右轴5 · 倍数','右轴6 · 百分点']):
            self.assertIn(text, labels[name])

    def test_axis_translation_covers_mobile_and_desktop_without_mutating_option(self):
        option = {'series': [{'name':'VIX', 'data':[['2026-11-12',20]], 'yAxisIndex':0},
                             {'name':'MOVE/VIX (R5)', 'data':[['2026-11-12',5]], 'yAxisIndex':1}],
                  'yAxis':[{'name':'VIX · pts'}, {'name':'R5 · ×', 'scale':True, 'offset':58}],
                  'media':[{'query':{'maxWidth':480}, 'option':{'yAxis':[{'name':'L\npts'}, {'name':'R5\n×'}]}}],
                  'legend':{'selected':{'MOVE/VIX (R5)':False}}, 'dataZoom':[{'start':80,'end':100}]}
        before = deepcopy(option)
        display = readable_chart_option(option)
        self.assertEqual(option, before)
        self.assertEqual(display['series'], before['series'])
        self.assertEqual(display['dataZoom'], before['dataZoom'])
        self.assertEqual(display['legend'], before['legend'])
        self.assertEqual(display['yAxis'][1], {'name':'右轴5 · 倍数', 'scale':True, 'offset':58})
        self.assertEqual(display['media'][0]['option']['yAxis'][0]['name'], '左轴\n年化%')
        self.assertEqual(display['media'][0]['option']['yAxis'][1]['name'], '右轴5\n倍数')

    def test_all_known_parameters_keep_axis_markers(self):
        for name in HINTS:
            for axis in ('R1', 'R2', 'R5'):
                with self.subTest(name=name, axis=axis):
                    self.assertIn(axis, short_parameter_label(name + ' (' + axis + ')'))

    def test_ratios_identify_the_actual_numerator_denominator_and_window(self):
        for name, terms in {
            '9D/30D (R1)': ['VIX9D÷VIX', '9天', '30天', 'R1'],
            'VVIX/VIX (R4)': ['VVIX÷VIX', 'VIX水平', 'R4'],
            'VIX/VIX3M (R1)': ['VIX÷VIX3M', '30天', '3个月'],
            'SPX P/C 63D MA (R1)': ['看跌÷看涨', '63交易日'],
            'SKEW 5D MA (R2)': ['尾部风险', '5交易日'],
        }.items():
            for term in terms:
                self.assertIn(term, short_parameter_label(name))

    def test_every_series_has_rendered_axis_and_unit_without_changing_identity(self):
        option = {'yAxis': [{'name': 'CDS · bp'}, {'name': 'R1 · %'}, {'name': 'R2 · pts'}],
                  'series': [{'name': 'NVIDIA 5Y', 'yAxisIndex': 0, 'data': [['2026-11-09', 100]]},
                             {'name': 'HY OAS (R1)', 'yAxisIndex': 1},
                             {'name': 'NASDAQ-100 (R2)', 'yAxisIndex': 2}],
                  'legend': {'selected': {'HY OAS (R1)': False}}}
        before = deepcopy(option)
        labels = compact_parameter_labels(option)
        self.assertIn('〔左轴 · 基点〕', labels['NVIDIA 5Y'])
        self.assertIn('〔右轴1 · 百分比（%）〕', labels['HY OAS (R1)'])
        self.assertIn('〔右轴2 · 指数点〕', labels['NASDAQ-100 (R2)'])
        self.assertEqual(before, option)
        self.assertEqual(labels, compact_parameter_labels(option))


if __name__ == '__main__':
    unittest.main()
