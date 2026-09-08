from pathlib import Path
import json
import plotly.io as pio
import streamlit.components.v1 as components

base_path = Path(__file__).with_name("app_base.py")
source = base_path.read_text(encoding="utf-8")

# Render Plotly charts in a small component so native legend click state can be
# stored in browser localStorage and restored after Streamlit reruns/range changes.
def _render_chart_with_state(fig, desc_index):
    chart_id = f"macro-chart-{desc_index}"
    for trace in fig.data:
        if getattr(trace, "name", None):
            trace.uid = f"{chart_id}:{trace.name}"

    fig_json = pio.to_json(fig, validate=False, pretty=False)
    payload = json.dumps(fig_json, ensure_ascii=False)
    html = f"""
<!doctype html>
<html>
<head>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>html,body,#chart{{margin:0;width:100%;height:100%;overflow:hidden;background:transparent;}}</style>
</head>
<body>
<div id="chart"></div>
<script>
const chartId = {json.dumps(chart_id)};
const storageKey = "macro-dashboard-legend:" + chartId;
const fig = JSON.parse({payload});
const gd = document.getElementById("chart");

function readHidden() {{
  try {{
    const value = localStorage.getItem(storageKey);
    const parsed = value ? JSON.parse(value) : [];
    return Array.isArray(parsed) ? new Set(parsed) : new Set();
  }} catch (e) {{ return new Set(); }}
}}
function writeHidden(hidden) {{
  try {{ localStorage.setItem(storageKey, JSON.stringify(Array.from(hidden))); }} catch (e) {{}}
}}
function restoreHidden() {{
  const hidden = readHidden();
  const indices = [];
  (fig.data || []).forEach((trace, i) => {{
    const key = trace.uid || trace.name || String(i);
    if (hidden.has(key)) indices.push(i);
  }});
  if (indices.length) Plotly.restyle(gd, {{visible: "legendonly"}}, indices);
}}

Plotly.newPlot(gd, fig.data || [], fig.layout || {{}}, {{displayModeBar:false, scrollZoom:false, doubleClick:false, editable:false, displaylogo:false, responsive:true}}).then(() => {{
  restoreHidden();
  gd.on("plotly_legendclick", (event) => {{
    const hidden = readHidden();
    const index = event.curveNumber;
    const trace = gd.data[index];
    const key = trace && (trace.uid || trace.name || String(index));
    if (!key) return true;
    if (trace.visible === "legendonly") hidden.delete(key);
    else hidden.add(key);
    writeHidden(hidden);
    return true;
  }});
  gd.on("plotly_legenddoubleclick", (event) => {{
    // Plotly handles double-click natively; reconcile the stored state after it.
    setTimeout(() => {{
      const hidden = readHidden();
      (gd.data || []).forEach((trace, i) => {{
        const key = trace.uid || trace.name || String(i);
        if (trace.visible === "legendonly") hidden.add(key);
        else hidden.delete(key);
      }});
      writeHidden(hidden);
    }}, 80);
  }});
}});
</script>
</body>
</html>
"""
    components.html(html, height=470, scrolling=False)

render_call = 'st.plotly_chart(builder(date_range), use_container_width=True, config=PLOTLY_CONFIG); show_parameter_description(desc_index)'
render_replacement = '_render_chart_with_state(builder(date_range), desc_index); show_parameter_description(desc_index)'
if render_call not in source:
    raise RuntimeError("chart render call not found")
source = source.replace(render_call, render_replacement)

# Chart 1: retain the four official series and add the derived SOFR−IORB spread.
start = source.index("def build_fig1(date_range):")
end = source.index("\ndef build_fig2(date_range):", start)
block = source[start:end]
if 'SOFR_minus_IORB_bp' not in block:
    block = block.replace(
        'data = filter_range(data, date_range); fig = go.Figure()\n',
        'data = filter_range(data, date_range);\n    if "SOFR" in data.columns and "IORB" in data.columns:\n        data["SOFR_minus_IORB_bp"] = (data["SOFR"] - data["IORB"]) * 100.0\n    fig = go.Figure()\n',
        1,
    )
    block = block.replace(
        'for column, name, width in [("IORB", "IORB", 2.6), ("RRPONTSYAWARD", "ON RRP", 2.6), ("EFFR", "EFFR", 2.6), ("SOFR", "SOFR", 2.2)]: add_line(fig, data, column, name, width)\n',
        'for column, name, width in [("IORB", "IORB", 2.6), ("RRPONTSYAWARD", "ON RRP", 2.6), ("EFFR", "EFFR", 2.6), ("SOFR", "SOFR", 2.2)]: add_line(fig, data, column, name, width)\n    add_line(fig, data, "SOFR_minus_IORB_bp", "SOFR−IORB", 2.2, "dot", "y2", " bp")\n',
        1,
    )
    block = block.replace(
        'fig.update_layout(yaxis_title="Rate (%)"); return apply_chart_style(fig, chart_height(285, 470))\n',
        'fig.update_layout(yaxis=dict(title="Rate (%)", fixedrange=True), yaxis2=dict(title="Spread (bp)", overlaying="y", side="right", anchor="free", position=1.0, showgrid=False, zeroline=True, zerolinecolor="#9ca3af", fixedrange=True, automargin=True)); fig.update_traces(selector=dict(name="SOFR−IORB"), hovertemplate="SOFR−IORB: %{y:.1f} bp<extra></extra>"); return apply_chart_style(fig, chart_height(285, 470))\n',
        1,
    )
    source = source[:start] + block + source[end:]

source = source.replace("IORB / ON RRP / EFFR / SOFR", "IORB / ON RRP / EFFR / SOFR / SOFR−IORB")
source = source.replace("IORB、ON RRP Rate、EFFR、SOFR", "IORB、ON RRP Rate、EFFR、SOFR 与 SOFR−IORB 利差")
source = source.replace(
    "SOFR（Secured Overnight Financing Rate）：以美国国债为抵押的隔夜融资利率。",
    "SOFR（Secured Overnight Financing Rate）：以美国国债为抵押的隔夜融资利率。SOFR−IORB：SOFR 与 IORB 的利差，单位 bp，用于观察短期融资压力；为 Dashboard 派生指标，不是 FRED 官方独立序列。",
    1,
)

# The news backend uses Eastmoney type=102 (full 7x24 feed), so keep UI labels consistent.
source = source.replace("东方财富「红字焦点快讯」 · 平台已筛选重点 · 每60秒自动刷新", "东方财富 7×24 全球直播 · 全量快讯 · 每60秒自动刷新")
source = source.replace("东方财富红字焦点快讯", "东方财富 7×24 全球直播")
source = source.replace("Eastmoney 7×24 Focus News", "Eastmoney 7×24 Global Live News")

exec(compile(source, str(base_path), "exec"), globals(), globals())
