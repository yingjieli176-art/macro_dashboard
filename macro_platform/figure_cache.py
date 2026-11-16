"""Fast isolated copies of figures already validated by our chart builders."""
import plotly.graph_objects as go


def _restore_figure(payload):
    # Only our own validated Figure.to_dict() output enters this path.
    # Revalidating every template/trace on each cache read is unnecessary.
    return CachedFigure(payload, _validate=False)


class CachedFigure(go.Figure):
    """Keep normal Figure behavior without revalidating internal cache copies."""

    @classmethod
    def adopt(cls, figure):
        # Builders hand ownership of this fresh, already validated Figure to
        # the cache. Changing only its copy hooks avoids an extra full data/
        # template copy on the first request; all trace parent links stay valid.
        figure.__class__ = cls
        return figure

    def __reduce__(self):
        return _restore_figure, (self.to_dict(),)

    def __deepcopy__(self, memo):
        # to_dict already creates independent copies of data, layout and frames.
        result = _restore_figure(self.to_dict())
        memo[id(self)] = result
        return result
