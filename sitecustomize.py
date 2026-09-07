"""Small runtime patch for Chart 4 readability.

Keeps the existing dashboard code intact while giving Fed Total Assets its
own right-side scale so its trend is not visually flattened by smaller
liquidity components.
"""

try:
    import plotly.graph_objects as go

    _orig_add_trace = go.Figure.add_trace
    _orig_update_layout = go.Figure.update_layout

    def _add_trace(self, trace, *args, **kwargs):
        if getattr(trace, "name", None) == "Fed Total Assets":
            trace.update(yaxis="y2")
        return _orig_add_trace(self, trace, *args, **kwargs)

    def _update_layout(self, *args, **kwargs):
        try:
            has_assets = any(getattr(t, "name", None) == "Fed Total Assets" for t in self.data)
            if has_assets:
                layout = kwargs.get("yaxis")
                if isinstance(layout, dict):
                    kwargs["yaxis2"] = {
                        "title": "Fed Total Assets ($T)",
                        "overlaying": "y",
                        "side": "right",
                        "anchor": "free",
                        "position": 1.0,
                        "showgrid": False,
                        "fixedrange": True,
                        "automargin": True,
                    }
        except Exception:
            pass
        return _orig_update_layout(self, *args, **kwargs)

    go.Figure.add_trace = _add_trace
    go.Figure.update_layout = _update_layout
except Exception:
    pass
