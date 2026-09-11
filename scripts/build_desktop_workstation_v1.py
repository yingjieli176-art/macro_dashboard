from pathlib import Path
import re

APP = Path("app.py")
text = APP.read_text(encoding="utf-8")

# Desktop-only phase: remove the deferred desktop/mobile switch and its CSS.
text = re.sub(
    r'\n# Workstation view mode: desktop is the deliberate default; mobile is an\n.*?\n(?=def _load_watchlists\(\):)',
    '\n',
    text,
    count=1,
    flags=re.S,
)
text = text.replace('\n.view-mode-note { color:#9ca3af; font-size:.60rem; letter-spacing:.11em; text-align:right; margin:-4px 2px 4px; }', '')
text = text.replace('\n# compact_mode is selected by the workstation view switch above.\n', '\n')

# Restore desktop-only chart geometry after the abandoned switch experiment.
text = text.replace(
    'margin=dict(l=50 if compact_mode else 64, r=118 if compact_mode else 164, t=62 if compact_mode else 72, b=30 if compact_mode else 34, pad=2),\n        legend=dict(y=1.08 if compact_mode else 1.09, x=0.01),\n        xaxis=dict(domain=[0.0, 0.78 if compact_mode else 0.82]),',
    'margin=dict(l=64, r=164, t=72, b=34, pad=2),\n        legend=dict(y=1.09, x=0.01),\n        xaxis=dict(domain=[0.0, 0.82]),',
)
text = text.replace(
    'margin=dict(l=48 if compact_mode else 62, r=108 if compact_mode else 150, t=62 if compact_mode else 72, b=30 if compact_mode else 34, pad=2),\n            legend=dict(y=1.08 if compact_mode else 1.09, x=0.01),\n            xaxis=dict(domain=[0.0, 0.78 if compact_mode else 0.84]),',
    'margin=dict(l=62, r=150, t=72, b=34, pad=2),\n            legend=dict(y=1.09, x=0.01),\n            xaxis=dict(domain=[0.0, 0.84]),',
)
text = text.replace(
    'margin=dict(l=50 if compact_mode else 68, r=152 if compact_mode else 220, t=62 if compact_mode else 72, b=30 if compact_mode else 34, pad=2),\n        legend=dict(y=1.08 if compact_mode else 1.09, x=0.01),\n        xaxis=dict(domain=[0.0, 0.68 if compact_mode else 0.75]),',
    'margin=dict(l=68, r=220, t=72, b=34, pad=2),\n        legend=dict(y=1.09, x=0.01),\n        xaxis=dict(domain=[0.0, 0.75]),',
)

text = text.replace('st.set_page_config(page_title="Macro Dashboard", page_icon="📊", layout="wide")', 'st.set_page_config(page_title="Macro Workstation", page_icon="📊", layout="wide")', 1)
text = text.replace('<div class="dashboard-eyebrow">MACRO · LIQUIDITY · RATES</div>', '<div class="dashboard-eyebrow">GLOBAL MACRO · CROSS-ASSET · LIQUIDITY</div>', 1)
text = text.replace('<div class="dashboard-title">Macro Dashboard</div>', '<div class="dashboard-title">Macro Workstation</div>', 1)
text = text.replace('跨市场行情、利率、流动性与 7×24 财经信息面板', 'Rates · Liquidity · Risk · Cross-asset monitoring · 7×24 news', 1)

