from pathlib import Path

APP = Path("app.py")
text = APP.read_text(encoding="utf-8")
original = text

old_helper = '''def build_fig5(date_range):
    return build_hk_liquidity_figures(date_range, compact_mode=False)
'''
new_helper = '''def build_fig5(date_range):
    return build_hk_liquidity_figures(date_range, compact_mode=False)


def apply_hk_chart_range(fig, date_range):
    """Apply an independent viewport to one Hong Kong chart without refetching market data."""
    hk_data = load_hk_liquidity()
    if hk_data.empty:
        return fig
    latest = hk_data.loc[
        hk_data.drop(columns=["observation_date"]).notna().any(axis=1), "observation_date"
    ].max()
    if pd.isna(latest):
        latest = hk_data["observation_date"].max()
    offsets = {
        "5Y": pd.DateOffset(years=5),
        "1Y": pd.DateOffset(years=1),
        "6M": pd.DateOffset(months=6),
        "3M": pd.DateOffset(months=3),
        "1M": pd.DateOffset(months=1),
    }
    start = latest - offsets.get(date_range, offsets["1Y"])
    fig.update_xaxes(range=[start, latest])
    return fig
'''
if old_helper not in text:
    raise RuntimeError("build_fig5 helper not found")
text = text.replace(old_helper, new_helper, 1)

old_render = '''    hk_range = st.radio("时间范围", RANGES, horizontal=True, index=1, key="normal_hk_liquidity_range", label_visibility="collapsed")
    hk_figures = build_fig5(hk_range)
    for hk_index, hk_figure in enumerate(hk_figures):
        st.plotly_chart(hk_figure, use_container_width=True, config=PLOTLY_CONFIG)
        show_hk_parameter_description(hk_index)
        if hk_index < len(hk_figures) - 1:
            st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)
'''
new_render = '''    # Build the full data set once; each 5-x panel controls only its own visible X-axis window.
    hk_figures = build_fig5("5Y")
    hk_range_keys = [
        "hk_5_1_range",
        "hk_5_2_range",
        "hk_5_3_range",
        "hk_5_4_range",
    ]
    for hk_index, hk_figure in enumerate(hk_figures):
        hk_range = st.radio(
            "时间范围",
            RANGES,
            horizontal=True,
            index=1,
            key=hk_range_keys[hk_index],
            label_visibility="collapsed",
        )
        st.plotly_chart(
            apply_hk_chart_range(hk_figure, hk_range),
            use_container_width=True,
            config=PLOTLY_CONFIG,
        )
        show_hk_parameter_description(hk_index)
        if hk_index < len(hk_figures) - 1:
            st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)
'''
if old_render not in text:
    raise RuntimeError("Hong Kong chart render block not found")
text = text.replace(old_render, new_render, 1)

if text == original:
    raise RuntimeError("No app.py changes made")
APP.write_text(text, encoding="utf-8")
print("app.py updated with independent 5-1/5-2/5-3/5-4 date ranges")
