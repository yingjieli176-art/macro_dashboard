from pathlib import Path

APP = Path("app.py")
text = APP.read_text(encoding="utf-8")

import_line = "from macro_platform.us_equity_risk import load_vixeq_snapshot\n"
anchor_import = "from macro_platform.chart_axes import apply_time_axis\n"
if import_line not in text:
    if anchor_import not in text:
        raise RuntimeError("chart_axes import anchor not found")
    text = text.replace(anchor_import, anchor_import + import_line, 1)

builder = r'''

def build_fig9(date_range):
    """US equity risk: index vol, constituent vol, VIX term spread, and SPX."""
    frames = []
    for series_id in ("VIXCLS", "VXVCLS", "SP500"):
        try:
            frame = get_fred_series(series_id).copy()
            frame["observation_date"] = pd.to_datetime(frame["observation_date"], errors="coerce")
            frame[series_id] = pd.to_numeric(frame[series_id], errors="coerce")
            frame = frame.dropna(subset=["observation_date", series_id])[["observation_date", series_id]]
            if not frame.empty:
                frames.append(frame)
        except Exception:
            continue

    try:
        vixeq = load_vixeq_snapshot()
        if not vixeq.empty:
            frames.append(vixeq)
    except Exception:
        pass

    if not frames:
        return apply_chart_style(go.Figure(), chart_height(340, 500), date_range)

    data = frames[0]
    for frame in frames[1:]:
        data = data.merge(frame, on="observation_date", how="outer")
    data = data.sort_values("observation_date")
    if "VIXCLS" in data.columns and "VXVCLS" in data.columns:
        data["VIX3M-VIX"] = data["VXVCLS"] - data["VIXCLS"]
    data = filter_range(data, date_range)

    fig = go.Figure()
    add_line(fig, data, "VIXCLS", "VIX", 2.7, unit="")
    add_line(fig, data, "VIXEQ", "VIXEQ", 2.4, "dash", unit="")
    add_line(fig, data, "SP500", "S&P 500 (R1)", 2.4, None, "y2", unit=" pts")
    add_line(fig, data, "VIX3M-VIX", "VIX3M−VIX (R2)", 2.0, "dot", "y3", unit=" pts")

    fig.update_layout(
        yaxis2=dict(overlaying="y", side="right", anchor="free", position=0.86),
        yaxis3=dict(overlaying="y", side="right", anchor="free", position=0.97),
    )
    fig = apply_chart_style(fig, chart_height(360, 520), date_range)
    fig.update_layout(
        margin=dict(l=62, r=144, t=124, b=44, pad=2),
        xaxis=dict(domain=[0.0, 0.84]),
        yaxis=dict(
            title="VIX / VIXEQ",
            showgrid=True, gridcolor="#e5e7eb", griddash="dot",
            zeroline=False, fixedrange=True,
        ),
        yaxis2=dict(
            title="R1 · S&P 500",
            overlaying="y", side="right", anchor="free", position=0.86,
            showgrid=False, zeroline=False, fixedrange=True, tickfont=dict(size=10),
        ),
        yaxis3=dict(
            title="R2 · VIX3M−VIX",
            overlaying="y", side="right", anchor="free", position=0.97,
            showgrid=False, zeroline=True, zerolinecolor="#94a3b8",
            zerolinewidth=1, fixedrange=True, tickfont=dict(size=10),
        ),
    )
    return fig
'''

if "def build_fig9(date_range):" not in text:
    marker = "\nPARAM_DESCRIPTIONS = ["
    if marker not in text:
        raise RuntimeError("PARAM_DESCRIPTIONS anchor not found")
    text = text.replace(marker, builder + marker, 1)

risk_description = r'''

US_EQUITY_RISK_DESCRIPTION = '<b>参数概念：</b><br>1. VIX：基于 S&P 500 指数期权的约 30 天隐含波动率，反映指数层面的近端风险定价。<br>2. VIXEQ：Cboe S&P 500 Constituent Volatility Index，衡量一篮子标普 500 成分股按市值加权的约 30 天隐含波动率；它使用单股期权，因此与 VIX 并非同一个指标。<br>3. S&P 500（R1）：标普 500 指数点位，用来观察风险价格与现货大盘的同步/背离。<br>4. VIX3M−VIX（R2）：3 个月 VIX 减约 30 天 VIX。通常为正代表期限结构较正常；快速收窄或转负表示近端隐含波动率高于远端，常见于短期压力上升阶段。<br><br><b>读取提示：</b>VIX 与 VIXEQ 同时上升代表指数与成分股隐含波动率共同抬升；若 VIXEQ 相对 VIX 更强，通常意味着单股波动/分化风险更突出。VIXEQ 于 2024-11-04 正式开始实时发布；Cboe 官方历史文件提供回溯序列，图表使用官方历史值，不自行外推。'
'''

if "US_EQUITY_RISK_DESCRIPTION =" not in text:
    marker = "\ncompact_mode = False"
    if marker not in text:
        raise RuntimeError("compact_mode anchor not found")
    text = text.replace(marker, risk_description + marker, 1)

old_note = "VIXEQ 自 2024-11-04 起正式发布，因此早于官方可用历史的区间不补造数据。"
new_note = "VIXEQ 于 2024-11-04 正式开始实时发布；Cboe 官方历史文件提供回溯序列，图表使用官方历史值，不自行外推。"
text = text.replace(old_note, new_note)

render_block = r'''

    st.markdown('<div class="section-kicker">US EQUITY RISK</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">9. US Equity Risk & Volatility Structure</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-description">VIX · VIXEQ · S&P 500 (R1) · VIX3M−VIX (R2)</div>', unsafe_allow_html=True)
    risk_range = st.radio(
        "时间范围",
        RANGES,
        horizontal=True,
        index=1,
        key="us_equity_risk_range",
        label_visibility="collapsed",
    )
    st.plotly_chart(build_fig9(risk_range), use_container_width=True, config=PLOTLY_CONFIG)
    st.markdown(f'<div class="mini-description">{US_EQUITY_RISK_DESCRIPTION}</div>', unsafe_allow_html=True)
    add_sources([
        ("Cboe VIX", "https://www.cboe.com/tradable-products/vix/"),
        ("Cboe VIXEQ / Dispersion", "https://www.cboe.com/us/indices/dispersion/"),
        ("FRED VIX3M (VXVCLS)", "https://fred.stlouisfed.org/series/VXVCLS"),
        ("FRED S&P 500 (SP500)", "https://fred.stlouisfed.org/series/SP500"),
    ])
    st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)
'''

if '9. US Equity Risk & Volatility Structure' not in text:
    marker = "\nst.markdown('<div id=\"macro-charts\" class=\"section-anchor\"></div><div class=\"section-kicker\">MACRO CHARTS</div>', unsafe_allow_html=True)"
    if marker not in text:
        raise RuntimeError("render_core_charts end anchor not found")
    text = text.replace(marker, render_block + marker, 1)

APP.write_text(text, encoding="utf-8")
print("Chart 9 added: VIX, VIXEQ, S&P 500 R1, VIX3M-VIX R2")
