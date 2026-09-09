from pathlib import Path

APP = Path("app.py")
HK = Path("macro_platform/hk_liquidity.py")

# ---------- macro_platform/hk_liquidity.py ----------
hk = HK.read_text(encoding="utf-8")

if "import requests\n" not in hk:
    hk = hk.replace("import plotly.graph_objects as go\n", "import plotly.graph_objects as go\nimport requests\n", 1)

start = hk.index("def build_hk_liquidity_figures(")
end = hk.index("\ndef liquidity_status_html", start)

new_builder = r'''def _market_monthly_change(symbol: str, label: str) -> pd.DataFrame:
    """Fetch monthly close-to-close percentage change from Yahoo Finance.

    Market overlays are enrichment only: a network/API failure returns an empty
    frame and must never prevent the HKMA liquidity charts from rendering.
    """
    try:
        response = requests.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
            params={
                "range": "5y",
                "interval": "1mo",
                "includeAdjustedClose": "true",
                "events": "div,splits",
            },
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=3.5,
        )
        response.raise_for_status()
        result = (((response.json() or {}).get("chart") or {}).get("result") or [])
        if not result:
            return pd.DataFrame(columns=["observation_date", label])
        node = result[0] or {}
        timestamps = node.get("timestamp") or []
        indicators = node.get("indicators") or {}
        adj = (indicators.get("adjclose") or [{}])[0].get("adjclose") or []
        closes = adj if len(adj) == len(timestamps) else ((indicators.get("quote") or [{}])[0].get("close") or [])
        if len(closes) != len(timestamps):
            return pd.DataFrame(columns=["observation_date", label])
        frame = pd.DataFrame(
            {
                "observation_date": pd.to_datetime(timestamps, unit="s", utc=True, errors="coerce").tz_convert(None),
                "close": pd.to_numeric(closes, errors="coerce"),
            }
        ).dropna()
        if frame.empty:
            return pd.DataFrame(columns=["observation_date", label])
        frame["observation_date"] = frame["observation_date"].dt.to_period("M").dt.to_timestamp()
        frame = frame.sort_values("observation_date").drop_duplicates("observation_date", keep="last")
        frame[label] = frame["close"].pct_change(fill_method=None) * 100.0
        return frame[["observation_date", label]].dropna(subset=[label])
    except Exception:
        return pd.DataFrame(columns=["observation_date", label])


def build_hk_liquidity_figures(date_range: str, compact_mode: bool = False) -> list[go.Figure]:
    """Build four independent Hong Kong liquidity charts for the dashboard."""
    all_data = load_hk_liquidity()
    data = _slice_range(all_data, date_range)
    meta = snapshot_metadata()
    latest_text = meta.get("latest_observation") or "--"

    if data.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="HKMA snapshot unavailable · data pipeline needs refresh",
            x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False,
            font=dict(size=14),
        )
        fig.update_layout(height=420, template="plotly_white")
        return [fig]

    # Market overlays use monthly close-to-close percentage changes so they are
    # directly comparable with the monthly liquidity impulse in 5-1.
    hkex_change = _market_monthly_change("0388.HK", "HKEX Price Change")
    hstech_change = _market_monthly_change("HSTECH.HK", "HSTECH Change")
    market_data = data[["observation_date"]].copy()
    for frame in (hkex_change, hstech_change):
        if not frame.empty:
            market_data = market_data.merge(frame, on="observation_date", how="left")

    def add_line(
        fig: go.Figure,
        frame: pd.DataFrame,
        column: str,
        name: str,
        color: str,
        width: float = 2.3,
        dash: str | None = None,
        unit: str = "%",
        secondary_y: bool | None = None,
    ) -> None:
        if column not in frame.columns or frame[column].notna().sum() == 0:
            return
        line: dict[str, Any] = {"width": width, "color": color}
        if dash:
            line["dash"] = dash
        trace = go.Scatter(
            x=frame["observation_date"], y=frame[column], name=name, mode="lines",
            line=line, connectgaps=False,
            hovertemplate=f"{name}: %{{y:.3f}}{unit}<extra></extra>",
        )
        if secondary_y is None:
            fig.add_trace(trace)
        else:
            fig.add_trace(trace, secondary_y=secondary_y)

    def add_constant(
        fig: go.Figure,
        value: float,
        name: str,
        color: str,
        dash: str = "dot",
        width: float = 1.4,
        secondary_y: bool | None = None,
    ) -> None:
        trace = go.Scatter(
            x=data["observation_date"], y=[value] * len(data), name=name, mode="lines",
            line=dict(width=width, color=color, dash=dash), connectgaps=True,
            hovertemplate=f"{name}: %{{y:.3f}}<extra></extra>",
        )
        if secondary_y is None:
            fig.add_trace(trace)
        else:
            fig.add_trace(trace, secondary_y=secondary_y)

    def style(fig: go.Figure, title: str, height: int = 430, right_axis: bool = False) -> go.Figure:
        fig.update_layout(
            height=height,
            template="plotly_white",
            hovermode="x unified",
            dragmode=False,
            margin=dict(l=62, r=82 if right_axis else 28, t=96, b=44, pad=2),
            title=dict(text=f"{title} · latest {latest_text}", x=0.01, xanchor="left", font=dict(size=16)),
            legend=dict(
                orientation="h", yanchor="bottom", y=1.08, xanchor="left", x=0,
                font=dict(size=11), traceorder="normal", itemwidth=30,
                bgcolor="rgba(255,255,255,0)", itemclick="toggle", itemdoubleclick="toggleothers",
            ),
            hoverlabel=dict(bgcolor="white", font_size=11, bordercolor="#e5e7eb"),
            font=dict(size=12), plot_bgcolor="#ffffff", paper_bgcolor="#ffffff",
        )
        fig.update_xaxes(
            showgrid=True, gridcolor="#eef2f7", griddash="dot",
            showline=True, linecolor="#9ca3af", linewidth=1,
            fixedrange=True, tickformat="%Y-%m", tickfont=dict(size=11), automargin=False,
        )
        return fig

    # 5-1 · Money supply + Hong Kong equity market monthly changes.
    money = make_subplots(specs=[[{"secondary_y": True}]])
    add_line(money, data, "M2 MoM", "M2 MoM", COLORS["m2"], 2.8, secondary_y=False)
    add_line(money, data, "M3 MoM", "M3 MoM", COLORS["m3"], 2.3, "dash", secondary_y=False)
    add_line(money, data, "Monetary Base MoM", "Monetary Base MoM", COLORS["base"], 1.8, "dot", secondary_y=False)
    add_line(money, market_data, "HKEX Price Change", "HKEX Price Change (R)", "#0891b2", 2.1, secondary_y=True)
    add_line(money, market_data, "HSTECH Change", "HSTECH Change (R)", "#db2777", 2.1, "dash", secondary_y=True)
    money.update_yaxes(
        title_text="Money MoM (%)", secondary_y=False,
        showgrid=True, gridcolor="#e5e7eb", griddash="dot",
        zeroline=True, zerolinecolor="#cbd5e1", fixedrange=True,
    )
    money.update_yaxes(
        title_text="Market Change (%)", secondary_y=True,
        showgrid=False, zeroline=True, zerolinecolor="#cbd5e1", fixedrange=True,
    )
    style(money, "5-1. HK Money Supply & Market Pulse", right_axis=True)

    # 5-2 · Banking-system liquidity.
    balance = go.Figure()
    add_line(balance, data, "Aggregate Balance", "Aggregate Balance", COLORS["balance"], 2.8, unit=" HK$ bn")
    balance.update_yaxes(
        title_text="HK$ bn", showgrid=True, gridcolor="#e5e7eb", griddash="dot",
        zeroline=False, fixedrange=True,
    )
    style(balance, "5-2. Banking-system Liquidity")

    # 5-3 · HKD funding.
    funding = make_subplots(specs=[[{"secondary_y": True}]])
    add_line(funding, data, "HIBOR O/N", "O/N HIBOR", COLORS["on"], 2.0, secondary_y=False)
    add_line(funding, data, "HIBOR 3M", "3M HIBOR", COLORS["h3m"], 2.3, "dash", secondary_y=False)
    add_line(funding, data, "HKMA Base Rate", "HKMA Base Rate", COLORS["policy"], 2.0, "dot", secondary_y=False)
    add_line(funding, data, "O/N-3M Spread", "O/N−3M Spread (R)", COLORS["spread"], 1.7, "dashdot", " bp", secondary_y=True)
    funding.update_yaxes(
        title_text="Rate (%)", secondary_y=False,
        showgrid=True, gridcolor="#e5e7eb", griddash="dot",
        zeroline=True, zerolinecolor="#cbd5e1", fixedrange=True,
    )
    funding.update_yaxes(
        title_text="Spread (bp)", secondary_y=True,
        showgrid=False, zeroline=True, zerolinecolor="#cbd5e1", fixedrange=True,
    )
    style(funding, "5-3. HKD Funding", right_axis=True)

    # 5-4 · Convertibility band + market reaction.
    fx = make_subplots(specs=[[{"secondary_y": True}]])
    add_line(fx, data, "USD/HKD", "USD/HKD", COLORS["fx"], 2.6, unit="", secondary_y=False)
    add_constant(fx, 7.75, "Strong-side CU 7.75", COLORS["strong"], "dot", 1.4, secondary_y=False)
    add_constant(fx, 7.80, "Linked Rate Center 7.80", "#64748b", "dash", 1.5, secondary_y=False)
    add_constant(fx, 7.85, "Weak-side CU 7.85", COLORS["weak"], "dot", 1.4, secondary_y=False)
    add_line(fx, market_data, "HKEX Price Change", "HKEX Price Change (R)", "#0891b2", 2.1, secondary_y=True)
    add_line(fx, market_data, "HSTECH Change", "HSTECH Change (R)", "#db2777", 2.1, "dash", secondary_y=True)
    fx.add_hrect(
        y0=7.75, y1=7.85,
        fillcolor="rgba(148,163,184,0.10)",
        line_width=0, layer="below",
        annotation_text="7.75–7.85 LERS band",
        annotation_position="top left",
    )
    fx.update_yaxes(
        title_text="USD/HKD", secondary_y=False, range=[7.73, 7.87],
        showgrid=True, gridcolor="#e5e7eb", griddash="dot",
        zeroline=False, fixedrange=True,
    )
    fx.update_yaxes(
        title_text="Market Change (%)", secondary_y=True,
        showgrid=False, zeroline=True, zerolinecolor="#cbd5e1", fixedrange=True,
    )
    style(fx, "5-4. USD/HKD Convertibility Band & Market", height=450, right_axis=True)

    return [money, balance, funding, fx]
'''

