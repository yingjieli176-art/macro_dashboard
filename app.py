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

# Keep the compact dashboard wide enough for readable charts.
source = source.replace("max-width: 1700px;", "max-width: 1850px;")
source = source.replace('cols = st.columns(2, gap="large")', 'cols = st.columns(2, gap="small")')

# Rename the original builders so the wrapper can safely replace chart behavior
# before render_core_charts() is executed.
source = source.replace("def build_fig1(date_range):", "def _base_build_fig1(date_range):", 1)
source = source.replace("def build_fig2(date_range):", "def _base_build_fig2(date_range):", 1)
source = source.replace("def build_fig3(date_range):", "def _base_build_fig3(date_range):", 1)
source = source.replace("def build_fig4(date_range):", "def _base_build_fig4(date_range):", 1)

wrapper_code = r'''

def _xaxis_config(date_range):
    date_cfg = {
        "5Y": {"dtick": "M6", "tickformat": "%Y-%m"},
        "1Y": {"dtick": "M2", "tickformat": "%y-%m"},
        "6M": {"dtick": "M1", "tickformat": "%m-%Y"},
        "3M": {"dtick": "D14", "tickformat": "%m/%d"},
        "1M": {"dtick": "D7", "tickformat": "%m/%d"},
    }.get(date_range, {"dtick": "M1", "tickformat": "%m/%d"})
    return dict(
        domain=[0.035, 0.965], fixedrange=True, automargin=False,
        showgrid=True, gridcolor="#f1f3f5", showline=True,
        linecolor="#c7cdd4", ticks="outside", ticklen=4, tickwidth=1,
        tickfont=dict(size=10), tickangle=-28, ticklabelmode="instant",
        ticklabelstandoff=5, ticklabeloverflow="hide past div",
        hoverformat="%Y-%m-%d", **date_cfg,
    )


def _finalize_chart(fig, right_names=(), right_title=None, left_title=None, date_range=None):
    fig = apply_chart_style(fig, 400)
    fig.update_layout(
        height=400,
        margin=dict(l=58, r=58, t=150, b=62, pad=0, autoexpand=False),
        autosize=True,
        xaxis=_xaxis_config(date_range),
        legend=dict(orientation="h", yanchor="bottom", y=1.20, xanchor="left", x=0,
                    xref="container", font=dict(size=10), bgcolor="rgba(255,255,255,0)"),
        legend2=dict(orientation="h", yanchor="bottom", y=1.20, xanchor="right", x=1,
                     xref="container", font=dict(size=10), bgcolor="rgba(255,255,255,0)"),
        legend3=dict(orientation="h", yanchor="bottom", y=1.105, xanchor="left", x=0,
                     xref="container", font=dict(size=10), bgcolor="rgba(255,255,255,0)"),
    )
    fig.update_yaxes(
        automargin=False, fixedrange=True, ticks="outside", ticklen=4,
        tickwidth=1, tickfont=dict(size=11), nticks=8,
        showgrid=True, gridcolor="#eeeeee",
    )
    if left_title is not None:
        fig.update_layout(yaxis=dict(
            title=left_title, side="left", anchor="x", fixedrange=True,
            automargin=False, ticks="outside", ticklabelposition="outside",
            tickformat=".2f", nticks=8, tickfont=dict(size=11),
        ))
    if right_names or any(getattr(t, "yaxis", "y") == "y2" for t in fig.data):
        fig.update_layout(yaxis2=dict(
            title=right_title or "Spread (bp)", overlaying="y", side="right",
            anchor="x", fixedrange=True, automargin=False, ticks="outside",
            ticklen=4, tickwidth=1, tickfont=dict(size=11), nticks=8,
            ticklabelposition="outside", showgrid=False, zeroline=True,
            zerolinecolor="#9ca3af", tickmode="sync",
        ))
        fig.update_layout(yaxis2_tickformat=".0f" if right_title == "Spread (bp)" else ".2f")
    right_names = set(right_names)
    for trace in fig.data:
        name = getattr(trace, "name", None)
        trace.legend = "legend2" if (getattr(trace, "yaxis", "y") == "y2" or name in right_names) else "legend"
    return fig


def build_fig1(date_range):
    fig = _base_build_fig1(date_range)
    data = get_iorb().merge(get_sofr(), on="observation_date", how="outer").sort_values("observation_date")
    data = filter_range(data, date_range)
    data["SOFR_minus_IORB_bp"] = (data["SOFR"] - data["IORB"]) * 100.0
    add_line(fig, data, "SOFR_minus_IORB_bp", "SOFR−IORB", 2.2, "dot", "y2", " bp")
    fig.update_traces(selector=dict(name="SOFR−IORB"), hovertemplate="SOFR−IORB: %{y:.1f} bp<extra></extra>")
    return _finalize_chart(fig, right_title="Spread (bp)", left_title="Rate (%)", date_range=date_range)


def build_fig2(date_range):
    # Build Chart 2 directly instead of inheriting any state from the base
    # builder. This makes DGS10 / 10Y Nominal an explicit trace in the figure.
    data = (
        get_dgs10()
        .merge(get_dfii10(), on="observation_date", how="outer")
        .merge(get_fred_series("T10YIE"), on="observation_date", how="outer")
        .sort_values("observation_date")
    )
    data = filter_range(data, date_range)
    fig = go.Figure()
    add_line(fig, data, "DGS10", "10Y Nominal", 2.8)
    add_line(fig, data, "DFII10", "10Y Real", 2.6, None, "y2")
    add_line(fig, data, "T10YIE", "10Y Breakeven", 2.5, "dot", "y2")
    # Do not route Chart 2 through split Plotly legends. All three series use
    # one legend; the right axis is determined only by each trace's yaxis.
    for trace in fig.data:
        trace.legend = "legend"
        trace.visible = True
    fig.update_layout(yaxis_title="Yield (%)")
    return _finalize_chart(fig, right_title="Yield (%)", left_title="Yield (%)", date_range=date_range)


def build_fig3(date_range):
    return _finalize_chart(_base_build_fig3(date_range), right_names=("10Y−2Y", "10Y−3M"), right_title="Spread (bp)", left_title="Yield (%)", date_range=date_range)


def build_fig4(date_range):
    return _finalize_chart(_base_build_fig4(date_range), left_title="$T", date_range=date_range)

'''

