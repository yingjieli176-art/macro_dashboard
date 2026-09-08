from pathlib import Path
import json
import plotly.io as pio
import streamlit as st

base_path = Path(__file__).with_name("app_base.py")
source = base_path.read_text(encoding="utf-8")
source = source.replace("get_sina_news", "get_eastmoney_news")
source = source.replace("东方财富「红字焦点快讯」 · 平台已筛选重点 · 每60秒自动刷新", "东方财富 7×24 全球直播 · 全量快讯 · 每60秒自动刷新")
source = source.replace("东方财富红字焦点快讯", "东方财富 7×24 全球直播")
source = source.replace("Eastmoney 7×24 Focus News", "Eastmoney 7×24 Global Live News")

# One fixed Plotly geometry for all four charts. Axis margins are deliberately
# disabled so dual-axis charts cannot change the plotting rectangle.
def _render_chart_with_state(fig, desc_index):
    chart_id = f"macro-chart-{desc_index}"
    for trace in fig.data:
        if getattr(trace, "name", None):
            trace.uid = f"{chart_id}:{trace.name}"
    fig.update_layout(
        template="plotly_white",
        width=None,
        height=400,
        autosize=True,
        margin=dict(l=72, r=72, t=150, b=42, pad=0, autoexpand=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.20, xanchor="left", x=0.02, xref="paper", font=dict(size=10), bgcolor="rgba(255,255,255,0)", traceorder="normal", entrywidthmode="pixels", entrywidth=145),
        legend2=dict(orientation="h", yanchor="bottom", y=1.20, xanchor="right", x=0.98, xref="paper", font=dict(size=10), bgcolor="rgba(255,255,255,0)", traceorder="normal", entrywidthmode="pixels", entrywidth=145),
        legend3=dict(orientation="h", yanchor="bottom", y=1.105, xanchor="left", x=0.02, xref="paper", font=dict(size=10), bgcolor="rgba(255,255,255,0)", traceorder="normal", entrywidthmode="pixels", entrywidth=145),
        xaxis=dict(domain=[0, 1], fixedrange=True, automargin=False),
    )
    fig.update_yaxes(automargin=False, fixedrange=True)
    payload = json.dumps(pio.to_json(fig, validate=False, pretty=False), ensure_ascii=False)
    html = f'''<!doctype html><html><head><script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script><style>html,body,#chart{{margin:0;padding:0;width:100%;height:100%;overflow:hidden;background:transparent;}}</style></head><body><div id="chart"></div><script>const chartId={json.dumps(chart_id)};const storageKey="macro-dashboard-legend:"+chartId;const fig=JSON.parse({payload});const gd=document.getElementById("chart");function readHidden(){{try{{const v=localStorage.getItem(storageKey);const p=v?JSON.parse(v):[];return Array.isArray(p)?new Set(p):new Set();}}catch(e){{return new Set();}}}}function writeHidden(s){{try{{localStorage.setItem(storageKey,JSON.stringify([...s]));}}catch(e){{}}}}function keyOf(t,i){{return t&&(t.uid||t.name)||String(i);}}function restoreHidden(){{const hidden=readHidden();(fig.data||[]).forEach((t,i)=>{{if(hidden.has(keyOf(t,i)))Plotly.restyle(gd,{{visible:"legendonly"}},[i]);}});}}Plotly.newPlot(gd,fig.data||[],fig.layout||{{}},{{displayModeBar:false,scrollZoom:false,doubleClick:false,editable:false,displaylogo:false,responsive:true}}).then(()=>{{restoreHidden();gd.on("plotly_legendclick",ev=>{{const i=ev.curveNumber,t=gd.data[i],k=keyOf(t,i),hidden=readHidden();if(t.visible==="legendonly"){{Plotly.restyle(gd,{{visible:true}},[i]);hidden.delete(k);}}else{{Plotly.restyle(gd,{{visible:"legendonly"}},[i]);hidden.add(k);}}writeHidden(hidden);return false;}});gd.on("plotly_legenddoubleclick",()=>{{setTimeout(()=>{{const hidden=readHidden();(gd.data||[]).forEach((t,i)=>{{const k=keyOf(t,i);if(t.visible==="legendonly")hidden.add(k);else hidden.delete(k);}});writeHidden(hidden);}},50);return true;}});}});</script></body></html>'''
    st.iframe(html, height=500)

render_call = 'st.plotly_chart(builder(date_range), use_container_width=True, config=PLOTLY_CONFIG); show_parameter_description(desc_index)'
if render_call not in source:
    raise RuntimeError("chart render call not found")
source = source.replace(render_call, '_render_chart_with_state(builder(date_range), desc_index); show_parameter_description(desc_index)')
source = source.replace("</style>", ".mini-description { min-height: 54px; box-sizing: border-box; }\n.source-text { min-height: 34px; box-sizing: border-box; }\n</style>", 1)

