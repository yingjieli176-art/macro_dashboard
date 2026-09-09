from pathlib import Path

APP = Path("app.py")
HK = Path("macro_platform/hk_liquidity.py")

# ---- app.py: render Chart 5 as four independent full-width figures ----
app = APP.read_text(encoding="utf-8")
original_app = app

app = app.replace(
    "from macro_platform.hk_liquidity import build_hk_liquidity_figure, liquidity_status_html, load_hk_liquidity",
    "from macro_platform.hk_liquidity import build_hk_liquidity_figure, build_hk_liquidity_figures, liquidity_status_html, load_hk_liquidity",
    1,
)
app = app.replace(
    "def build_fig5(date_range):\n    return build_hk_liquidity_figure(date_range, compact_mode=False)",
    "def build_fig5(date_range):\n    return build_hk_liquidity_figures(date_range, compact_mode=False)",
    1,
)

old_render = '''    hk_range = st.radio("时间范围", RANGES, horizontal=True, index=1, key="normal_hk_liquidity_range", label_visibility="collapsed")
    st.plotly_chart(build_fig5(hk_range), use_container_width=True, config=PLOTLY_CONFIG)
    st.markdown(liquidity_status_html(), unsafe_allow_html=True)
    show_parameter_description(4)
'''
new_render = '''    hk_range = st.radio("时间范围", RANGES, horizontal=True, index=1, key="normal_hk_liquidity_range", label_visibility="collapsed")
    st.markdown(liquidity_status_html(), unsafe_allow_html=True)
    for hk_figure in build_fig5(hk_range):
        st.plotly_chart(hk_figure, use_container_width=True, config=PLOTLY_CONFIG)
    show_parameter_description(4)
'''
if old_render not in app:
    raise RuntimeError("Chart 5 render block not found in app.py")
app = app.replace(old_render, new_render, 1)

if app != original_app:
    APP.write_text(app, encoding="utf-8")
    print("app.py updated for four Chart 5 figures")
else:
    print("app.py already split")

# ---- hk_liquidity.py: add independent figure builder while preserving legacy combined builder ----
hk = HK.read_text(encoding="utf-8")
original_hk = hk

