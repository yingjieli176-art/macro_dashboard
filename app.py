import html

import pandas as pd
import plotly.graph_objects as go
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
    get_wsj_news,
)

st.set_page_config(
    page_title="Macro Dashboard",
    page_icon="📊",
    layout="wide",
)

st.markdown(
    """
    <style>
    .block-container {padding-top:1.5rem; padding-bottom:3rem; max-width:1400px;}
    .dashboard-title {font-size:2rem; font-weight:700; margin-bottom:.15rem;}
    .dashboard-subtitle,.section-description,.mini-description,.source-text {color:#6b7280;}
    .dashboard-subtitle {font-size:.95rem; margin-bottom:.8rem;}
    .section-title {font-size:1.35rem; font-weight:650; margin-top:.8rem; margin-bottom:.15rem;}
    .section-description {font-size:.88rem; margin-bottom:.4rem;}
    .mini-description {font-size:.78rem; line-height:1.45; margin:2px 0 8px;}
    .source-text {font-size:.76rem; margin:3px 0 12px;}
    .chart-divider {margin:1rem 0 1.5rem; border-top:1px solid #e5e7eb;}
    .news-box {border:1px solid #e5e7eb; border-radius:8px; padding:6px 10px; background:#fff; max-height:520px; overflow-y:auto;}
    .news-item {padding:7px 3px; border-bottom:1px solid #eee; line-height:1.4; font-size:.84rem;}
    .news-item:last-child {border-bottom:none;}
    .news-time {color:#6b7280; font-size:.72rem; margin-right:7px; white-space:nowrap;}
    .news-source {color:#9ca3af; font-size:.68rem; margin-top:2px;}
    .news-status {color:#6b7280; font-size:.75rem; margin-bottom:5px;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="dashboard-title">Macro Dashboard</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="dashboard-subtitle">US monetary policy, Treasury yields and inflation expectations</div>',
    unsafe_allow_html=True,
)

compact_mode = st.toggle(
    "缩小图表 / 快速浏览",
    value=False,
    help="开启后，三个核心图表横向并排显示，适合快速查看。",
)


def get_start_date(range_name):
    today = pd.Timestamp.today().normalize()
    offsets = {
        "5Y": pd.DateOffset(years=5),
        "1Y": pd.DateOffset(years=1),
        "6M": pd.DateOffset(months=6),
        "3M": pd.DateOffset(months=3),
        "1M": pd.DateOffset(months=1),
    }
    return today - offsets.get(range_name, pd.DateOffset(years=1))


def apply_chart_style(fig, height):
    fig.update_layout(
        height=height,
        template="plotly_white",
        hovermode="x unified",
        margin=dict(l=35, r=35, t=30, b=35),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0, font=dict(size=10)),
        hoverlabel=dict(bgcolor="white", font_size=11),
        font=dict(size=10 if compact_mode else 12),
        xaxis=dict(showgrid=False, showline=True, linecolor="#d1d5db"),
        yaxis=dict(showgrid=True, gridcolor="#eeeeee", zeroline=False),
    )
    return fig


def add_source(text, url):
    st.markdown(
        f'<div class="source-text">Source: <a href="{url}" target="_blank">{html.escape(text)}</a></div>',
        unsafe_allow_html=True,
    )


# =========================================================
# Core charts
# =========================================================

# 1. Fed Policy Rate & Money Market
st.markdown('<div class="section-title">🏦 1. Fed Policy Rate & Money Market</div>', unsafe_allow_html=True)
st.markdown('<div class="section-description">IORB、ON RRP Rate、EFFR 与 SOFR</div>', unsafe_allow_html=True)

corridor_range = st.radio(
    "时间范围",
    ["5Y", "1Y", "6M", "3M", "1M"],
    horizontal=True,
    index=1,
    key="corridor_range",
)

corridor = (
    get_iorb()
    .merge(get_rrp_rate(), on="observation_date", how="outer")
    .merge(get_effr(), on="observation_date", how="outer")
    .merge(get_sofr(), on="observation_date", how="outer")
    .sort_values("observation_date")
)
corridor = corridor[corridor["observation_date"] >= get_start_date(corridor_range)]

fig1 = go.Figure()
for series_id, name, width in [
    ("IORB", "IORB", 2.6),
    ("RRPONTSYAWARD", "ON RRP", 2.6),
    ("EFFR", "EFFR", 2.6),
    ("SOFR", "SOFR", 2.2),
]:
    fig1.add_trace(
        go.Scatter(
            x=corridor["observation_date"],
            y=corridor[series_id],
            name=name,
            mode="lines",
            line=dict(width=width),
        )
    )
fig1.update_layout(yaxis_title="Rate (%)")
apply_chart_style(fig1, 190 if compact_mode else 470)

# 2. 10Y Yield Structure
st.markdown('<div class="section-title">2. 10Y Yield Structure</div>', unsafe_allow_html=True)
st.markdown('<div class="section-description">10Y Nominal / 10Y Real / 10Y Breakeven</div>', unsafe_allow_html=True)

yield10_range = st.radio(
    "时间范围",
    ["5Y", "1Y", "6M", "3M", "1M"],
    horizontal=True,
    index=1,
    key="yield10_range",
)

yield10 = (
    get_dgs10()
    .merge(get_dfii10(), on="observation_date", how="inner")
    .sort_values("observation_date")
)
yield10 = yield10[yield10["observation_date"] >= get_start_date(yield10_range)]
yield10["Breakeven"] = yield10["DGS10"] - yield10["DFII10"]

fig2 = go.Figure()
for col, name, width, dash in [
    ("DGS10", "10Y Nominal", 2.8, None),
    ("DFII10", "10Y Real", 2.6, None),
    ("Breakeven", "10Y Breakeven", 2.5, "dot"),
]:
    line = dict(width=width)
    if dash:
        line["dash"] = dash
    fig2.add_trace(
        go.Scatter(
            x=yield10["observation_date"],
            y=yield10[col],
            name=name,
            mode="lines",
            line=line,
        )
    )
fig2.update_layout(yaxis_title="Yield (%)")
apply_chart_style(fig2, 190 if compact_mode else 470)

# 3. Treasury Yield & Curve Spread
st.markdown('<div class="section-title">3. Treasury Yield & Curve Spread</div>', unsafe_allow_html=True)
st.markdown('<div class="section-description">3M、2Y、10Y Treasury Yield 与曲线利差</div>', unsafe_allow_html=True)

treasury_range = st.radio(
    "时间范围",
    ["5Y", "1Y", "6M", "3M", "1M"],
    horizontal=True,
    index=1,
    key="treasury_range",
)

treasury = (
    get_dgs3mo()
    .merge(get_dgs2(), on="observation_date", how="outer")
    .merge(get_dgs10(), on="observation_date", how="outer")
    .sort_values("observation_date")
)
treasury = treasury[treasury["observation_date"] >= get_start_date(treasury_range)]
treasury["10Y-2Y"] = treasury["DGS10"] - treasury["DGS2"]
treasury["10Y-3M"] = treasury["DGS10"] - treasury["DGS3MO"]

fig3 = go.Figure()
fig3.add_trace(
    go.Scatter(
        x=treasury["observation_date"],
        y=treasury["DGS3MO"],
        name="3M",
        mode="lines",
        line=dict(width=2.2),
    )
)
fig3.add_trace(
    go.Scatter(
        x=treasury["observation_date"],
        y=treasury["DGS2"],
        name="2Y",
        mode="lines",
        line=dict(width=2.4),
    )
)
fig3.add_trace(
    go.Scatter(
        x=treasury["observation_date"],
        y=treasury["DGS10"],
        name="10Y",
        mode="lines",
        line=dict(width=2.8),
    )
)
fig3.add_trace(
    go.Scatter(
        x=treasury["observation_date"],
        y=treasury["10Y-2Y"] * 100,
        name="10Y−2Y",
        mode="lines",
        line=dict(width=2.2, dash="dot"),
        yaxis="y2",
    )
)
fig3.add_trace(
    go.Scatter(
        x=treasury["observation_date"],
        y=treasury["10Y-3M"] * 100,
        name="10Y−3M",
        mode="lines",
        line=dict(width=2.2, dash="dash"),
        yaxis="y2",
    )
)
fig3.update_layout(
    yaxis=dict(title="Yield (%)"),
    yaxis2=dict(
        title="Spread (bp)",
        overlaying="y",
        side="right",
        showgrid=False,
        zeroline=True,
        zerolinecolor="#9ca3af",
    ),
)
apply_chart_style(fig3, 200 if compact_mode else 500)


# Display charts horizontally only in compact mode.
if compact_mode:
    chart_col1, chart_col2, chart_col3 = st.columns(3, gap="small")
    with chart_col1:
        st.markdown("**1. Fed Policy Rate & Money Market**")
        st.plotly_chart(fig1, use_container_width=True)
        st.caption("IORB / ON RRP / EFFR / SOFR")
        add_source("FRED", "https://fred.stlouisfed.org/graph/?graph_id=1547733&rn=698")
    with chart_col2:
        st.markdown("**2. 10Y Yield Structure**")
        st.plotly_chart(fig2, use_container_width=True)
        st.caption("10Y Nominal / Real / Breakeven")
        add_source("FRED", "https://fred.stlouisfed.org/")
    with chart_col3:
        st.markdown("**3. Treasury Yield & Curve Spread**")
        st.plotly_chart(fig3, use_container_width=True)
        st.caption("3M / 2Y / 10Y / 10Y−2Y / 10Y−3M")
        add_source("FRED", "https://fred.stlouisfed.org/")
else:
    st.plotly_chart(fig1, use_container_width=True)
    st.markdown('<div class="mini-description">IORB / ON RRP构成政策利率走廊，EFFR观察联邦基金市场，SOFR观察隔夜担保融资。</div>', unsafe_allow_html=True)
    add_source("FRED — Policy Rate Corridor", "https://fred.stlouisfed.org/graph/?graph_id=1547733&rn=698")

    st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)
    st.plotly_chart(fig2, use_container_width=True)
    st.markdown('<div class="mini-description">10Y Breakeven = 10Y Nominal − 10Y Real，用于观察市场隐含通胀预期。</div>', unsafe_allow_html=True)
    add_source("FRED — Treasury & Real Yield Data", "https://fred.stlouisfed.org/")

    st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)
    st.plotly_chart(fig3, use_container_width=True)
    st.markdown('<div class="mini-description">曲线斜率：10Y−2Y、10Y−3M；正值代表正常向上倾斜，负值代表倒挂。</div>', unsafe_allow_html=True)
    add_source("FRED — Treasury Constant Maturity Rates", "https://fred.stlouisfed.org/")


# =========================================================
# 7×24 Market News — standalone bottom panel
# =========================================================

st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)
st.markdown('<div class="section-title">📰 7×24 Market News</div>', unsafe_allow_html=True)
st.markdown('<div class="section-description">实时财经文字快讯 · 每 60 秒自动刷新</div>', unsafe_allow_html=True)

@st.fragment(run_every="60s")
def render_news_panel():
    if st.button("🔄 立即刷新7×24", key="refresh_7x24"):
        get_sina_news.clear()
        get_wsj_news.clear()

    sina_news, sina_error = get_sina_news(limit=20)
    wsj_news, wsj_error = get_wsj_news(limit=10)

    col_sina, col_wsj = st.columns(2, gap="large")

    with col_sina:
        st.markdown("#### 新浪财经 7×24")
        if sina_news:
            st.markdown(f'<div class="news-status">最新 {len(sina_news)} 条 · 自动刷新中</div>', unsafe_allow_html=True)
            st.markdown('<div class="news-box">', unsafe_allow_html=True)
            for item in sina_news:
                news_time = html.escape(str(item.get("time", "")))
                news_title = html.escape(str(item.get("title", "")))
                news_url = html.escape(str(item.get("url", "")))
                st.markdown(
                    f'<div class="news-item"><span class="news-time">{news_time}</span>'
                    f'<a href="{news_url}" target="_blank">{news_title}</a></div>',
                    unsafe_allow_html=True,
                )
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.error("新浪7×24获取失败。")
            if sina_error:
                st.caption(f"错误：{sina_error}")
        add_source("新浪财经 7×24", "https://finance.sina.com.cn/7x24/")

    with col_wsj:
        st.markdown("#### WSJ")
        if wsj_news:
            st.markdown(f'<div class="news-status">公开可见 Headlines · {len(wsj_news)} 条 · 自动刷新中</div>', unsafe_allow_html=True)
            st.markdown('<div class="news-box">', unsafe_allow_html=True)
            for item in wsj_news:
                news_title = html.escape(str(item.get("title", "")))
                news_url = html.escape(str(item.get("url", "")))
                st.markdown(
                    f'<div class="news-item"><a href="{news_url}" target="_blank">{news_title}</a>'
                    '<div class="news-source">The Wall Street Journal</div></div>',
                    unsafe_allow_html=True,
                )
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.warning("WSJ公开新闻暂时无法获取。")
            if wsj_error:
                st.caption(f"错误：{wsj_error}")
        add_source("WSJ Finance", "https://www.wsj.com/finance")


render_news_panel()
