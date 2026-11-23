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
        html='<div class="macro-chart-shell"><div class="macro-chart-periods" data-testid="macroPeriodControls" role="group" aria-label="时间范围">'
             + ''.join(f'<button type="button" data-period="{period}" disabled>{period}</button>' for period in ('5Y','1Y','6M','3M','1M'))
             + '</div><div data-testid="macroEChartsChart" '
             'aria-busy="true" style="height:465px;width:100%;min-width:0"></div>'
             '<div class="macro-chart-tools"><button type="button" class="macro-chart-lock" '
             'aria-label="锁定最新日期" title="锁定最新日期（默认关闭）" aria-pressed="false">锁定最新日期</button>'
             '<button type="button" aria-label="Download as PNG" title="下载图片">↓</button>'
             '<button type="button" aria-label="Fullscreen" title="全屏">⛶</button>'
             '</div><p role="alert" class="macro-chart-error" hidden></p></div>',
        # A newline keeps attribute selectors from being mistaken for file globs.
        css='.macro-chart-shell{position:relative;width:100%;min-width:0}\n'
            '.macro-chart-periods{display:flex;gap:0;padding-bottom:8px}'
            '.macro-chart-periods button{background:#fff;border:1px solid #d1d5db;color:#334155;'
            'font-family:inherit;font-size:.80rem;font-weight:400;line-height:1.25;'
            'min-height:0;min-width:0;height:auto;padding:3px 10px;cursor:pointer}'
            '.macro-chart-periods button[aria-pressed=true]{color:#ef4444;background:#fff1f2;border-color:#ef4444}'
            '.macro-chart-time{font-size:11px;color:#64748b;text-align:right;margin:3px 0 0}'
            '.macro-chart-tools{position:absolute;right:0;top:0;display:flex;gap:4px}'
            '.macro-chart-tools button{border:0;background:#fff;color:#64748b;'
            'cursor:pointer;font-size:15px;padding:0 5px}'
            '.macro-chart-tools .macro-chart-lock{font-size:12px;border:1px solid #cbd5e1;'
            'border-radius:4px;padding:3px 8px;margin-right:4px;white-space:nowrap}'
            '.macro-chart-tools .macro-chart-lock[aria-pressed=true]{background:#e0f2fe;'
            'color:#075985;border-color:#0284c7}'
            '.macro-chart-shell:fullscreen{background:#fff;width:100vw;height:100vh}'
            '.macro-chart-error{color:#b91c1c;font-size:12px}',
        js=(frontend / "linked_charts.js").read_text(encoding="utf-8"),
        isolate_styles=False,
    )


def render_echarts_chart(option, *, height=465, width="stretch", key=None, theme=None):
    # Keep component identity stable across periods. The requested period
    # travels as data so the existing canvas can apply its new X window.
    logical_key, _, schema = str(key or "").partition("_schema_")
    parts = logical_key.rsplit("_", 1)
    legend_key = parts[0] if len(parts) == 2 and parts[1] in {"5Y", "1Y", "6M", "3M", "1M"} else logical_key
    if schema:
        legend_key += "_schema_" + schema
    price_series = [series for series in option.get("series", []) if any(
        str(line.get("name", "")).endswith(" · 最高收盘")
        for line in (series.get("markLine") or {}).get("data", []))]
    footer_height = 16 + 20 * len(price_series) if price_series else 0
    component_height = height + footer_height
    from macro_platform.parameter_guide import compact_parameter_labels, readable_chart_option
    return _component()(data={"option": readable_chart_option(option), "height": component_height,
                              "parameter_labels": compact_parameter_labels(option),
                              "price_footer_height": footer_height,
                              "period": parts[1] if len(parts) == 2 else None,
                              "legend_state_key": legend_key},
                        key=legend_key or key, height="content", width=width)