if "def build_hk_liquidity_figures(" not in hk:
    insert_at = hk.index("\ndef liquidity_status_html")
    new_builder = r'''

def build_hk_liquidity_figures(date_range: str, compact_mode: bool = False) -> list[go.Figure]:
    """Build four independent Hong Kong liquidity charts for the dashboard.

    The legacy combined-subplot builder is intentionally retained for backwards
    compatibility and existing CI. The dashboard uses this split view.
    """
    all_data = load_hk_liquidity()
    data = _slice_range(all_data, date_range)
    meta = snapshot_metadata()
    latest_text = meta.get("latest_observation") or "--"

    if data.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="HKMA snapshot unavailable · data pipeline needs refresh",
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
            font=dict(size=14),
        )
        fig.update_layout(height=420, template="plotly_white")
        return [fig]

    def add_line(
        fig: go.Figure,
        column: str,
        name: str,
        color: str,
        width: float = 2.3,
        dash: str | None = None,
        unit: str = "%",
        secondary_y: bool | None = None,
    ) -> None:
        if column not in data.columns or data[column].notna().sum() == 0:
            return
        line: dict[str, Any] = {"width": width, "color": color}
        if dash:
            line["dash"] = dash
        trace = go.Scatter(
            x=data["observation_date"],
            y=data[column],
            name=name,
            mode="lines",
            line=line,
            connectgaps=False,
            hovertemplate=f"{name}: %{{y:.3f}}{unit}<extra></extra>",
        )
        if secondary_y is None:
            fig.add_trace(trace)
        else:
            fig.add_trace(trace, secondary_y=secondary_y)

    def style(fig: go.Figure, title: str, height: int = 410, right_axis: bool = False) -> go.Figure:
        fig.update_layout(
            height=height,
            template="plotly_white",
            hovermode="x unified",
            dragmode=False,
            margin=dict(l=62, r=76 if right_axis else 28, t=96, b=44, pad=2),
            title=dict(text=f"{title} · latest {latest_text}", x=0.01, xanchor="left", font=dict(size=16)),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.08,
                xanchor="left",
                x=0,
                font=dict(size=11),
                traceorder="normal",
                itemwidth=30,
                bgcolor="rgba(255,255,255,0)",
                itemclick="toggle",
                itemdoubleclick="toggleothers",
            ),
            hoverlabel=dict(bgcolor="white", font_size=11, bordercolor="#e5e7eb"),
            font=dict(size=12),
            plot_bgcolor="#ffffff",
            paper_bgcolor="#ffffff",
        )
        fig.update_xaxes(
            showgrid=True,
            gridcolor="#eef2f7",
            griddash="dot",
            showline=True,
            linecolor="#9ca3af",
            linewidth=1,
            fixedrange=True,
            tickformat="%Y-%m",
            tickfont=dict(size=11),
            automargin=False,
        )
        return fig

    # 5A · Money supply
    money = go.Figure()
    add_line(money, "M2 MoM", "M2 MoM", COLORS["m2"], 2.8)
    add_line(money, "M3 MoM", "M3 MoM", COLORS["m3"], 2.3, "dash")
    add_line(money, "Monetary Base MoM", "Monetary Base MoM", COLORS["base"], 1.8, "dot")
    money.update_yaxes(
        title_text="MoM (%)",
        showgrid=True,
        gridcolor="#e5e7eb",
        griddash="dot",
        zeroline=True,
        zerolinecolor="#cbd5e1",
        fixedrange=True,
    )
    style(money, "HK Money Supply")

    # 5B · Banking-system liquidity
    balance = go.Figure()
    add_line(balance, "Aggregate Balance", "Aggregate Balance", COLORS["balance"], 2.8, unit=" HK$ bn")
    balance.update_yaxes(
        title_text="HK$ bn",
        showgrid=True,
        gridcolor="#e5e7eb",
        griddash="dot",
        zeroline=False,
        fixedrange=True,
    )
    style(balance, "Banking-system Liquidity")

    # 5C · HKD funding; spread is the only right-axis parameter.
    funding = make_subplots(specs=[[{"secondary_y": True}]])
    add_line(funding, "HIBOR O/N", "O/N HIBOR", COLORS["on"], 2.0, secondary_y=False)
    add_line(funding, "HIBOR 3M", "3M HIBOR", COLORS["h3m"], 2.3, "dash", secondary_y=False)
    add_line(funding, "HKMA Base Rate", "HKMA Base Rate", COLORS["policy"], 2.0, "dot", secondary_y=False)
    add_line(
        funding,
        "O/N-3M Spread",
        "O/N−3M Spread (R)",
        COLORS["spread"],
        1.7,
        "dashdot",
        " bp",
        secondary_y=True,
    )
    funding.update_yaxes(
        title_text="Rate (%)",
        secondary_y=False,
        showgrid=True,
        gridcolor="#e5e7eb",
        griddash="dot",
        zeroline=True,
        zerolinecolor="#cbd5e1",
        fixedrange=True,
    )
    funding.update_yaxes(
        title_text="Spread (bp)",
        secondary_y=True,
        showgrid=False,
        zeroline=True,
        zerolinecolor="#cbd5e1",
        fixedrange=True,
    )
    style(funding, "HKD Funding", height=430, right_axis=True)

    # 5D · Convertibility band
    fx = go.Figure()
    add_line(fx, "USD/HKD", "USD/HKD", COLORS["fx"], 2.6, unit="")
    add_line(fx, "Strong-side CU", "Strong-side 7.75", COLORS["strong"], 1.4, "dot", unit="")
    add_line(fx, "Weak-side CU", "Weak-side 7.85", COLORS["weak"], 1.4, "dot", unit="")
    fx.update_yaxes(
        title_text="USD/HKD",
        range=[7.73, 7.87],
        showgrid=True,
        gridcolor="#e5e7eb",
        griddash="dot",
        zeroline=False,
        fixedrange=True,
    )
    style(fx, "USD/HKD Convertibility Band")

    return [money, balance, funding, fx]
'''
    hk = hk[:insert_at] + new_builder + hk[insert_at:]

if hk != original_hk:
    HK.write_text(hk, encoding="utf-8")
    print("hk_liquidity.py updated with four independent figures")
else:
    print("hk_liquidity.py already split")
