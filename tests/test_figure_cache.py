"""Cached copies retain every observation and isolate callers without validators."""
from copy import deepcopy
import pickle
import unittest
from unittest.mock import patch

import plotly.graph_objects as go

from macro_platform.figure_cache import CachedFigure


class FigureCacheTests(unittest.TestCase):
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
