from pathlib import Path

APP = Path("app.py")
HK = Path("macro_platform/hk_liquidity.py")

# ---- app.py: full-size charts only + restore a unified explanation section ----
text = APP.read_text(encoding="utf-8")
original = text

hk_desc = """    '<b>参数概念：</b><br>1. HKD M2 MoM：港元 M2 月环比增速，用来观察广义港元货币的边际扩张或收缩；主图采用月环比以提高对当前流动性变化的敏感度。<br>2. HKD M3 MoM：港元 M3 月环比增速，统计口径较 M2 更广，用于交叉确认广义货币边际变化。<br>3. Monetary Base MoM：香港货币基础总量月环比变化，用于观察基础货币层面的边际扩张与收缩。<br>4. Aggregate Balance：银行体系总结余，单位 HK$ billion；总结余下降通常代表银行体系可用港元流动性趋紧。<br>5. O/N HIBOR：隔夜港元银行同业拆息，反映最短端港元资金价格。<br>6. 3M HIBOR：3 个月港元银行同业拆息，用来观察更持续的港元融资成本。<br>7. HKMA Base Rate：香港金管局基本利率，是港元利率体系的重要政策参考。<br>8. O/N−3M Spread（R）：隔夜 HIBOR 减 3M HIBOR，右轴单位 bp；显著转正通常代表短端资金压力上升。<br>9. USD/HKD：每 1 美元对应的港元价格；向 7.85 上升表示港元转弱，向 7.75 下降表示港元转强。<br>10. Strong-side CU 7.75：联系汇率制度下强方兑换保证。<br>11. Weak-side CU 7.85：联系汇率制度下弱方兑换保证。<br><br><b>读取提示：</b>M2/M3 为月度统计，公布存在时滞；主图使用 MoM 观察边际变化，流动性评分使用最近 3 个月 M2/M3 MoM 均值降低单月噪声。YoY 保留在数据层供后续切换与中期趋势判断。',\n"""

if "HKD M2 MoM：港元 M2 月环比增速" not in text.split("def show_parameter_description", 1)[0]:
    marker = "\n]\n\ndef show_parameter_description"
    if marker not in text:
        raise RuntimeError("PARAM_DESCRIPTIONS closing marker not found")
    text = text.replace(marker, ",\n" + hk_desc + "]\n\ndef show_parameter_description", 1)

