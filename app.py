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

def _render_chart_with_state(fig, desc_index):
    chart_id = f"macro-chart-{desc_index}"
    for trace in fig.data:
        if getattr(trace, "name", None): trace.uid = f"{chart_id}:{trace.name}"
    fig.update_layout(template="plotly_white", width=None, height=400, margin=dict(l=58, r=58, t=150, b=42), legend=dict(orientation="h", yanchor="bottom", y=1.20, xanchor="left", x=0.02, xref="paper", font=dict(size=10), bgcolor="rgba(255,255,255,0)", traceorder="normal", entrywidthmode="pixels", entrywidth=145), legend2=dict(orientation="h", yanchor="bottom", y=1.105, xanchor="left", x=0.02, xref="paper", font=dict(size=10), bgcolor="rgba(255,255,255,0)", traceorder="normal", entrywidthmode="pixels", entrywidth=145), legend3=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0.02, xref="paper", font=dict(size=10), bgcolor="rgba(255,255,255,0)", traceorder="normal", entrywidthmode="pixels", entrywidth=145))
    payload = json.dumps(pio.to_json(fig, validate=False, pretty=False), ensure_ascii=False)
    html = f'''<!doctype html><html><head><script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script><style>html,body,#chart{{margin:0;padding:0;width:100%;height:100%;overflow:hidden;background:transparent;}}</style></head><body><div id="chart"></div><script>const chartId={json.dumps(chart_id)};const storageKey="macro-dashboard-legend:"+chartId;const fig=JSON.parse({payload});const gd=document.getElementById("chart");function readHidden(){{try{{const v=localStorage.getItem(storageKey);const p=v?JSON.parse(v):[];return Array.isArray(p)?new Set(p):new Set();}}catch(e){{return new Set();}}}}function writeHidden(s){{try{{localStorage.setItem(storageKey,JSON.stringify([...s]));}}catch(e){{}}}}function keyOf(t,i){{return t&&(t.uid||t.name)||String(i);}}function restoreHidden(){{const hidden=readHidden();(fig.data||[]).forEach((t,i)=>{{if(hidden.has(keyOf(t,i)))Plotly.restyle(gd,{{visible:"legendonly"}},[i]);}});}}Plotly.newPlot(gd,fig.data||[],fig.layout||{{}},{{displayModeBar:false,scrollZoom:false,doubleClick:false,editable:false,displaylogo:false,responsive:true}}).then(()=>{{restoreHidden();gd.on("plotly_legendclick",ev=>{{const i=ev.curveNumber,t=gd.data[i],k=keyOf(t,i),hidden=readHidden();if(t.visible==="legendonly"){{Plotly.restyle(gd,{{visible:true}},[i]);hidden.delete(k);}}else{{Plotly.restyle(gd,{{visible:"legendonly"}},[i]);hidden.add(k);}}writeHidden(hidden);return false;}});gd.on("plotly_legenddoubleclick",()=>{{setTimeout(()=>{{const hidden=readHidden();(gd.data||[]).forEach((t,i)=>{{const k=keyOf(t,i);if(t.visible==="legendonly")hidden.add(k);else hidden.delete(k);}});writeHidden(hidden);}},50);return true;}});}});</script></body></html>'''
    st.iframe(html, height=500)

render_call = 'st.plotly_chart(builder(date_range), use_container_width=True, config=PLOTLY_CONFIG); show_parameter_description(desc_index)'
render_replacement = '_render_chart_with_state(builder(date_range), desc_index); show_parameter_description(desc_index)'
if render_call not in source: raise RuntimeError("chart render call not found")
source = source.replace(render_call, render_replacement)
source = source.replace("</style>", ".mini-description { min-height: 54px; box-sizing: border-box; }\n.source-text { min-height: 34px; box-sizing: border-box; }\n</style>", 1)