workstation_css = r'''

/* Desktop Workstation V1 */
.block-container {
    max-width: none !important;
    padding-top: .40rem !important;
    padding-left: 184px !important;
    padding-right: 324px !important;
    padding-bottom: 1.4rem !important;
}
html, body, [data-testid="stAppViewContainer"] { background:#f6f8fb !important; }
header[data-testid="stHeader"] { background:rgba(246,248,251,.94) !important; }
.dashboard-header {
    position: sticky; top: 0; z-index: 70;
    background: rgba(246,248,251,.96);
    backdrop-filter: blur(10px);
    padding: 5px 0 8px !important;
    margin-bottom: 5px !important;
    border-bottom: 1px solid #dbe2ea !important;
}
.dashboard-title { font-size:1.52rem !important; font-weight:720 !important; letter-spacing:-.025em !important; }
.dashboard-eyebrow { font-size:.60rem !important; letter-spacing:.16em !important; }
.dashboard-subtitle { font-size:.72rem !important; color:#7c8798 !important; }
.dashboard-links { display:none !important; }
.workstation-rail {
    position:fixed; left:0; top:0; bottom:0; width:164px; z-index:900;
    background:#0f172a; border-right:1px solid #1e293b;
    padding:62px 10px 16px; box-sizing:border-box;
}
.workstation-brand { color:#f8fafc; font-size:.90rem; font-weight:720; padding:0 10px 15px; letter-spacing:-.01em; }
.workstation-brand span { display:block; color:#64748b; font-size:.54rem; font-weight:650; letter-spacing:.16em; margin-top:3px; }
.workstation-nav { display:flex; flex-direction:column; gap:3px; }
.workstation-nav a {
    color:#94a3b8 !important; text-decoration:none !important; font-size:.72rem; font-weight:600;
    padding:8px 10px; border-radius:6px; border:1px solid transparent;
}
.workstation-nav a:hover { color:#f8fafc !important; background:#172033; border-color:#26344a; }
.workstation-nav .nav-group { color:#475569; font-size:.50rem; font-weight:750; letter-spacing:.15em; padding:13px 10px 4px; }
.workstation-rail-foot { position:absolute; left:12px; right:12px; bottom:15px; color:#475569; font-size:.54rem; line-height:1.45; }
.workspace-news-rail {
    position:fixed; right:0; top:0; bottom:0; width:304px; z-index:850;
    background:#ffffff; border-left:1px solid #dbe2ea;
    padding:60px 12px 14px; box-sizing:border-box; overflow-y:auto;
}
.news-rail-head { display:flex; justify-content:space-between; align-items:baseline; padding:0 3px 9px; border-bottom:1px solid #e5e7eb; }
.news-rail-title { color:#111827; font-size:.82rem; font-weight:720; }
.news-rail-live { color:#059669; font-size:.54rem; font-weight:700; letter-spacing:.10em; }
.news-rail-item { padding:9px 3px; border-bottom:1px solid #f0f2f5; }
.news-rail-time { color:#94a3b8; font-size:.56rem; font-family:"Segoe UI",sans-serif; margin-bottom:3px; }
.news-rail-text { color:#334155; font-size:.67rem; line-height:1.42; }
.news-rail-text a { color:#334155 !important; text-decoration:none !important; }
.news-rail-text a:hover { color:#0f172a !important; }
.news-rail-source { color:#94a3b8; font-size:.53rem; margin-top:4px; }
.command-shell { border:1px solid #dbe2ea; background:#fff; border-radius:7px; padding:6px 8px; margin:4px 0 7px; }
.command-label { color:#64748b; font-size:.54rem; font-weight:750; letter-spacing:.13em; margin-bottom:3px; }
.command-status { color:#64748b; font-size:.64rem; line-height:1.35; text-align:right; padding-top:5px; }
.command-status strong { color:#0f172a; font-weight:680; }
.signal-title { display:flex; align-items:center; justify-content:space-between; margin:2px 0 5px; }
.signal-title strong { color:#111827; font-size:.72rem; }
.signal-title span { color:#94a3b8; font-size:.54rem; letter-spacing:.08em; }
.signal-strip { display:grid; grid-template-columns:repeat(8,minmax(0,1fr)); gap:5px; margin:0 0 9px; }
.signal-card { background:#fff; border:1px solid #dbe2ea; border-radius:6px; padding:7px 8px 6px; min-width:0; }
.signal-name { color:#64748b; font-size:.54rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.signal-value { color:#0f172a; font-size:.84rem; font-weight:720; margin-top:2px; white-space:nowrap; }
.signal-delta { font-size:.56rem; margin-top:2px; white-space:nowrap; }
.signal-up { color:#059669; } .signal-down { color:#dc2626; } .signal-flat { color:#94a3b8; }
.signal-meta { color:#a1aab8; font-size:.48rem; margin-top:2px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.section-kicker { font-size:.55rem !important; letter-spacing:.14em !important; margin-top:.20rem !important; }
.section-title { font-size:1.03rem !important; min-height:22px !important; margin-top:.22rem !important; }
.section-description { font-size:.70rem !important; min-height:15px !important; margin-bottom:.10rem !important; }
.market-groups { gap:5px !important; margin-bottom:.35rem !important; }
.market-group { border-radius:7px !important; padding:7px 8px 6px !important; box-shadow:none !important; }
.market-group-title { font-size:.72rem !important; margin-bottom:4px !important; }
.market-item { height:60px !important; min-height:60px !important; max-height:60px !important; }
.market-name { font-size:.64rem !important; }.market-price { font-size:.86rem !important; }.market-change { font-size:.64rem !important; }.market-meta { font-size:.54rem !important; }
.watch-market-title { font-size:.76rem !important; }.watch-card-name { font-size:.74rem !important; }.watch-price { font-size:.94rem !important; }
.watch-session,.watch-meta,.watch-toolbar { font-size:.60rem !important; }
div[data-testid="stVerticalBlockBorderWrapper"] { border-color:#dbe2ea !important; border-radius:7px !important; background:#fff !important; }
div[data-testid="stPlotlyChart"] { border:0 !important; border-radius:6px !important; padding:0 !important; background:#fff !important; }
.work-card-kicker { color:#94a3b8; font-size:.51rem; font-weight:750; letter-spacing:.12em; margin-bottom:2px; }
.work-card-title { color:#111827; font-size:.84rem; font-weight:720; line-height:1.25; }
.work-card-subtitle { color:#7c8798; font-size:.60rem; margin-top:2px; margin-bottom:2px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
div[data-testid="stExpander"] { border-color:#edf0f4 !important; background:#fbfcfd !important; }
div[data-testid="stExpander"] summary { font-size:.62rem !important; color:#64748b !important; }
.mini-description { font-size:.63rem !important; line-height:1.38 !important; color:#64748b !important; }
.source-text { font-size:.56rem !important; line-height:1.35 !important; }
.chart-divider { margin:.10rem 0 .26rem !important; }
@media (max-width: 1440px) {
    .block-container { padding-left:172px !important; padding-right:286px !important; }
    .workstation-rail { width:154px; }
    .workspace-news-rail { width:270px; }
    .signal-strip { grid-template-columns:repeat(4,minmax(0,1fr)); }
}
'''

