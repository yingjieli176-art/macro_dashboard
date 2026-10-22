"""ECharts component with client-side legend/axis visibility linkage.

Streamlit's native JSON-only chart cannot register legend event handlers.
Serve the pinned Apache ECharts module from this app, with no CDN dependency.
"""
from pathlib import Path

import streamlit.components.v2 as components


def _component():
    # Re-register the identical definition for the current Streamlit runtime.
    # A process-level cached callable can outlive its registry after restart.
    frontend = Path(__file__).with_name("frontend")
    return components.component(
        "macro_linked_chart",
        html='<div class="macro-chart-shell"><div data-testid="macroEChartsChart" '
             'aria-busy="true" style="height:465px;width:100%;min-width:0"></div>'
             '<div class="macro-chart-tools"><button type="button" '
             'aria-label="Download as PNG" title="下载图片">↓</button>'
             '<button type="button" aria-label="Fullscreen" title="全屏">⛶</button>'
             '</div><p role="alert" class="macro-chart-error" hidden></p></div>',
        css='.macro-chart-shell{position:relative;width:100%;min-width:0}'
            '.macro-chart-tools{position:absolute;right:0;top:0;display:flex;gap:4px}'
            '.macro-chart-tools button{border:0;background:#fff;color:#64748b;'
            'cursor:pointer;font-size:15px;padding:0 5px}'
            '.macro-chart-shell:fullscreen{background:#fff;width:100vw;height:100vh}'
            '.macro-chart-error{color:#b91c1c;font-size:12px}',
        js=(frontend / "linked_charts.js").read_text(encoding="utf-8"),
        isolate_styles=False,
    )


def render_echarts_chart(option, *, height=465, width="stretch", key=None, theme=None):
    # The component key still includes the period so a new month applies its
    # own X window. Legend choices belong to the chart, independently of it.
    parts = str(key or "").rsplit("_", 1)
    legend_key = parts[0] if len(parts) == 2 and parts[1] in {"5Y", "1Y", "6M", "3M", "1M"} else str(key or "")
    return _component()(data={"option": option, "height": height, "legend_state_key": legend_key},
                        key=key, height=height, width=width)
