from pathlib import Path

base_path = Path(__file__).with_name("app_base.py")
source = base_path.read_text(encoding="utf-8")

# Restore the original parameter behavior: the parameter description is
# rendered directly below each chart. Range selection does not create a
# separate parameter state.
old_parameter_fn = '''def show_parameter_description(index): st.markdown(f'<div class="mini-description">{PARAM_DESCRIPTIONS[index]}</div>', unsafe_allow_html=True)'''
new_parameter_fn = old_parameter_fn

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

# Preserve Plotly legend visibility across time-range changes. The state key
# is tied to the chart itself, never to the selected date range.
plotly_call = 'st.plotly_chart(builder(date_range), use_container_width=True, config=PLOTLY_CONFIG)'
plotly_replacement = 'fig = builder(date_range)\n        fig.update_layout(uirevision=f"macro-chart-{desc_index}")\n        st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG, key=f"macro-chart-{desc_index}")'
if plotly_call not in source:
    raise RuntimeError("chart render call not found")
source = source.replace(plotly_call, plotly_replacement, 1)

source = source.replace("IORB / ON RRP / EFFR / SOFR", "IORB / ON RRP / EFFR / SOFR / SOFR−IORB")
source = source.replace("IORB、ON RRP Rate、EFFR、SOFR", "IORB、ON RRP Rate、EFFR、SOFR 与 SOFR−IORB 利差")
source = source.replace(
    "SOFR（Secured Overnight Financing Rate）：以美国国债为抵押的隔夜融资利率。",
    "SOFR（Secured Overnight Financing Rate）：以美国国债为抵押的隔夜融资利率。SOFR−IORB：SOFR 与 IORB 的利差，单位 bp，用于观察短期融资压力；为 Dashboard 派生指标，不是 FRED 官方独立序列。",
    1,
)

exec(compile(source, str(base_path), "exec"), globals(), globals())
