import html

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

from data import (
    get_dgs3mo,
    get_dgs2,
    get_dgs10,
    get_dfii10,
    get_sofr,
    get_iorb,
    get_effr,
    get_rrp_rate,
    get_sina_news,
    get_market_snapshot,
)

st.set_page_config(page_title="Macro Dashboard", page_icon="📊", layout="wide")

EASTMONEY_FOCUS_URL = "https://kuaixun.eastmoney.com/"
RANGES = ["5Y", "1Y", "6M", "3M", "1M"]
PLOTLY_CONFIG = {
    "displayModeBar": False,
    "scrollZoom": False,
    "doubleClick": False,
    "editable": False,
    "displaylogo": False,
}

st.markdown(
    """
    <style>
    .block-container { padding-top: 1.5rem; padding-bottom: 3rem; max-width: 1400px; }
    html, body, [class*="css"] { font-family: "Noto Sans TC", "Noto Sans CJK TC", "Microsoft JhengHei", "PingFang TC", "Segoe UI", sans-serif; }
    .dashboard-title { font-size: 2rem; font-weight: 700; letter-spacing: -0.02em; margin-bottom: 0.15rem; }
    .dashboard-subtitle { color: #6b7280; font-size: 0.95rem; margin-bottom: 0.8rem; }
    .section-title { font-size: 1.35rem; font-weight: 650; letter-spacing: -0.01em; margin-top: 0.8rem; margin-bottom: 0.15rem; }
    .section-description { color: #6b7280; font-size: 0.88rem; margin-bottom: 0.4rem; }
    .mini-description { color: #6b7280; font-size: 0.78rem; line-height: 1.5; margin: 2px 0 8px; }
    .source-text { color: #6b7280; font-size: 0.76rem; margin: 3px 0 12px; line-height: 1.5; }
    .source-text a { color: #6b7280; text-decoration: none !important; white-space: nowrap; }
    .source-text a:hover { color: #374151; text-decoration: underline !important; }
    .source-sep { color: #d1d5db; margin: 0 5px; }
    .chart-divider { margin: 1rem 0 1.5rem; border-top: 1px solid #e5e7eb; }
    .compact-title { font-size: 1rem; font-weight: 650; margin-bottom: 0.2rem; }
    .compact-description { color: #6b7280; font-size: 0.75rem; line-height: 1.4; margin-bottom: 0.25rem; }
    .news-status { color: #6b7280; font-size: 0.75rem; margin-bottom: 0.5rem; }
    .news-box { border: 1px solid #e5e7eb; border-radius: 8px; padding: 6px 10px; background: #ffffff; max-height: 650px; overflow-y: auto; }
    .news-item { display: flex; align-items: flex-start; padding: 8px 3px; border-bottom: 1px solid #eeeeee; line-height: 1.5; font-size: 0.84rem; }
    .news-item:last-child { border-bottom: none; }
    .news-index { flex: 0 0 32px; width: 32px; color: #9ca3af; font-size: 0.72rem; font-family: "Segoe UI", sans-serif; padding-top: 2px; }
    .news-time { flex: 0 0 72px; width: 72px; color: #6b7280; font-size: 0.72rem; white-space: nowrap; padding-top: 2px; margin-right: 6px; }
    .news-content { flex: 1; min-width: 0; }
    .news-content a { color: #374151; text-decoration: none !important; }
    .news-content a:hover { color: #111827; text-decoration: none !important; }
    .market-box { border: 1px solid #e5e7eb; border-radius: 8px; padding: 7px 10px 6px; margin-bottom: 0.7rem; background: #ffffff; }
    .market-title { font-size: 0.78rem; font-weight: 650; color: #374151; margin-bottom: 5px; }
    .market-row { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 6px; }
    .market-row.after-hours-row { grid-template-columns: repeat(2, minmax(0, 1fr)); max-width: 40%; }
    .market-row + .market-row { margin-top: 5px; padding-top: 5px; border-top: 1px solid #f3f4f6; }
    .market-item { min-width: 0; padding-right: 5px; border-right: 1px solid #f0f0f0; }
    .market-item:last-child { border-right: none; }
    .market-name { color: #6b7280; font-size: 0.68rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .market-price { color: #111827; font-size: 0.86rem; font-weight: 650; margin-top: 1px; white-space: nowrap; }
    .market-change { font-size: 0.68rem; white-space: nowrap; }
    .market-meta { color: #9ca3af; font-size: 0.61rem; margin-top: 2px; white-space: nowrap; }
    .market-note { color: #9ca3af; font-size: 0.62rem; margin-top: 5px; line-height: 1.55; }
    .market-note-line + .market-note-line { margin-top: 2px; }
    .market-groups { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin-bottom: 0.7rem; }
    .market-group { border: 1px solid #e5e7eb; border-radius: 8px; padding: 7px 9px 6px; background: #fff; min-width: 0; }
    .market-group-title { color: #374151; font-size: 0.76rem; font-weight: 650; margin-bottom: 5px; }
    .market-group-row { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 5px; }
    .market-group-row.two { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    @media (max-width: 900px) { .market-row { grid-template-columns: repeat(3, minmax(0, 1fr)); } .market-row.after-hours-row { max-width: 100%; } .market-groups { grid-template-columns: 1fr; } }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="dashboard-title">Macro Dashboard</div>', unsafe_allow_html=True)
st.markdown('<div class="dashboard-subtitle">US monetary policy, Treasury yields and inflation expectations</div>', unsafe_allow_html=True)

compact_mode = st.toggle("缩小图表 / 快速浏览", value=True, help="开启后，三个核心图表横向并排显示。")


def _get_after_hours_quote(symbol):
    response = requests.get(
        "https://query1.finance.yahoo.com/v8/finance/chart/" + symbol,
        params={"range": "5d", "interval": "5m", "includePrePost": "true"},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=10,
    )
    response.raise_for_status()
    result = (response.json().get("chart", {}).get("result") or [])[0]
    meta = result.get("meta", {})
    timestamps = result.get("timestamp") or []
    closes = ((result.get("indicators", {}).get("quote") or [{}])[0]).get("close") or []
    post_period = (meta.get("currentTradingPeriod") or {}).get("post") or {}
    post_start = post_period.get("start")
    post_end = post_period.get("end")
    post_values = []
    for timestamp, close in zip(timestamps, closes):
        if close is None:
            continue
        if post_start is not None and timestamp < post_start:
            continue
        if post_end is not None and timestamp > post_end:
            continue
        post_values.append(close)
    price = post_values[-1] if post_values else meta.get("postMarketPrice")
    regular_price = meta.get("regularMarketPrice")
    if price is None:
        raise RuntimeError("没有取得盘后成交价")
    change_pct = None if regular_price in (None, 0) else (price - regular_price) / regular_price * 100
    return price, change_pct


def _get_yahoo_quote_safe(symbol):
    try:
        response = requests.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/" + symbol,
            params={"range": "1d", "interval": "1m", "includePrePost": "true"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        response.raise_for_status()
        result = (response.json().get("chart", {}).get("result") or [])[0]
        meta = result.get("meta", {})
        price = meta.get("regularMarketPrice")
        previous = meta.get("previousClose")
        if price is None:
            closes = ((result.get("indicators", {}).get("quote") or [{}])[0]).get("close") or []
            values = [v for v in closes if v is not None]
            price = values[-1] if values else None
        change_pct = None if price is None or previous in (None, 0) else (price - previous) / previous * 100
        return {"price": price, "change_pct": change_pct, "market_state": meta.get("marketState", ""), "currency": meta.get("currency", "")}
    except Exception as exc:
        return {"price": None, "change_pct": None, "market_state": "", "currency": "", "error": str(exc)}


def _render_market_item(name, row, meta=""):
    price = row.get("price")
    change_pct = row.get("change_pct")
    price_text = "--" if price is None else f"{price:,.2f}"
    change_text = "数据暂缺" if price is None else ("--" if change_pct is None else f"{change_pct:+.2f}%")
    return (
        f'<div class="market-item"><div class="market-name">{html.escape(name)}</div>'
        f'<div class="market-price">{html.escape(price_text)}</div>'
        f'<div class="market-change">{html.escape(change_text)}</div>'
        f'<div class="market-meta">{html.escape(meta)}</div></div>'
    )


@st.fragment(run_every="60s")
def render_market_snapshot():
    rows = get_market_snapshot()
    by_name = {row.get("name"): row for row in rows}
    nvda = _get_yahoo_quote_safe("NVDA")
    regular_items = []
    for name in ["纳斯达克", "标普500", "上证指数", "深证成指"]:
        row = by_name.get(name, {})
        state = row.get("market_state") or ""
        meta = {"REGULAR": "交易中", "PRE": "盘前", "POST": "盘后"}.get(state, "")
        regular_items.append(_render_market_item(name, row, meta))
    regular_items.append(_render_market_item("英伟达", nvda, {"REGULAR": "交易中", "PRE": "盘前", "POST": "盘后"}.get(nvda.get("market_state", ""), "")))
    after_hours = []
    for name, symbol, label in [("纳指夜盘", "QQQ", "QQQ 盘后"), ("标普夜盘", "SPY", "SPY 盘后")]:
        try:
            price, change_pct = _get_after_hours_quote(symbol)
            after_hours.append(_render_market_item(name, {"price": price, "change_pct": change_pct}, label))
        except Exception:
            after_hours.append(_render_market_item(name, {}, label))
    st.markdown(
        '<div class="market-box"><div class="market-title">🌐 全球核心市场 · 实时/近实时</div>'
        '<div class="market-row">' + "".join(regular_items) + '</div>'
        '<div class="market-row after-hours-row">' + "".join(after_hours) + '</div>'
        '<div class="market-note"><div class="market-note-line">每60秒刷新 · 第一排为核心指数盘中/最新收盘价。</div>'
        '<div class="market-note-line">第二排仅显示美股盘后价格：纳指参考 QQQ、标普参考 SPY；不使用 NQ / ES 期货。</div></div></div>',
        unsafe_allow_html=True,
    )


def _market_state_text(row):
    return {"REGULAR": "交易中", "PRE": "盘前", "POST": "盘后"}.get(row.get("market_state") or "", "")


@st.fragment(run_every="60s")
def render_market_groups():
    us_symbols = [("纳斯达克", "^IXIC"), ("标普500", "^GSPC"), ("道琼斯", "^DJI")]
    hk_symbols = [("恒生指数", "^HSI"), ("恒生科技", "^HSTECH")]
    cn_symbols = [("上证指数", "000001.SS"), ("深证成指", "399001.SZ"), ("沪深300", "000300.SS")]

    groups = [("🇺🇸 美股", us_symbols), ("🇭🇰 港股", hk_symbols), ("🇨🇳 A股", cn_symbols)]
    html_groups = []
    for title, symbols in groups:
        items = []
        for name, symbol in symbols:
            row = _get_yahoo_quote_safe(symbol)
            items.append(_render_market_item(name, row, _market_state_text(row)))
        two_class = " two" if len(symbols) == 2 else ""
        html_groups.append(
            f'<div class="market-group"><div class="market-group-title">{title}</div>'
            f'<div class="market-group-row{two_class}">' + "".join(items) + '</div></div>'
        )
    st.markdown('<div class="market-groups">' + "".join(html_groups) + '</div>', unsafe_allow_html=True)


render_market_snapshot()
render_market_groups()


def get_start_date(range_name):
    today = pd.Timestamp.today().normalize()
    offsets = {"5Y": pd.DateOffset(years=5), "1Y": pd.DateOffset(years=1), "6M": pd.DateOffset(months=6), "3M": pd.DateOffset(months=3), "1M": pd.DateOffset(months=1)}
    return today - offsets.get(range_name, pd.DateOffset(years=1))


def filter_range(data, date_range):
    return data[data["observation_date"] >= get_start_date(date_range)]


def add_sources(sources):
    links = []
    for text, url in sources:
        safe_text = html.escape(text)
        safe_url = html.escape(url, quote=True)
        links.append(f'<a href="{safe_url}" target="_blank" rel="noopener noreferrer">{safe_text}</a>')
    st.markdown('<div class="source-text">Source: ' + '<span class="source-sep">|</span>'.join(links) + '</div>', unsafe_allow_html=True)


def add_line(fig, data, column, name, width=2.5, dash=None, yaxis=None, unit="%"):
    line = {"width": width}
    if dash:
        line["dash"] = dash
    trace = go.Scatter(x=data["observation_date"], y=data[column], name=name, mode="lines", line=line, hovertemplate=f"{name}: %{{y:.3f}}{unit}<extra></extra>")
    if yaxis:
        trace.update(yaxis=yaxis)
    fig.add_trace(trace)


def apply_chart_style(fig, height):
    fig.update_layout(height=height, template="plotly_white", hovermode="x unified", dragmode=False, margin=dict(l=35, r=35, t=30, b=35), legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0, font=dict(size=10)), hoverlabel=dict(bgcolor="white", font_size=11), font=dict(size=10 if compact_mode else 12), xaxis=dict(showgrid=False, showline=True, linecolor="#d1d5db", fixedrange=True, hoverformat="%Y-%m-%d"), yaxis=dict(showgrid=True, gridcolor="#eeeeee", zeroline=False, fixedrange=True))
    fig.update_xaxes(fixedrange=True)
    fig.update_yaxes(fixedrange=True)
    return fig


def chart_height(compact, normal):
    return compact if compact_mode else normal


def build_fig1(date_range):
    data = get_iorb().merge(get_rrp_rate(), on="observation_date", how="outer").merge(get_effr(), on="observation_date", how="outer").merge(get_sofr(), on="observation_date", how="outer").sort_values("observation_date")
    data = filter_range(data, date_range)
    fig = go.Figure()
    for column, name, width in [("IORB", "IORB", 2.6), ("RRPONTSYAWARD", "ON RRP", 2.6), ("EFFR", "EFFR", 2.6), ("SOFR", "SOFR", 2.2)]:
        add_line(fig, data, column, name, width)
    fig.update_layout(yaxis_title="Rate (%)")
    return apply_chart_style(fig, chart_height(190, 470))


def build_fig2(date_range):
    data = get_dgs10().merge(get_dfii10(), on="observation_date", how="inner").sort_values("observation_date")
    data = filter_range(data, date_range)
    data["Breakeven"] = data["DGS10"] - data["DFII10"]
    fig = go.Figure()
    for column, name, width, dash in [("DGS10", "10Y Nominal", 2.8, None), ("DFII10", "10Y Real", 2.6, None), ("Breakeven", "10Y Breakeven", 2.5, "dot")]:
        add_line(fig, data, column, name, width, dash)
    fig.update_layout(yaxis_title="Yield (%)")
    return apply_chart_style(fig, chart_height(190, 470))


def build_fig3(date_range):
    data = get_dgs3mo().merge(get_dgs2(), on="observation_date", how="outer").merge(get_dgs10(), on="observation_date", how="outer").sort_values("observation_date")
    data = filter_range(data, date_range)
    data["10Y-2Y"] = data["DGS10"] - data["DGS2"]
    data["10Y-3M"] = data["DGS10"] - data["DGS3MO"]
    fig = go.Figure()
    for column, name, width in [("DGS3MO", "3M", 2.2), ("DGS2", "2Y", 2.4), ("DGS10", "10Y", 2.8)]:
        add_line(fig, data, column, name, width)
    add_line(fig, data, "10Y-2Y", "10Y−2Y", 2.2, "dot", "y2", " bp")
    add_line(fig, data, "10Y-3M", "10Y−3M", 2.2, "dash", "y2", " bp")
    fig.update_traces(selector=dict(name="10Y−2Y"), hovertemplate="10Y−2Y: %{y:.1f} bp<extra></extra>")
    fig.update_traces(selector=dict(name="10Y−3M"), hovertemplate="10Y−3M: %{y:.1f} bp<extra></extra>")
    fig.update_layout(yaxis=dict(title="Yield (%)", fixedrange=True), yaxis2=dict(title="Spread (bp)", overlaying="y", side="right", showgrid=False, zeroline=True, zerolinecolor="#9ca3af", fixedrange=True))
    return apply_chart_style(fig, chart_height(200, 500))


PARAM_DESCRIPTIONS = [
    "IORB（Interest on Reserve Balances）：美联储对存放在美联储的准备金余额支付的利率。ON RRP（Overnight Reverse Repurchase Agreement）：美联储隔夜逆回购工具的利率。EFFR（Effective Federal Funds Rate）：美国联邦基金市场的有效隔夜利率。SOFR（Secured Overnight Financing Rate）：以美国国债为抵押的隔夜融资利率。",
    "10Y Nominal：10年期美国国债名义收益率。10Y Real：10年期美国国债实际收益率，通常指10年期TIPS实际收益率。Breakeven：10年期盈亏平衡通胀率，即名义收益率与实际收益率之差。",
    "3M：3个月期美国国债收益率。2Y：2年期美国国债收益率。10Y：10年期美国国债收益率。10Y−2Y：10年期与2年期美国国债收益率之差。10Y−3M：10年期与3个月期美国国债收益率之差。",
]


def show_parameter_description(index):
    st.markdown(f'<div class="mini-description">{PARAM_DESCRIPTIONS[index]}</div>', unsafe_allow_html=True)


@st.fragment(run_every="3600s")
def render_core_charts():
    if compact_mode:
        col1, col2, col3 = st.columns(3, gap="small")
        configs = [
            (col1, '<div class="compact-title">🏦 1. Fed Policy Rate</div>', '<div class="compact-description">IORB / ON RRP / EFFR / SOFR</div>', "compact_corridor_range", build_fig1, [("IORB", "https://fred.stlouisfed.org/series/IORB"), ("ON RRP", "https://fred.stlouisfed.org/series/RRPONTSYAWARD"), ("EFFR", "https://fred.stlouisfed.org/series/EFFR"), ("SOFR", "https://fred.stlouisfed.org/series/SOFR")], 0),
            (col2, '<div class="compact-title">2. 10Y Yield Structure</div>', '<div class="compact-description">10Y Nominal / Real / Breakeven</div>', "compact_yield10_range", build_fig2, [("DGS10", "https://fred.stlouisfed.org/series/DGS10"), ("DFII10", "https://fred.stlouisfed.org/series/DFII10"), ("T10YIE", "https://fred.stlouisfed.org/series/T10YIE")], 1),
            (col3, '<div class="compact-title">3. Treasury Yield</div>', '<div class="compact-description">3M / 2Y / 10Y / Curve Spread</div>', "compact_treasury_range", build_fig3, [("DGS3MO", "https://fred.stlouisfed.org/series/DGS3MO"), ("DGS2", "https://fred.stlouisfed.org/series/DGS2"), ("DGS10", "https://fred.stlouisfed.org/series/DGS10"), ("T10Y2Y", "https://fred.stlouisfed.org/series/T10Y2Y"), ("T10Y3M", "https://fred.stlouisfed.org/series/T10Y3M")], 2),
        ]
        for column, title, description, key, builder, sources, desc_index in configs:
            with column:
                st.markdown(title, unsafe_allow_html=True)
                st.markdown(description, unsafe_allow_html=True)
                date_range = st.radio("时间范围", RANGES, horizontal=True, index=1, key=key, label_visibility="collapsed")
                st.plotly_chart(builder(date_range), use_container_width=True, config=PLOTLY_CONFIG)
                show_parameter_description(desc_index)
                add_sources(sources)
    else:
        configs = [
            ('<div class="section-title">🏦 1. Fed Policy Rate & Money Market</div>', '<div class="section-description">IORB、ON RRP Rate、EFFR 与 SOFR</div>', "normal_corridor_range", build_fig1, [("IORB", "https://fred.stlouisfed.org/series/IORB"), ("ON RRP", "https://fred.stlouisfed.org/series/RRPONTSYAWARD"), ("EFFR", "https://fred.stlouisfed.org/series/EFFR"), ("SOFR", "https://fred.stlouisfed.org/series/SOFR")], 0, True),
            ('<div class="section-title">2. 10Y Yield Structure</div>', '<div class="section-description">10Y Nominal / 10Y Real / 10Y Breakeven</div>', "normal_yield10_range", build_fig2, [("DGS10", "https://fred.stlouisfed.org/series/DGS10"), ("DFII10", "https://fred.stlouisfed.org/series/DFII10"), ("T10YIE", "https://fred.stlouisfed.org/series/T10YIE")], 1, True),
            ('<div class="section-title">3. Treasury Yield & Curve Spread</div>', '<div class="section-description">3M、2Y、10Y Treasury Yield 与曲线利差</div>', "normal_treasury_range", build_fig3, [("DGS3MO", "https://fred.stlouisfed.org/series/DGS3MO"), ("DGS2", "https://fred.stlouisfed.org/series/DGS2"), ("DGS10", "https://fred.stlouisfed.org/series/DGS10"), ("T10Y2Y", "https://fred.stlouisfed.org/series/T10Y2Y"), ("T10Y3M", "https://fred.stlouisfed.org/series/T10Y3M")], 2, False),
        ]
        for title, description, key, builder, sources, desc_index, divider in configs:
            st.markdown(title, unsafe_allow_html=True)
            st.markdown(description, unsafe_allow_html=True)
            date_range = st.radio("时间范围", RANGES, horizontal=True, index=1, key=key, label_visibility="collapsed")
            st.plotly_chart(builder(date_range), use_container_width=True, config=PLOTLY_CONFIG)
            show_parameter_description(desc_index)
            add_sources(sources)
            if divider:
                st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)


render_core_charts()

st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)
st.markdown('<div class="section-title">📰 7×24 重点财经快讯</div>', unsafe_allow_html=True)
st.markdown('<div class="section-description">东方财富「红字焦点快讯」 · 平台已筛选重点 · 每60秒自动刷新</div>', unsafe_allow_html=True)


@st.fragment(run_every="60s")
def render_news_panel():
    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("🔄 立即刷新", key="refresh_7x24", use_container_width=True):
            get_sina_news.clear()
            st.rerun()
    news_items, news_error = get_sina_news(limit=50)
    if news_items:
        st.markdown(f'<div class="news-status">当前显示 {len(news_items)} 条 · 来源：东方财富红字焦点快讯 · 60秒自动刷新</div>', unsafe_allow_html=True)
        news_html = '<div class="news-box">'
        for idx, item in enumerate(news_items, start=1):
            news_time = html.escape(str(item.get("time", "")))
            news_title = html.escape(str(item.get("title", "")))
            news_content = html.escape(str(item.get("content", "")))
            news_url = html.escape(str(item.get("url", EASTMONEY_FOCUS_URL)), quote=True)
            if not news_url.startswith(("http://", "https://")):
                news_url = EASTMONEY_FOCUS_URL
            if news_title and news_content and news_title != news_content:
                body = f"<strong>{news_title}</strong><div style=\"margin-top:3px;\">{news_content}</div>"
            else:
                body = news_content or news_title
            news_html += f"""
            <div class="news-item">
                <span class="news-index">{idx}.</span>
                <span class="news-time">{news_time}</span>
                <div class="news-content"><a href="{news_url}" target="_blank" rel="noopener noreferrer">{body}</a></div>
            </div>
            """
        st.html(news_html + "</div>")
    else:
        st.warning("暂时无法取得东方财富红字焦点快讯。")
        if news_error:
            st.caption(f"错误：{news_error}")
    add_sources([("东方财富红字焦点快讯", EASTMONEY_FOCUS_URL)])


render_news_panel()

st.markdown(f'<div class="source-text">Source: <a href="{EASTMONEY_FOCUS_URL}" target="_blank" rel="noopener noreferrer">Eastmoney 7×24 Focus News</a></div>', unsafe_allow_html=True)