if '/* Desktop Workstation V1 */' not in text:
    text = text.replace('\n</style>\n""", unsafe_allow_html=True)', workstation_css + '\n</style>\n""", unsafe_allow_html=True)', 1)

# Replace the abandoned view switch location with a desktop command bar + fixed navigation rail.
command_block = r'''

compact_mode = False

st.markdown(
    """
    <aside class="workstation-rail">
      <div class="workstation-brand">Macro Workstation<span>DESKTOP TERMINAL</span></div>
      <nav class="workstation-nav">
        <a href="#market-overview">Overview</a>
        <a href="#watchlist">Watchlist</a>
        <div class="nav-group">MACRO</div>
        <a href="#rates">Rates</a>
        <a href="#us-liquidity">US Liquidity</a>
        <a href="#hk-liquidity">HK Liquidity</a>
        <a href="#volatility">Volatility</a>
        <a href="#metals">Metals</a>
        <div class="nav-group">FLOW</div>
        <a href="#news">7×24 News</a>
      </nav>
      <div class="workstation-rail-foot">Macro Workstation v1<br>Data for monitoring only</div>
    </aside>
    """,
    unsafe_allow_html=True,
)

_cmd_left, _cmd_range, _cmd_status = st.columns([2.6, 4.8, 2.6], vertical_alignment="center")
with _cmd_left:
    st.markdown('<div class="command-shell"><div class="command-label">WORKSPACE</div><div style="font-size:.72rem;font-weight:680;color:#111827;">Market Overview</div></div>', unsafe_allow_html=True)
with _cmd_range:
    st.markdown('<div class="command-label">GLOBAL RANGE</div>', unsafe_allow_html=True)
    workspace_range = st.radio(
        "全局时间范围",
        ["1M", "3M", "6M", "1Y", "5Y"],
        horizontal=True,
        index=3,
        key="workspace_global_range",
        label_visibility="collapsed",
    )
with _cmd_status:
    _now_hkt = datetime.now(DASHBOARD_TZ).strftime("%m-%d %H:%M HKT")
    st.markdown(f'<div class="command-status"><strong>● DATA LIVE</strong><br>Refresh · {_now_hkt}</div>', unsafe_allow_html=True)
'''

if 'DESKTOP TERMINAL' not in text:
    anchor = '\ndef _load_watchlists():'
    if anchor not in text:
        raise RuntimeError('command bar anchor not found')
    text = text.replace(anchor, command_block + anchor, 1)

