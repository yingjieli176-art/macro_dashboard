from pathlib import Path

base_path = Path(__file__).with_name("app_base.py")
source = base_path.read_text(encoding="utf-8")

# Parameter UI: use native HTML <details> so opening/closing the parameter
# panel is purely client-side and never depends on Streamlit reruns.
old_parameter_fn = '''def show_parameter_description(index): st.markdown(f'<div class="mini-description">{PARAM_DESCRIPTIONS[index]}</div>', unsafe_allow_html=True)'''
new_parameter_fn = '''def show_parameter_description(index):
    st.markdown(
        f'''<details class="parameter-details">\n<summary>参数</summary>\n<div class="mini-description">{PARAM_DESCRIPTIONS[index]}</div>\n</details>''',
        unsafe_allow_html=True,
    )'''
if old_parameter_fn not in source:
    raise RuntimeError("parameter function not found")
source = source.replace(old_parameter_fn, new_parameter_fn, 1)

# Keep each chart's range selector isolated. The parameter control itself is
# plain HTML, so clicking it works independently for every chart/month range.
fragment_helper = '''
def _render_chart_fragment(column, title, description, key, builder, sources, desc_index, divider=False):
    container = column if column is not None else st
    with container:
        st.markdown(title, unsafe_allow_html=True)
        st.markdown(description, unsafe_allow_html=True)
        date_range = st.radio("时间范围", RANGES, horizontal=True, index=1, key=key, label_visibility="collapsed")
        st.markdown('<div style="height:6px"></div>', unsafe_allow_html=True)
        st.plotly_chart(builder(date_range), use_container_width=True, config=PLOTLY_CONFIG)
        show_parameter_description(desc_index)
        add_sources(sources)
        if divider:
            st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)

if hasattr(st, "fragment"):
    _render_chart_fragment = st.fragment(_render_chart_fragment)
'''
marker = '\ncompact_mode = True\n'
if marker not in source:
    raise RuntimeError("compact mode marker not found")
source = source.replace(marker, fragment_helper + marker, 1)

old_compact_loop = '''        for column, title, description, key, builder, sources, desc_index in configs:\n            with column:\n                st.markdown(title, unsafe_allow_html=True); st.markdown(description, unsafe_allow_html=True); date_range = st.radio("时间范围", RANGES, horizontal=True, index=1, key=key, label_visibility="collapsed"); st.markdown('<div style="height:6px"></div>', unsafe_allow_html=True); st.plotly_chart(builder(date_range), use_container_width=True, config=PLOTLY_CONFIG); show_parameter_description(desc_index); add_sources(sources)\n'''
new_compact_loop = '''        for column, title, description, key, builder, sources, desc_index in configs:\n            _render_chart_fragment(column, title, description, key, builder, sources, desc_index)\n'''
if old_compact_loop not in source:
    raise RuntimeError("compact render loop not found")
source = source.replace(old_compact_loop, new_compact_loop, 1)

old_normal_loop = '''        for title, description, key, builder, sources, desc_index, divider in configs:\n            st.markdown(title, unsafe_allow_html=True); st.markdown(description, unsafe_allow_html=True); date_range = st.radio("时间范围", RANGES, horizontal=True, index=1, key=key, label_visibility="collapsed"); st.plotly_chart(builder(date_range), use_container_width=True, config=PLOTLY_CONFIG); show_parameter_description(desc_index); add_sources(sources)\n            if divider: st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)\n'''
new_normal_loop = '''        for title, description, key, builder, sources, desc_index, divider in configs:\n            _render_chart_fragment(None, title, description, key, builder, sources, desc_index, divider)\n'''
if old_normal_loop not in source:
    raise RuntimeError("normal render loop not found")
source = source.replace(old_normal_loop, new_normal_loop, 1)

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

exec(compile(source, str(base_path), "exec"), globals(), globals())