start = text.index("def render_core_charts():")
end = text.index("\nst.markdown('<div id=\"macro-charts\"", start)
new_render = '''def render_core_charts():
    st.markdown('<div class="section-title">US monetary policy, Treasury yields and inflation expectations</div>', unsafe_allow_html=True)

    configs = [
        ('<div class="section-title">🏦 1. Fed Policy Rate & Money Market</div>', '<div class="section-description">IORB / ON RRP Rate / EFFR / SOFR</div>', "normal_corridor_range", build_fig1, [("IORB (IORB)", "https://fred.stlouisfed.org/series/IORB"), ("ON RRP Rate (RRPONTSYAWARD)", "https://fred.stlouisfed.org/series/RRPONTSYAWARD"), ("EFFR (EFFR)", "https://fred.stlouisfed.org/series/EFFR"), ("SOFR (SOFR)", "https://fred.stlouisfed.org/series/SOFR")], 0),
        ('<div class="section-title">2. 10Y Yield Structure</div>', '<div class="section-description">10Y Nominal / 10Y Real (R) / 10Y Breakeven (R)</div>', "normal_yield10_range", build_fig2, [("10Y Nominal (DGS10)", "https://fred.stlouisfed.org/series/DGS10"), ("10Y Real (DFII10)", "https://fred.stlouisfed.org/series/DFII10"), ("10Y Breakeven (T10YIE)", "https://fred.stlouisfed.org/series/T10YIE")], 1),
        ('<div class="section-title">3. Treasury Yield & Curve Spread</div>', '<div class="section-description">3M / 2Y / 10Y / 10Y−2Y (R) / 10Y−3M (R)</div>', "normal_treasury_range", build_fig3, [("3M Treasury (DGS3MO)", "https://fred.stlouisfed.org/series/DGS3MO"), ("2Y Treasury (DGS2)", "https://fred.stlouisfed.org/series/DGS2"), ("10Y Nominal (DGS10)", "https://fred.stlouisfed.org/series/DGS10"), ("10Y−2Y Spread (T10Y2Y)", "https://fred.stlouisfed.org/series/T10Y2Y"), ("10Y−3M Spread (T10Y3M)", "https://fred.stlouisfed.org/series/T10Y3M")], 2),
        ('<div class="section-title">4. US Liquidity</div>', '<div class="section-description">Net Liquidity / Reserve Balances / TGA / ON RRP</div>', "normal_liquidity_range", build_fig4, [("Reserve Balances (WRESBAL)", "https://fred.stlouisfed.org/series/WRESBAL"), ("TGA (WTREGEN)", "https://fred.stlouisfed.org/series/WTREGEN"), ("ON RRP Balance (RRPONTSYD)", "https://fred.stlouisfed.org/series/RRPONTSYD")], 3),
    ]

    for title, description, key, builder, sources, desc_index in configs:
        st.markdown(title, unsafe_allow_html=True)
        st.markdown(description, unsafe_allow_html=True)
        date_range = st.radio("时间范围", RANGES, horizontal=True, index=1, key=key, label_visibility="collapsed")
        st.plotly_chart(builder(date_range), use_container_width=True, config=PLOTLY_CONFIG)
        show_parameter_description(desc_index)
        add_sources(sources)
        st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)

    st.markdown('<div class="section-title">5. Hong Kong Liquidity</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-description">HKD M2/M3 MoM / Monetary Base MoM / Aggregate Balance / HIBOR / O/N−3M Spread (R) / USD-HKD / 7.75–7.85 CU</div>', unsafe_allow_html=True)
    hk_range = st.radio("时间范围", RANGES, horizontal=True, index=1, key="normal_hk_liquidity_range", label_visibility="collapsed")
    st.plotly_chart(build_fig5(hk_range), use_container_width=True, config=PLOTLY_CONFIG)
    st.markdown(liquidity_status_html(), unsafe_allow_html=True)
    show_parameter_description(4)
    add_sources([
        ("HKMA Monetary Statistics", "https://apidocs.hkma.gov.hk/documentation/market-data-and-statistics/monthly-statistical-bulletin/financial/monetary-statistics/"),
        ("HKMA Open API", "https://apidocs.hkma.gov.hk/"),
    ])
'''
text = text[:start] + new_render + text[end:]

# Keep the old global false value because shared chart helpers reference it, but there is no UI toggle anymore.
text = text.replace("def build_fig5(date_range):\n    return build_hk_liquidity_figure(date_range, compact_mode=compact_mode)", "def build_fig5(date_range):\n    return build_hk_liquidity_figure(date_range, compact_mode=False)", 1)

if text != original:
    APP.write_text(text, encoding="utf-8")
    print("app.py refined: full-size charts only and explanations restored")
else:
    print("app.py already refined")

# ---- Chart 5: replace annotation-only labels with real, clickable local legends ----
hk = HK.read_text(encoding="utf-8")
hk_original = hk