# Compact top signal strip. It reuses current source functions and never changes
# the chart calculation paths.
signal_block = r'''

def _signal_last(frame, column, divisor=1.0):
    try:
        data = frame.copy()
        data["observation_date"] = pd.to_datetime(data["observation_date"], errors="coerce")
        data[column] = pd.to_numeric(data[column], errors="coerce") / divisor
        data = data.dropna(subset=["observation_date", column]).sort_values("observation_date")
        if data.empty:
            return None, None, ""
        value = float(data[column].iloc[-1])
        previous = float(data[column].iloc[-2]) if len(data) > 1 else None
        stamp = data["observation_date"].iloc[-1].strftime("%m-%d")
        return value, previous, stamp
    except Exception:
        return None, None, ""


def _signal_card(name, value, delta, meta, value_fmt="{:.2f}", delta_fmt="{:+.2f}", suffix=""):
    value_text = "--" if value is None else value_fmt.format(value) + suffix
    if delta is None:
        delta_text, cls = "--", "signal-flat"
    else:
        delta_text = delta_fmt.format(delta)
        cls = "signal-up" if delta > 0 else ("signal-down" if delta < 0 else "signal-flat")
    return (
        '<div class="signal-card">'
        f'<div class="signal-name">{html.escape(name)}</div>'
        f'<div class="signal-value">{html.escape(value_text)}</div>'
        f'<div class="signal-delta {cls}">{html.escape(delta_text)}</div>'
        f'<div class="signal-meta">{html.escape(meta)}</div>'
        '</div>'
    )


def render_signal_strip():
    cards = []

    effr, effr_prev, effr_date = _signal_last(get_effr(), "EFFR")
    effr_bp = None if effr is None or effr_prev is None else (effr - effr_prev) * 100.0
    cards.append(_signal_card("EFFR", effr, effr_bp, f"FRED · {effr_date}", "{:.2f}", "{:+.1f} bp", "%"))

    d10, d10_prev, d10_date = _signal_last(get_dgs10(), "DGS10")
    d10_bp = None if d10 is None or d10_prev is None else (d10 - d10_prev) * 100.0
    cards.append(_signal_card("US 10Y", d10, d10_bp, f"FRED · {d10_date}", "{:.2f}", "{:+.1f} bp", "%"))

    d2, d2_prev, _ = _signal_last(get_dgs2(), "DGS2")
    curve = None if d10 is None or d2 is None else (d10 - d2) * 100.0
    curve_prev = None if d10_prev is None or d2_prev is None else (d10_prev - d2_prev) * 100.0
    curve_delta = None if curve is None or curve_prev is None else curve - curve_prev
    cards.append(_signal_card("10Y−2Y", curve, curve_delta, f"curve · {d10_date}", "{:.0f}", "{:+.1f} bp", " bp"))

    walcl, _, walcl_date = _signal_last(get_walcl(), "WALCL", 1_000_000.0)
    tga, _, tga_date = _signal_last(get_tga_daily(), "TGA_DAILY")
    rrp, _, rrp_date = _signal_last(get_rrp_daily(), "RRPONTSYD", 1_000.0)
    net = None if any(v is None for v in (walcl, tga, rrp)) else walcl - tga - rrp
    cards.append(_signal_card("Net Liquidity", net, None, f"WALCL/TGA/RRP · {max(walcl_date, tga_date, rrp_date)}", "{:.2f}", "{:+.2f}", "T"))

    refresh_key = _quote_refresh_key()
    for signal_name, symbol, market in (("S&P 500", "^GSPC", "US"), ("Nasdaq", "^IXIC", "US"), ("HSI", "^HSI", "HK")):
        row = _stable_quote(symbol, refresh_key)
        price, change = _active_quote_values(row, market)
        cards.append(_signal_card(signal_name, price, change, _market_state_text(row, market), "{:,.0f}", "{:+.2f}%", ""))

    vix, vix_prev, vix_date = _signal_last(_fred_series("VIXCLS"), "VIXCLS")
    vix_delta = None if vix is None or vix_prev is None else vix - vix_prev
    cards.append(_signal_card("VIX", vix, vix_delta, f"FRED · {vix_date}", "{:.1f}", "{:+.1f}", ""))

    st.markdown('<div class="signal-title"><strong>Live Signals</strong><span>RATES · LIQUIDITY · RISK · EQUITY</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="signal-strip">' + ''.join(cards) + '</div>', unsafe_allow_html=True)


render_signal_strip()
'''