hk = hk[:start] + new_builder + hk[end:]
HK.write_text(hk, encoding="utf-8")
print("hk_liquidity.py: market overlays + 7.80 center + LERS band added")

# ---------- app.py ----------
app = APP.read_text(encoding="utf-8")

app = app.replace(
    "from macro_platform.hk_liquidity import build_hk_liquidity_figure, build_hk_liquidity_figures, liquidity_status_html, load_hk_liquidity",
    "from macro_platform.hk_liquidity import build_hk_liquidity_figure, build_hk_liquidity_figures, load_hk_liquidity",
    1,
)

# Remove the summary strip from Chart 5 rendering.
app = app.replace("    st.markdown(liquidity_status_html(), unsafe_allow_html=True)\n", "", 1)

app = app.replace(
    '<div class="section-description">HKD M2/M3 MoM / Monetary Base MoM / Aggregate Balance / HIBOR / O/N−3M Spread (R) / USD-HKD / 7.75–7.85 CU</div>',
    '<div class="section-description">Money supply / HKEX & HSTECH monthly change / Aggregate Balance / HIBOR / USD-HKD / 7.75–7.85 LERS band</div>',
    1,
)

old_hk_desc_start = "HK_PARAMETER_DESCRIPTIONS = ["
desc_start = app.index(old_hk_desc_start)
desc_end = app.index("\n]\n\ndef show_hk_parameter_description", desc_start) + 2
new_desc = r'''HK_PARAMETER_DESCRIPTIONS = [
    '<b>参数概念：</b><br>1. HKD M2 MoM：港元 M2 月环比增速，用来观察广义港元货币的边际扩张或收缩。<br>2. HKD M3 MoM：港元 M3 月环比增速，统计口径较 M2 更广，用于交叉确认广义货币边际变化。<br>3. Monetary Base MoM：香港货币基础总量月环比变化。<br>4. HKEX Price Change（R）：港交所 0388.HK 月末收盘价相对上月的涨跌幅，右轴单位 %；用于观察香港市场交易活跃度与流动性环境的市场映射。<br>5. HSTECH Change（R）：恒生科技指数 HSTECH.HK 月度涨跌幅，右轴单位 %；用于观察高贝塔科技资产对香港流动性变化的反应。',
    '<b>参数概念：</b><br>1. Aggregate Balance：银行体系总结余，单位 HK$ billion；总结余下降通常代表银行体系可用港元流动性趋紧，上升则通常代表即时银行体系流动性较充裕。',
    '<b>参数概念：</b><br>1. O/N HIBOR：隔夜港元银行同业拆息，反映最短端港元资金价格。<br>2. 3M HIBOR：3 个月港元银行同业拆息，用来观察更持续的港元融资成本。<br>3. HKMA Base Rate：香港金管局基本利率，是港元利率体系的重要政策参考。<br>4. O/N−3M Spread（R）：隔夜 HIBOR 减 3M HIBOR，右轴单位 bp；显著转正通常代表短端资金压力上升。',
    '<b>参数概念：</b><br>1. USD/HKD：每 1 美元对应的港元价格；向 7.85 上升表示港元转弱，向 7.75 下降表示港元转强。<br>2. Strong-side CU 7.75：联系汇率制度下强方兑换保证。<br>3. Linked Rate Center 7.80：7.75–7.85 兑换保证区间的中点参考线，用于快速判断港元当前处在偏强侧还是偏弱侧；不是额外的兑换保证触发水平。<br>4. Weak-side CU 7.85：联系汇率制度下弱方兑换保证。<br>5. HKEX Price Change（R）：港交所 0388.HK 月度涨跌幅，右轴单位 %。<br>6. HSTECH Change（R）：恒生科技指数 HSTECH.HK 月度涨跌幅，右轴单位 %。<br><br><b>读取提示：</b>灰色淡色区域表示 7.75–7.85 联系汇率兑换保证区间；7.80 为区间中点参考。市场涨跌幅用于对照汇率位置与香港风险资产表现。',
]'''
app = app[:desc_start] + new_desc + app[desc_end:]

APP.write_text(app, encoding="utf-8")
print("app.py: summary removed and per-chart descriptions updated")
