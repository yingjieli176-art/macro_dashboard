from pathlib import Path

APP = Path("app.py")
text = APP.read_text(encoding="utf-8")
original = text

old = '''def build_fig3(date_range):
    data = get_dgs3mo().merge(get_dgs2(), on="observation_date", how="outer").merge(get_dgs10(), on="observation_date", how="outer").merge(get_fred_series("T10Y2Y"), on="observation_date", how="outer").merge(get_fred_series("T10Y3M"), on="observation_date", how="outer").sort_values("observation_date"); data = filter_range(data, date_range); fig = go.Figure()
    for column, name, width in [("DGS3MO", "3M", 2.2), ("DGS2", "2Y", 2.4), ("DGS10", "10Y", 2.8)]: add_line(fig, data, column, name, width)
    data["T10Y2Y_bp"] = data["T10Y2Y"] * 100.0; data["T10Y3M_bp"] = data["T10Y3M"] * 100.0; add_line(fig, data, "T10Y2Y_bp", "10Y−2Y (R)", 2.2, "dot", "y2", " bp"); add_line(fig, data, "T10Y3M_bp", "10Y−3M (R)", 2.2, "dash", "y2", " bp")
    fig.update_traces(selector=dict(name="10Y−2Y (R)"), hovertemplate="10Y−2Y (R): %{y:.1f} bp<extra></extra>"); fig.update_traces(selector=dict(name="10Y−3M (R)"), hovertemplate="10Y−3M (R): %{y:.1f} bp<extra></extra>")
    fig.update_layout(yaxis=dict(title="Yield (%)", fixedrange=True), yaxis2=dict(title="Spread (bp)", overlaying="y", side="right", anchor="free", position=1.0, showgrid=False, zeroline=True, zerolinecolor="#9ca3af", fixedrange=True, automargin=True, tickfont=dict(size=9))); return apply_chart_style(fig, chart_height(340, 500), date_range)
'''

new = '''def build_fig3(date_range):
    data = get_dgs3mo().merge(get_dgs2(), on="observation_date", how="outer").merge(get_dgs10(), on="observation_date", how="outer").merge(get_fred_series("T10Y2Y"), on="observation_date", how="outer").merge(get_fred_series("T10Y3M"), on="observation_date", how="outer").sort_values("observation_date"); data = filter_range(data, date_range); fig = go.Figure()
    for column, name, width in [("DGS3MO", "3M", 2.2), ("DGS2", "2Y", 2.4), ("DGS10", "10Y", 2.8)]: add_line(fig, data, column, name, width)
    add_line(fig, data, "T10Y2Y", "10Y−2Y (R)", 2.2, "dot", "y2", "%"); add_line(fig, data, "T10Y3M", "10Y−3M (R)", 2.2, "dash", "y2", "%")
    fig.update_traces(selector=dict(name="10Y−2Y (R)"), hovertemplate="10Y−2Y (R): %{y:.3f}%<extra></extra>"); fig.update_traces(selector=dict(name="10Y−3M (R)"), hovertemplate="10Y−3M (R): %{y:.3f}%<extra></extra>")
    fig.update_layout(yaxis=dict(title="Yield (%)", fixedrange=True), yaxis2=dict(title="Spread (%)", overlaying="y", side="right", anchor="free", position=1.0, showgrid=False, zeroline=True, zerolinecolor="#9ca3af", fixedrange=True, automargin=True, tickfont=dict(size=9))); return apply_chart_style(fig, chart_height(340, 500), date_range)
'''

if old not in text:
    if 'Spread (%)' in text and 'T10Y2Y_bp' not in text:
        print('Treasury curve spreads already use percent')
    else:
        raise RuntimeError('build_fig3 bp block not found')
else:
    text = text.replace(old, new, 1)

# Keep the explanation explicit so users do not need to convert bp manually.
text = text.replace(
    '4. 10Y−2Y：10 年期减 2 年期国债收益率利差，用于描述收益率曲线的中长期斜率。<br>5. 10Y−3M：10 年期减 3 个月期国债收益率利差，用于描述长期利率相对短期政策利率的期限结构。',
    '4. 10Y−2Y：10 年期减 2 年期国债收益率利差，图中直接以百分比（%）显示，无需自行换算 bp。<br>5. 10Y−3M：10 年期减 3 个月期国债收益率利差，图中直接以百分比（%）显示，无需自行换算 bp。',
    1,
)

if text != original:
    APP.write_text(text, encoding='utf-8')
    print('Treasury curve spread units converted from bp to percent')
else:
    print('No app.py changes needed')