if 'def render_signal_strip():' not in text:
    anchor = 'st.markdown(\'<div id="market-overview" class="section-anchor"></div><div class="section-kicker">MARKET OVERVIEW</div>\', unsafe_allow_html=True)'
    if anchor not in text:
        raise RuntimeError('market overview anchor not found')
    text = text.replace(anchor, signal_block + '\n' + anchor, 1)

# Replace the long report-like macro stack with a 2-column desktop workspace.
new_render = r'''def render_core_charts():
    def render_card(col, kicker, title, subtitle, figure, description_html, sources, height=360):
        with col:
            with st.container(border=True):
                st.markdown(
                    f'<div class="work-card-kicker">{kicker}</div>'
                    f'<div class="work-card-title">{title}</div>'
                    f'<div class="work-card-subtitle">{subtitle}</div>',
                    unsafe_allow_html=True,
                )
                figure.update_layout(height=height)
                st.plotly_chart(figure, use_container_width=True, config=PLOTLY_CONFIG)
                with st.expander("Methodology · Sources"):
                    st.markdown(f'<div class="mini-description">{description_html}</div>', unsafe_allow_html=True)
                    add_sources(sources)

    st.markdown('<div id="rates" class="section-anchor"></div><div class="section-kicker">RATES WORKSPACE</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">US Rates & Policy</div><div class="section-description">Global range applies to all workstation charts · use legend to isolate individual series</div>', unsafe_allow_html=True)

    row1 = st.columns(2, gap="small")
    render_card(
        row1[0], "RATES · 01", "Fed Policy & Money Market", "IORB · ON RRP Rate · EFFR · SOFR",
        build_fig1(workspace_range), PARAM_DESCRIPTIONS[0],
        [("IORB", "https://fred.stlouisfed.org/series/IORB"), ("ON RRP Rate", "https://fred.stlouisfed.org/series/RRPONTSYAWARD"), ("EFFR", "https://fred.stlouisfed.org/series/EFFR"), ("SOFR", "https://fred.stlouisfed.org/series/SOFR")],
    )
    render_card(
        row1[1], "RATES · 02", "10Y Yield Structure", "Nominal · Real · Breakeven",
        build_fig2(workspace_range), PARAM_DESCRIPTIONS[1],
        [("10Y Nominal", "https://fred.stlouisfed.org/series/DGS10"), ("10Y Real", "https://fred.stlouisfed.org/series/DFII10"), ("10Y Breakeven", "https://fred.stlouisfed.org/series/T10YIE")],
    )

    row2 = st.columns(2, gap="small")
    render_card(
        row2[0], "CURVE · 03", "Treasury Curve", "3M · 2Y · 10Y · 10Y−2Y · 10Y−3M",
        build_fig3(workspace_range), PARAM_DESCRIPTIONS[2],
        [("3M Treasury", "https://fred.stlouisfed.org/series/DGS3MO"), ("2Y Treasury", "https://fred.stlouisfed.org/series/DGS2"), ("10Y Treasury", "https://fred.stlouisfed.org/series/DGS10")],
    )
    st.markdown('<div id="us-liquidity" class="section-anchor"></div>', unsafe_allow_html=True)
    render_card(
        row2[1], "LIQUIDITY · 04", "US Liquidity", "Net Liquidity (L) · Reserve / TGA (R1) · ON RRP (R2)",
        build_fig4(workspace_range), PARAM_DESCRIPTIONS[3],
        [("Fed Total Assets", "https://fred.stlouisfed.org/series/WALCL"), ("Reserve Balances", "https://fred.stlouisfed.org/series/WRESBAL"), ("TGA · Daily Treasury Statement", "https://fiscaldata.treasury.gov/datasets/daily-treasury-statement/operating-cash-balance"), ("ON RRP Balance", "https://fred.stlouisfed.org/series/RRPONTSYD")],
        height=375,
    )

    st.markdown('<div id="hk-liquidity" class="section-anchor"></div><div class="section-kicker">HONG KONG WORKSPACE</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">HK Liquidity & Funding</div><div class="section-description">Money supply · banking-system liquidity · HIBOR · linked-exchange-rate pressure</div>', unsafe_allow_html=True)

    hk5_mode = st.segmented_control("HK Market Display", ["Raw", "Rebased 100"], default="Raw", key="workstation_hk5_mode", label_visibility="collapsed") or "Raw"
    hk8_mode = st.session_state.get("workstation_hk8_mode", "Raw")
    hk_raw = build_fig5(workspace_range, market_mode="Raw")
    hk5 = build_fig5(workspace_range, market_mode=hk5_mode)[0] if hk5_mode != "Raw" else hk_raw[0]

    row3 = st.columns(2, gap="small")
    render_card(
        row3[0], "HK · 05", "Money Supply & Market Pulse", f"M2 trend · market overlay · {hk5_mode}",
        hk5, HK_PARAMETER_DESCRIPTIONS[0],
        [("HKMA Monetary Statistics", "https://apidocs.hkma.gov.hk/documentation/market-data-and-statistics/monthly-statistical-bulletin/financial/monetary-statistics/"), ("Hang Seng Indexes", "https://www.hsi.com.hk/eng/indexes/all-indexes/hstech"), ("Yahoo Finance", "https://finance.yahoo.com/")],
        height=375,
    )
    render_card(
        row3[1], "HK · 06", "Banking-system Liquidity", "Aggregate Balance · EFBN",
        hk_raw[1], HK_PARAMETER_DESCRIPTIONS[1],
        [("HKMA Monetary Base", "https://apidocs.hkma.gov.hk/documentation/market-data-and-statistics/monthly-statistical-bulletin/monetary-operation/monetary-base-endperiod/"), ("HKMA Daily Interbank Liquidity", "https://apidocs.hkma.gov.hk/documentation/market-data-and-statistics/daily-monetary-statistics/daily-figures-interbank-liquidity/")],
    )

    row4 = st.columns(2, gap="small")
    render_card(
        row4[0], "HK · 07", "HKD Funding", "O/N HIBOR · 3M HIBOR · Base Rate · spread",
        hk_raw[2], HK_PARAMETER_DESCRIPTIONS[2],
        [("HKMA Open API", "https://apidocs.hkma.gov.hk/"), ("HKMA Base Rate", "https://apidocs.hkma.gov.hk/documentation/market-data-and-statistics/monthly-statistical-bulletin/monetary-operation/disc-win-liquid-adj-win-rates-endperiod/")],
    )
    with row4[1]:
        hk8_mode = st.segmented_control("USD/HKD Market Display", ["Raw", "Rebased 100"], default="Raw", key="workstation_hk8_mode", label_visibility="collapsed") or "Raw"
    hk8 = build_fig5(workspace_range, market_mode=hk8_mode)[3] if hk8_mode != "Raw" else hk_raw[3]
    render_card(
        row4[1], "HK · 08", "USD/HKD Convertibility Band", f"7.75–7.85 band · market overlay · {hk8_mode}",
        hk8, HK_PARAMETER_DESCRIPTIONS[3],
        [("HKMA Linked Exchange Rate System", "https://www.hkma.gov.hk/eng/key-functions/money/linked-exchange-rate-system/"), ("Yahoo Finance", "https://finance.yahoo.com/"), ("Hang Seng Indexes", "https://www.hsi.com.hk/eng/indexes/all-indexes/hsi")],
        height=375,
    )

    st.markdown('<div id="volatility" class="section-anchor"></div><div class="section-kicker">CROSS-ASSET RISK</div>', unsafe_allow_html=True)
    row5 = st.columns(2, gap="small")
    render_card(
        row5[0], "RISK · 09", "US Equity Volatility", "VIX · VIXEQ · S&P 500 · VIX term spread",
        build_fig9(workspace_range), US_EQUITY_RISK_DESCRIPTION,
        [("Cboe VIX", "https://www.cboe.com/tradable-products/vix/"), ("Cboe VIXEQ / Dispersion", "https://www.cboe.com/us/indices/dispersion/"), ("FRED VIX3M", "https://fred.stlouisfed.org/series/VXVCLS"), ("FRED S&P 500", "https://fred.stlouisfed.org/series/SP500")],
        height=380,
    )
    with row5[1]:
        st.markdown('<div id="metals" class="section-anchor"></div>', unsafe_allow_html=True)
        metals_mode = st.segmented_control("Metals Display", ["Rebased 100", "Raw"], default="Rebased 100", key="workstation_metals_mode", label_visibility="collapsed") or "Rebased 100"
    render_card(
        row5[1], "METALS · 10", "Precious Metals", f"Gold · Silver · Gold/Silver · GVZ · {metals_mode}",
        build_fig10(workspace_range, metals_mode), PRECIOUS_METALS_DESCRIPTION,
        [("Yahoo Gold Futures", "https://finance.yahoo.com/quote/GC=F/history/"), ("Yahoo Silver Futures", "https://finance.yahoo.com/quote/SI=F/history/"), ("FRED GVZ", "https://fred.stlouisfed.org/series/GVZCLS")],
        height=380,
    )
'''