start = hk.index("def build_hk_liquidity_figure(")
end = hk.index("\ndef liquidity_status_html", start)
new_hk_builder = '''def build_hk_liquidity_figure(date_range: str, compact_mode: bool = False) -> go.Figure:
    all_data = load_hk_liquidity()
    data = _slice_range(all_data, date_range)

    fig = make_subplots(
        rows=4,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.085,
        row_heights=[0.27, 0.18, 0.29, 0.26],
        specs=[[{}], [{}], [{"secondary_y": True}], [{}]],
    )

    if data.empty:
        fig.add_annotation(
            text="HKMA snapshot unavailable · data pipeline needs refresh",
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
            font=dict(size=14),
        )
        fig.update_layout(height=900, template="plotly_white")
        return fig

    legend_map = {1: "legend", 2: "legend2", 3: "legend3", 4: "legend4"}

    def add_trace(
        row: int,
        column: str,
        name: str,
        color: str,
        width: float = 2.3,
        dash: str | None = None,
        unit: str = "%",
        secondary_y: bool = False,
    ) -> None:
        if column not in data.columns or data[column].notna().sum() == 0:
            return
        line: dict[str, Any] = {"width": width, "color": color}
        if dash:
            line["dash"] = dash
        fig.add_trace(
            go.Scatter(
                x=data["observation_date"],
                y=data[column],
                name=name,
                mode="lines+markers",
                line=line,
                marker=dict(symbol="circle", size=4.5, color=color),
                connectgaps=False,
                showlegend=True,
                legend=legend_map[row],
                legendrank=100 + row,
                hovertemplate=f"{name}: %{{y:.3f}}{unit}<extra></extra>",
            ),
            row=row,
            col=1,
            secondary_y=secondary_y,
        )

    # Order is analytical reading order and is mirrored by each local legend.
    add_trace(1, "M2 MoM", "M2 MoM", COLORS["m2"], 2.8)
    add_trace(1, "M3 MoM", "M3 MoM", COLORS["m3"], 2.3, "dash")
    add_trace(1, "Monetary Base MoM", "Monetary Base MoM", COLORS["base"], 1.8, "dot")

    add_trace(2, "Aggregate Balance", "Aggregate Balance", COLORS["balance"], 2.8, unit=" HK$ bn")

    add_trace(3, "HIBOR O/N", "O/N HIBOR", COLORS["on"], 2.0)
    add_trace(3, "HIBOR 3M", "3M HIBOR", COLORS["h3m"], 2.3, "dash")
    add_trace(3, "HKMA Base Rate", "HKMA Base Rate", COLORS["policy"], 2.0, "dot")
    add_trace(3, "O/N-3M Spread", "O/N−3M Spread (R)", COLORS["spread"], 1.7, "dashdot", " bp", secondary_y=True)

    add_trace(4, "USD/HKD", "USD/HKD", COLORS["fx"], 2.6, unit="")
    add_trace(4, "Strong-side CU", "Strong-side 7.75", COLORS["strong"], 1.4, "dot", unit="")
    add_trace(4, "Weak-side CU", "Weak-side 7.85", COLORS["weak"], 1.4, "dot", unit="")

    state = liquidity_state(all_data)
    meta = snapshot_metadata()
    latest_text = meta.get("latest_observation") or "--"
    fig.update_layout(
        height=960,
        template="plotly_white",
        hovermode="x unified",
        dragmode=False,
        margin=dict(l=62, r=70, t=74, b=42, pad=2),
        title=dict(
            text=f"Hong Kong Liquidity · {state['label']} · latest {latest_text}",
            x=0.01,
            xanchor="left",
            font=dict(size=16),
        ),
        hoverlabel=dict(bgcolor="white", font_size=11, bordercolor="#e5e7eb"),
        font=dict(size=11),
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        legend=dict(traceorder="normal", groupclick="toggleitem", itemclick="toggle", itemdoubleclick="toggleothers"),
    )

    grid = dict(showgrid=True, gridcolor="#e5e7eb", griddash="dot", fixedrange=True)
    fig.update_yaxes(title_text="MoM (%)", row=1, col=1, zeroline=True, zerolinecolor="#cbd5e1", **grid)
    fig.update_yaxes(title_text="HK$ bn", row=2, col=1, zeroline=False, **grid)
    fig.update_yaxes(title_text="Rate (%)", row=3, col=1, secondary_y=False, zeroline=True, zerolinecolor="#cbd5e1", **grid)
    fig.update_yaxes(title_text="Spread (bp)", row=3, col=1, secondary_y=True, showgrid=False, zeroline=True, zerolinecolor="#cbd5e1", fixedrange=True)
    fig.update_yaxes(title_text="USD/HKD", row=4, col=1, range=[7.73, 7.87], zeroline=False, **grid)
    fig.update_xaxes(showgrid=True, gridcolor="#eef2f7", griddash="dot", fixedrange=True, tickformat="%Y-%m", row=4, col=1)

    legend_style = dict(
        orientation="h",
        x=0.0,
        xanchor="left",
        yanchor="bottom",
        bgcolor="rgba(255,255,255,0.88)",
        borderwidth=0,
        font=dict(size=10, color="#374151"),
        itemsizing="constant",
        traceorder="normal",
    )
    # Multiple Plotly legends keep each parameter selector next to its own subplot.
    domains = [fig.layout.yaxis.domain, fig.layout.yaxis2.domain, fig.layout.yaxis3.domain, fig.layout.yaxis5.domain]
    for idx, domain in enumerate(domains, start=1):
        key = "legend" if idx == 1 else f"legend{idx}"
        cfg = dict(legend_style)
        cfg["y"] = min(0.995, float(domain[1]) + 0.012)
        fig.layout[key] = cfg

    return fig
'''
hk = hk[:start] + new_hk_builder + hk[end:]

if hk != hk_original:
    HK.write_text(hk, encoding="utf-8")
    print("Chart 5 refined: local clickable legends with uniform circle markers")
else:
    print("Chart 5 already refined")