# Reuse the base data builders, then make the axis/legend contract explicit.
# This avoids duplicating the data-fetching logic in app.py.
chart_override = r'''
_orig_build_fig1 = build_fig1
_orig_build_fig2 = build_fig2
_orig_build_fig3 = build_fig3
_orig_build_fig4 = build_fig4

def _finalize_chart(fig, right_names=(), second_row_names=(), right_title=None, left_title=None):
    fig = apply_chart_style(fig, 400)
    fig.update_layout(
        height=400,
        margin=dict(l=72, r=72, t=150, b=42, pad=0, autoexpand=False),
        autosize=True,
        xaxis=dict(domain=[0, 1], fixedrange=True, automargin=False, showgrid=False, showline=True, linecolor="#d1d5db", hoverformat="%Y-%m-%d"),
        legend=dict(orientation="h", yanchor="bottom", y=1.20, xanchor="left", x=0.02, xref="paper", font=dict(size=10), bgcolor="rgba(255,255,255,0)", entrywidthmode="pixels", entrywidth=145),
        legend2=dict(orientation="h", yanchor="bottom", y=1.20, xanchor="right", x=0.98, xref="paper", font=dict(size=10), bgcolor="rgba(255,255,255,0)", entrywidthmode="pixels", entrywidth=145),
        legend3=dict(orientation="h", yanchor="bottom", y=1.105, xanchor="left", x=0.02, xref="paper", font=dict(size=10), bgcolor="rgba(255,255,255,0)", entrywidthmode="pixels", entrywidth=145),
    )
    fig.update_yaxes(automargin=False, fixedrange=True)
    if left_title is not None:
        fig.update_layout(yaxis=dict(title=left_title, side="left", anchor="x", fixedrange=True, automargin=False, ticks="outside", ticklabelposition="outside"))
    if right_names or any(getattr(t, "yaxis", "y") == "y2" for t in fig.data):
        fig.update_layout(yaxis2=dict(title=right_title or "Spread (bp)", overlaying="y", side="right", anchor="x", fixedrange=True, automargin=False, ticks="outside", ticklabelposition="outside", showgrid=False, zeroline=True, zerolinecolor="#9ca3af", tickmode="sync"))
    right_names = set(right_names)
    second_row_names = set(second_row_names)
    for trace in fig.data:
        name = getattr(trace, "name", None)
        if getattr(trace, "yaxis", "y") == "y2" or name in right_names:
            trace.legend = "legend2"
        elif name in second_row_names:
            trace.legend = "legend3"
        else:
            trace.legend = "legend"
    return fig

def build_fig1(date_range):
    fig = _orig_build_fig1(date_range)
    data = get_iorb().merge(get_sofr(), on="observation_date", how="outer").sort_values("observation_date")
    data = filter_range(data, date_range)
    data["SOFR_minus_IORB_bp"] = (data["SOFR"] - data["IORB"]) * 100.0
    add_line(fig, data, "SOFR_minus_IORB_bp", "SOFR−IORB", 2.2, "dot", "y2", " bp")
    fig.update_traces(selector=dict(name="SOFR−IORB"), hovertemplate="SOFR−IORB: %{y:.1f} bp<extra></extra>")
    return _finalize_chart(fig, second_row_names=("ON RRP",), right_title="Spread (bp)", left_title="Rate (%)")

def build_fig2(date_range):
    fig = _orig_build_fig2(date_range)
    return _finalize_chart(fig, second_row_names=("10Y Real",), left_title="Yield (%)")

def build_fig3(date_range):
    fig = _orig_build_fig3(date_range)
    return _finalize_chart(fig, second_row_names=("2Y",), right_names=("10Y−2Y", "10Y−3M"), right_title="Spread (bp)", left_title="Yield (%)")

def build_fig4(date_range):
    fig = _orig_build_fig4(date_range)
    return _finalize_chart(fig, second_row_names=("Reserve Balances",), left_title="$T")
'''

marker = "\nrender_core_charts"
if marker not in source:
    raise RuntimeError("render_core_charts call not found")
source = source.replace(marker, "\n" + chart_override + marker, 1)
source = source.replace("IORB / ON RRP / EFFR / SOFR", "IORB / ON RRP / EFFR / SOFR / SOFR−IORB")
source = source.replace("IORB、ON RRP Rate、EFFR、SOFR", "IORB、ON RRP Rate、EFFR、SOFR 与 SOFR−IORB 利差")
source = source.replace("SOFR（Secured Overnight Financing Rate）：以美国国债为抵押的隔夜融资利率。", "SOFR（Secured Overnight Financing Rate）：以美国国债为抵押的隔夜融资利率。SOFR−IORB：SOFR 与 IORB 的利差，单位 bp，用于观察短期融资压力；为 Dashboard 派生指标，不是 FRED 官方独立序列。", 1)
source = source.replace("Net Liquidity Proxy：Reserve Balances − TGA − ON RRP，用于观察美国金融市场流动性方向的分析指标，不是美联储官方命名指标。", "Net Liquidity Proxy：Reserve Balances − TGA − ON RRP。该值由 Dashboard 根据三个 FRED 原始序列计算，不是 FRED 官方独立序列。")

exec(compile(source, str(base_path), "exec"), globals(), globals())