marker = "def render_core_charts():"
if marker not in source:
    raise RuntimeError("render_core_charts marker not found")
source = source.replace(marker, wrapper_code + marker, 1)

render_call = 'st.plotly_chart(builder(date_range), use_container_width=True, config=PLOTLY_CONFIG); show_parameter_description(desc_index)'
if render_call not in source:
    raise RuntimeError("chart render call not found")

def _render_chart_with_state(fig, desc_index, date_range):
    chart_id = f"macro-chart-{desc_index}"
    for trace in fig.data:
        if getattr(trace, "name", None):
            trace.uid = f"{chart_id}:{trace.name}"
    fig.update_layout(
        template="plotly_white", width=None, height=400, autosize=True,
        margin=dict(l=58, r=58, t=150, b=62, pad=0, autoexpand=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.20, xanchor="left", x=0,
                    xref="container", font=dict(size=10), bgcolor="rgba(255,255,255,0)"),
        legend2=dict(orientation="h", yanchor="bottom", y=1.20, xanchor="right", x=1,
                     xref="container", font=dict(size=10), bgcolor="rgba(255,255,255,0)"),
        legend3=dict(orientation="h", yanchor="bottom", y=1.105, xanchor="left", x=0,
                     xref="container", font=dict(size=10), bgcolor="rgba(255,255,255,0)"),
        xaxis=_xaxis_config(date_range),
    )
    fig.update_yaxes(automargin=False, fixedrange=True, ticks="outside", ticklen=4,
                     tickwidth=1, tickfont=dict(size=11), nticks=8)
    payload = json.dumps(pio.to_json(fig, validate=False, pretty=False), ensure_ascii=False)
    html = f'''<!doctype html><html><head><script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script><style>html,body,#chart{{margin:0;padding:0;width:100%;height:100%;overflow:hidden;background:transparent;}}</style></head><body><div id="chart"></div><script>const chartId={json.dumps(chart_id)};const storageKey="macro-dashboard-legend:"+chartId;const fig=JSON.parse({payload});const gd=document.getElementById("chart");function readHidden(){{try{{const v=localStorage.getItem(storageKey);const p=v?JSON.parse(v):[];return Array.isArray(p)?new Set(p):new Set();}}catch(e){{return new Set();}}}}function writeHidden(s){{try{{localStorage.setItem(storageKey,JSON.stringify([...s]));}}catch(e){{}}}}function keyOf(t,i){{return t&&(t.uid||t.name)||String(i);}}function restoreHidden(){{const hidden=readHidden();(fig.data||[]).forEach((t,i)=>{{if(hidden.has(keyOf(t,i)))Plotly.restyle(gd,{{visible:"legendonly"}},[i]);}});}}Plotly.newPlot(gd,fig.data||[],fig.layout||{{}},{{displayModeBar:false,scrollZoom:false,doubleClick:false,editable:false,displaylogo:false,responsive:true}}).then(()=>{{restoreHidden();gd.on("plotly_legendclick",ev=>{{const i=ev.curveNumber,t=gd.data[i],k=keyOf(t,i),hidden=readHidden();if(t.visible==="legendonly"){{Plotly.restyle(gd,{{visible:true}},[i]);hidden.delete(k);}}else{{Plotly.restyle(gd,{{visible:"legendonly"}},[i]);hidden.add(k);}}writeHidden(hidden);return false;}});}});</script></body></html>'''
    st.components.v1.html(html, height=500, scrolling=False)

source = source.replace(render_call, '_render_chart_with_state(builder(date_range), desc_index, date_range); show_parameter_description(desc_index)')
source = source.replace("</style>", ".mini-description { height: 72px; min-height: 72px; max-height: 72px; box-sizing: border-box; overflow: hidden; }\n.source-text { height: 34px; min-height: 34px; max-height: 34px; box-sizing: border-box; overflow: hidden; }\n</style>", 1)
source = source.replace("IORB / ON RRP / EFFR / SOFR", "IORB / ON RRP / EFFR / SOFR / SOFR−IORB")
source = source.replace("IORB、ON RRP Rate、EFFR、SOFR", "IORB、ON RRP Rate、EFFR、SOFR 与 SOFR−IORB 利差")
source = source.replace("SOFR（Secured Overnight Financing Rate）：以美国国债为抵押的隔夜融资利率。", "SOFR（Secured Overnight Financing Rate）：以美国国债为抵押的隔夜融资利率。SOFR−IORB：SOFR 与 IORB 的利差，单位 bp，用于观察短期融资压力；为 Dashboard 派生指标，不是 FRED 官方独立序列。", 1)
source = source.replace("Net Liquidity Proxy：Reserve Balances − TGA − ON RRP，用于观察美国金融市场流动性方向的分析指标，不是美联储官方命名指标。", "Net Liquidity Proxy：Reserve Balances − TGA − ON RRP。该值由 Dashboard 根据三个 FRED 原始序列计算，不是 FRED 官方独立序列。")

exec(compile(source, str(base_path), "exec"), globals(), globals())