pattern = r'def render_core_charts\(\):\n.*?(?=st\.markdown\(\'<div id="macro-charts")'
text, count = re.subn(pattern, new_render + '\n', text, count=1, flags=re.S)
if count != 1:
    raise RuntimeError(f'render_core_charts replacement count={count}')

# Keep the existing macro anchor but make it a terse workspace divider.
text = text.replace(
    'st.markdown(\'<div id="macro-charts" class="section-anchor"></div><div class="section-kicker">MACRO CHARTS</div>\', unsafe_allow_html=True)\nrender_core_charts()\nst.markdown(\'<div class="chart-divider"></div>\', unsafe_allow_html=True)',
    'st.markdown(\'<div id="macro-charts" class="section-anchor"></div>\', unsafe_allow_html=True)\nrender_core_charts()',
    1,
)

# Replace the report-style bottom news section with an always-visible desktop rail.
news_rail = r'''st.markdown('<div id="news" class="section-anchor"></div>', unsafe_allow_html=True)

@st.fragment(run_every="60s")
def render_news_rail():
    news_items, news_error = get_sina_news(limit=18)
    chunks = [
        '<aside class="workspace-news-rail">',
        '<div class="news-rail-head"><div class="news-rail-title">7×24 News</div><div class="news-rail-live">● LIVE</div></div>',
    ]
    if news_items:
        for item in news_items:
            news_time = html.escape(str(item.get("time", "")))
            news_title = html.escape(str(item.get("title", "")))
            news_content = html.escape(str(item.get("content", "")))
            news_url = html.escape(str(item.get("url", EASTMONEY_FOCUS_URL)), quote=True)
            if not news_url.startswith(("http://", "https://")):
                news_url = EASTMONEY_FOCUS_URL
            body = news_title or news_content
            if news_title and news_content and news_title != news_content:
                body = f'<strong>{news_title}</strong><br>{news_content}'
            chunks.append(
                '<div class="news-rail-item">'
                f'<div class="news-rail-time">{news_time}</div>'
                f'<div class="news-rail-text"><a href="{news_url}" target="_blank" rel="noopener noreferrer">{body}</a></div>'
                '<div class="news-rail-source">Eastmoney Focus</div>'
                '</div>'
            )
    else:
        chunks.append(f'<div class="news-rail-item"><div class="news-rail-text">News temporarily unavailable{": " + html.escape(str(news_error)) if news_error else ""}</div></div>')
    chunks.append('</aside>')
    st.markdown(''.join(chunks), unsafe_allow_html=True)


render_news_rail()
st.markdown('<div class="source-text" style="margin-top:10px;">Macro Workstation · data for monitoring and research, not investment advice.</div>', unsafe_allow_html=True)
'''