chart_override = r'''
def _clean_chart_frame(frame, column):
    frame = frame.copy(); frame["observation_date"] = pd.to_datetime(frame["observation_date"], errors="coerce"); frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.dropna(subset=["observation_date", column]).sort_values("observation_date")[["observation_date", column]]

def _apply_split_legends(fig, right_names=(), second_row_names=()):
    for name in right_names: fig.update_traces(selector=dict(name=name), legend="legend2")
    for name in second_row_names: fig.update_traces(selector=dict(name=name), legend="legend3")

def _apply_secondary_yaxis(fig, title="Spread (bp)"):
    # Secondary parameters belong to the right Y axis. Keep that axis dedicated
    # to parameter/spread traces; the left Y axis remains the primary metric axis.
    fig.update_layout(
        yaxis=dict(side="left", anchor="x", fixedrange=True, automargin=True),
        yaxis2=dict(title=title, overlaying="y", side="right", anchor="x", tickmode="sync", showgrid=False, zeroline=True, zerolinecolor="#9ca3af", fixedrange=True, automargin=True, ticks="outside", ticklabelposition="outside")
    )

def build_fig1(date_range):
    frames = [_clean_chart_frame(get_iorb(), "IORB"), _clean_chart_frame(get_rrp_rate(), "RRPONTSYAWARD"), _clean_chart_frame(get_effr(), "EFFR"), _clean_chart_frame(get_sofr(), "SOFR")]
    data = frames[0]
    for frame in frames[1:]: data = data.merge(frame, on="observation_date", how="outer")
    data = filter_range(data.sort_values("observation_date"), date_range); data["SOFR_minus_IORB_bp"] = (data["SOFR"] - data["IORB"]) * 100.0
    fig = go.Figure()
    for column, name, width in [("IORB", "IORB", 2.6), ("RRPONTSYAWARD", "ON RRP", 2.6), ("EFFR", "EFFR", 2.6), ("SOFR", "SOFR", 2.2)]: add_line(fig, data, column, name, width)
    add_line(fig, data, "SOFR_minus_IORB_bp", "SOFR−IORB", 2.2, "dot", "y2", " bp")
    _apply_split_legends(fig, [], ["ON RRP"]); _apply_secondary_yaxis(fig); fig.update_layout(yaxis_title="Rate (%)")
    fig.update_traces(selector=dict(name="SOFR−IORB"), hovertemplate="SOFR−IORB: %{y:.1f} bp<extra></extra>")
    return apply_chart_style(fig, 400)

def build_fig2(date_range):
    frames = [_clean_chart_frame(get_dgs10(), "DGS10"), _clean_chart_frame(get_dfii10(), "DFII10"), _clean_chart_frame(get_fred_series("T10YIE"), "T10YIE")]; data = frames[0]
    for frame in frames[1:]: data = data.merge(frame, on="observation_date", how="outer")
    data = filter_range(data.sort_values("observation_date"), date_range); fig = go.Figure()
    for column, name, width, dash in [("DGS10", "10Y Nominal", 2.8, None), ("DFII10", "10Y Real", 2.6, None), ("T10YIE", "10Y Breakeven", 2.5, "dot")]: add_line(fig, data, column, name, width, dash)
    _apply_split_legends(fig, [], ["10Y Real"]); fig.update_layout(yaxis_title="Yield (%)")
    return apply_chart_style(fig, 400)

def build_fig3(date_range):
    frames = [_clean_chart_frame(get_dgs3mo(), "DGS3MO"), _clean_chart_frame(get_dgs2(), "DGS2"), _clean_chart_frame(get_dgs10(), "DGS10"), _clean_chart_frame(get_fred_series("T10Y2Y"), "T10Y2Y"), _clean_chart_frame(get_fred_series("T10Y3M"), "T10Y3M")]; data = frames[0]
    for frame in frames[1:]: data = data.merge(frame, on="observation_date", how="outer")
    data = filter_range(data.sort_values("observation_date"), date_range); data["T10Y2Y_bp"] = data["T10Y2Y"] * 100.0; data["T10Y3M_bp"] = data["T10Y3M"] * 100.0
    fig = go.Figure()
    for column, name, width in [("DGS3MO", "3M", 2.2), ("DGS2", "2Y", 2.4), ("DGS10", "10Y", 2.8)]: add_line(fig, data, column, name, width)
    add_line(fig, data, "T10Y2Y_bp", "10Y−2Y", 2.2, "dot", "y2", " bp"); add_line(fig, data, "T10Y3M_bp", "10Y−3M", 2.2, "dash", "y2", " bp")
    _apply_split_legends(fig, [], ["2Y"]); fig.update_traces(selector=dict(name="10Y−2Y"), hovertemplate="10Y−2Y: %{y:.1f} bp<extra></extra>"); fig.update_traces(selector=dict(name="10Y−3M"), hovertemplate="10Y−3M: %{y:.1f} bp<extra></extra>"); _apply_secondary_yaxis(fig); fig.update_layout(yaxis_title="Yield (%)")
    return apply_chart_style(fig, 400)

def build_fig4(date_range):
    reserve = _clean_chart_frame(get_wresbal(), "WRESBAL"); tga = _clean_chart_frame(get_wtre_gen(), "WTREGEN"); rrp = _clean_chart_frame(get_rrp_daily(), "RRPONTSYD"); reserve["WRESBAL"] /= 1_000_000.0; tga["WTREGEN"] /= 1_000_000.0; rrp["RRPONTSYD"] /= 1_000.0
    data = reserve.merge(tga, on="observation_date", how="outer").merge(rrp, on="observation_date", how="outer").sort_values("observation_date"); data[["WRESBAL", "WTREGEN"]] = data[["WRESBAL", "WTREGEN"]].ffill(); data["NetLiquidity"] = data["WRESBAL"] - data["WTREGEN"] - data["RRPONTSYD"]; data = filter_range(data, date_range)
    fig = go.Figure()
    for column, name, width, dash in [("NetLiquidity", "Net Liquidity Proxy", 3.0, None), ("WRESBAL", "Reserve Balances", 2.3, None), ("WTREGEN", "TGA", 2.1, "dash"), ("RRPONTSYD", "ON RRP", 2.1, "dot")]: add_line(fig, data, column, name, width, dash, unit=" T")
    _apply_split_legends(fig, [], ["Reserve Balances"]); fig.update_layout(yaxis_title="$T")
    return apply_chart_style(fig, 400)
'''
marker = "\nrender_core_charts"
if marker not in source: raise RuntimeError("render_core_charts call not found")
source = source.replace(marker, "\n" + chart_override + marker, 1)
source = source.replace("IORB / ON RRP / EFFR / SOFR", "IORB / ON RRP / EFFR / SOFR / SOFR−IORB")
source = source.replace("IORB、ON RRP Rate、EFFR、SOFR", "IORB、ON RRP Rate、EFFR、SOFR 与 SOFR−IORB 利差")
source = source.replace("SOFR（Secured Overnight Financing Rate）：以美国国债为抵押的隔夜融资利率。", "SOFR（Secured Overnight Financing Rate）：以美国国债为抵押的隔夜融资利率。SOFR−IORB：SOFR 与 IORB 的利差，单位 bp，用于观察短期融资压力；为 Dashboard 派生指标，不是 FRED 官方独立序列。", 1)
source = source.replace("Net Liquidity Proxy：Reserve Balances − TGA − ON RRP，用于观察美国金融市场流动性方向的分析指标，不是美联储官方命名指标。", "Net Liquidity Proxy：Reserve Balances − TGA − ON RRP。该值由 Dashboard 根据三个 FRED 原始序列计算，不是 FRED 官方独立序列。")
