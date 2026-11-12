from copy import deepcopy
import unittest

from macro_platform.parameter_guide import compact_parameter_labels, short_parameter_label, HINTS


class ReadableLabels(unittest.TestCase):
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
        self.assertIn('〔左轴 · bp〕', labels['NVIDIA 5Y'])
        self.assertIn('〔R1 · %〕', labels['HY OAS (R1)'])
        self.assertIn('〔R2 · pts〕', labels['NASDAQ-100 (R2)'])
        self.assertEqual(before, option)
        self.assertEqual(labels, compact_parameter_labels(option))


if __name__ == '__main__':
    unittest.main()