news_pattern = r'st\.markdown\(\'<div id="news" class="section-anchor"></div><div class="section-kicker">NEWS</div>\'.*\Z'
text, count = re.subn(news_pattern, news_rail, text, count=1, flags=re.S)
if count != 1:
    raise RuntimeError(f'news section replacement count={count}')

# Market overview/watchlist headings become terse workstation labels.
text = text.replace('<div class="section-kicker">MARKET OVERVIEW</div>', '<div class="section-kicker">MARKET TAPE</div>', 1)
text = text.replace('<div class="section-title">市场概览</div><div class="section-description">美股、港股与 A 股主要指数 · 报价时间来自行情源 · 交易状态按市场时段与报价日期判定 · 60 秒刷新</div>', '<div class="section-title">Market Overview</div><div class="section-description">US · Hong Kong · China major-index tape · 60-second quote refresh</div>', 1)
text = text.replace('<div class="section-title">自选观察</div><div class="section-description">核心标的快速监控 · 港/A/美股正常盘优先低延时多源行情 · Yahoo 仅备用或美股扩展时段 · 60 秒自动刷新</div>', '<div class="section-title">Watchlist</div><div class="section-description">Cross-market instruments · multi-source quotes · 60-second refresh</div>', 1)

APP.write_text(text, encoding="utf-8")
print("Desktop Workstation V1 applied; no mobile switch included.")
