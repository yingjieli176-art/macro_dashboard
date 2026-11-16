"""Cached copies retain every observation and isolate callers without validators."""
from copy import deepcopy
import pickle
import unittest
from unittest.mock import patch

import plotly.graph_objects as go

from macro_platform.figure_cache import CachedFigure
from macro_platform.echarts_axes import cached_adaptive_echarts_option, _cached_chart_option


class FigureCacheTests(unittest.TestCase):
    def test_option_cache_invalidates_values_axes_dates_and_keeps_callers_isolated(self):
        from macro_platform.echarts_axes import build_adaptive_echarts_option
        _cached_chart_option.clear()
        self.addCleanup(_cached_chart_option.clear)
        figure = go.Figure(go.Scatter(x=["2026-11-12", "2026-11-13"], y=[3., 4.], name="Observed"))
        with patch("macro_platform.echarts_axes.build_adaptive_echarts_option",
                   wraps=build_adaptive_echarts_option) as build:
            first = cached_adaptive_echarts_option(figure)
            first["series"][0]["data"][0][1] = 999
            second = cached_adaptive_echarts_option(deepcopy(figure))
            self.assertEqual(build.call_count, 1)
            self.assertEqual(second["series"][0]["data"][0][1], 3.)
            figure.data[0].y = [3., 5.]
            self.assertEqual(cached_adaptive_echarts_option(figure)["series"][0]["data"][-1][1], 5.)
            figure.data[0].x = ["2026-11-12", "2026-11-16"]
            self.assertIn("2026-11-16", cached_adaptive_echarts_option(figure)["series"][0]["data"][-1][0])
            figure.update_yaxes(title="New units")
            cached_adaptive_echarts_option(figure)
            self.assertEqual(build.call_count, 4)

    def test_cached_and_fragment_copies_preserve_values_dates_and_isolation(self):
        figure = go.Figure(go.Scatter(x=["2026-11-12", "2026-11-13"],
                                     y=[4.17, None], name="Observed", yaxis="y2"))
        figure.update_layout(meta={"missing_series": ["Other"]},
                             yaxis2=dict(title="R1 · %", overlaying="y", side="right"))
        cached = CachedFigure(figure.to_dict(), _validate=False)
        for clone in (pickle.loads(pickle.dumps(cached)), deepcopy(cached)):
            self.assertEqual(clone.to_dict(), figure.to_dict())
            clone.data[0].y = [999, 999]
            clone.layout.meta["missing_series"].append("Mutated")
        self.assertEqual(cached.to_dict(), figure.to_dict())
        # A cache hit restores our validated payload without revalidating it.
        with patch.object(go.Figure, "__init__", autospec=True, return_value=None) as init:
            pickle.loads(pickle.dumps(cached))
            self.assertFalse(init.call_args.kwargs["_validate"])
