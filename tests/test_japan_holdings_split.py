"""Splitting a chart must preserve observations and keep each unit independent."""
import unittest
import plotly.graph_objects as go
from macro_platform.yen_carry import combine_yen_carry_figures, combine_japan_holdings_figures
from macro_platform.dashboard_layout import MACRO_DISPLAY_NUMBER


class JapanHoldingsSplitTests(unittest.TestCase):
    def test_observations_and_signed_flows_survive_the_move_without_mutating_sources(self):
        sources = []
        for names, axes in ((['total', 'long', 'short', 'net', 'valuation'], ['y']*3+['y2']*2),
                            (['gpif', 'life'], ['y']*2), (['life hedge', 'postal hedge'], ['y']*2)):
            fig = go.Figure()
            for name, axis in zip(names, axes):
                fig.add_scatter(name=name, x=['2025-03-31', '2026-03-31'], y=[-2, 5], yaxis=axis)
            sources.append(fig)
        before = [f.to_json() for f in sources]
        result = combine_japan_holdings_figures(sources[0], holdings=sources[1], hedging=sources[2])
        self.assertEqual(len(result.data), 9)
        self.assertEqual([t.yaxis for t in result.data], ['y']*3+['y2']*2+['y3']*2+['y4']*2)
        for trace in result.data:
            self.assertEqual(list(trace.x), ['2025-03-31', '2026-03-31'])
            self.assertEqual(list(trace.y), [-2, 5])
        self.assertEqual([f.to_json() for f in sources], before)
        carry = combine_yen_carry_figures(go.Figure(go.Scatter(name='USD/JPY', x=['2026-03-31'], y=[150])),
                                         volatility=go.Figure())
        self.assertTrue({t.name for t in result.data}.isdisjoint(t.name for t in carry.data))
        self.assertEqual(MACRO_DISPLAY_NUMBER['japan_holdings'], 12)
        self.assertEqual(MACRO_DISPLAY_NUMBER[16], 11)
        self.assertEqual(MACRO_DISPLAY_NUMBER[14], 13)
