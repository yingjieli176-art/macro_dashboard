import streamlit as st

import html
import pandas as pd
import plotly.graph_objects as go

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


# =========================================================
# Page Config
# =========================================================

st.set_page_config(
    page_title="Macro Dashboard",
    page_icon="📊",
    layout="wide"
)


# =========================================================
# CSS
# =========================================================

st.markdown(
    """
    <style>

    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 3rem;
        max-width: 1400px;
    }

    .dashboard-title {
        font-size: 2rem;
        font-weight: 700;
        margin-bottom: 0.15rem;
    }

    .dashboard-subtitle {
        color: #6b7280;
        font-size: 0.95rem;
        margin-bottom: 0.8rem;
    }

    .section-title {
        font-size: 1.35rem;
        font-weight: 650;
        margin-top: 0.8rem;
        margin-bottom: 0.15rem;
    }

    .section-description {
        color: #6b7280;
        font-size: 0.88rem;
        margin-bottom: 0.4rem;
    }

    .mini-description {
        color: #6b7280;
        font-size: 0.78rem;
        line-height: 1.45;
        margin-top: 2px;
        margin-bottom: 8px;
    }

    .source-text {
        color: #6b7280;
        font-size: 0.76rem;
        margin-top: 3px;
        margin-bottom: 12px;
    }

    .chart-divider {
        margin-top: 0.8rem;
        margin-bottom: 1.5rem;
        border-top: 1px solid #e5e7eb;
    }

    .news-box {
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 6px 10px;
        background: #ffffff;
        max-height: 520px;
        overflow-y: auto;
    }

    .news-item {
        padding: 7px 3px;
        border-bottom: 1px solid #eeeeee;
        line-height: 1.4;
        font-size: 0.84rem;
    }

    .news-item:last-child {
        border-bottom: none;
    }

    .news-time {
        color: #6b7280;
        font-size: 0.72rem;
        margin-right: 7px;
        white-space: nowrap;
    }

    .news-source {
        color: #9ca3af;
        font-size: 0.68rem;
        margin-top: 2px;
    }

    .news-status {
        color: #6b7280;
        font-size: 0.75rem;
        margin-bottom: 5px;
    }

    </style>
    """,
    unsafe_allow_html=True
)


# =========================================================
# Header
# =========================================================

st.markdown(
    '<div class="dashboard-title">'
    'Macro Dashboard'
    '</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="dashboard-subtitle">'
    'US monetary policy, Treasury yields and inflation expectations'
    '</div>',
    unsafe_allow_html=True
)


# =========================================================
# Compact Mode
# =========================================================

compact_mode = st.toggle(
    "缩小图表 / 快速浏览",
    value=False,
    help="开启后，所有图表缩小，适合快速查看。"
)


# =========================================================
# Helpers
# =========================================================

def get_start_date(range_name):

    today = pd.Timestamp.today().normalize()

    if range_name == "5Y":
        return today - pd.DateOffset(years=5)

    if range_name == "1Y":
        return today - pd.DateOffset(years=1)

    if range_name == "6M":
        return today - pd.DateOffset(months=6)

    if range_name == "3M":
        return today - pd.DateOffset(months=3)

    if range_name == "1M":
        return today - pd.DateOffset(months=1)

    return today - pd.DateOffset(years=1)


def apply_chart_style(fig, height):

    fig.update_layout(

        height=height,

        template="plotly_white",

        hovermode="x unified",

        margin=dict(
            l=45,
            r=55,
            t=35,
            b=40
        ),

        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.01,
            xanchor="left",
            x=0
        ),

        hoverlabel=dict(
            bgcolor="white",
            font_size=12
        ),

        font=dict(
            size=12
        ),

        xaxis=dict(
            showgrid=False,
            showline=True,
            linecolor="#d1d5db"
        ),

        yaxis=dict(
            showgrid=True,
            gridcolor="#eeeeee",
            zeroline=False
        )
    )

    return fig


def add_source(text, url):

    st.markdown(
        f"""
        <div class="source-text">
            Source:
            <a href="{url}" target="_blank">
                {html.escape(text)}
            </a>
        </div>
        """,
        unsafe_allow_html=True
    )


# =========================================================
# 7×24 Market News
# =========================================================
#
# 放在最上面，确保打开 Dashboard 第一屏就能看到
#

st.markdown(
    '<div class="section-title">'
    '📰 7×24 Market News'
    '</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="section-description">'
    '实时财经文字快讯'
    '</div>',
    unsafe_allow_html=True
)


refresh = st.button(
    "🔄 刷新7×24",
    key="refresh_7x24"
)


if refresh:

    get_sina_news.clear()
    get_wsj_news.clear()


sina_news, sina_error = get_sina_news(
    limit=20
)

wsj_news, wsj_error = get_wsj_news(
    limit=10
)


col_sina, col_wsj = st.columns(
    2,
    gap="large"
)


# =========================================================
# Sina
# =========================================================

with col_sina:

    st.markdown(
        "#### 新浪财经 7×24"
    )

    if sina_news:

        st.markdown(
            '<div class="news-status">'
            f'最新 {len(sina_news)} 条'
            '</div>',
            unsafe_allow_html=True
        )

        st.markdown(
            '<div class="news-box">',
            unsafe_allow_html=True
        )

        for item in sina_news:

            news_time = html.escape(
                str(item.get("time", ""))
            )

            news_title = html.escape(
                str(item.get("title", ""))
            )

            news_url = html.escape(
                str(item.get("url", ""))
            )

            st.markdown(
                f"""
                <div class="news-item">
                    <span class="news-time">
                        {news_time}
                    </span>
                    <a href="{news_url}" target="_blank">
                        {news_title}
                    </a>
                </div>
                """,
                unsafe_allow_html=True
            )

        st.markdown(
            '</div>',
            unsafe_allow_html=True
        )

    else:

        st.error(
            "新浪7×24获取失败。"
        )

        if sina_error:

            st.caption(
                f"错误：{sina_error}"
            )

    add_source(
        "新浪财经 7×24",
        "https://finance.sina.com.cn/7x24/"
    )


# =========================================================
# WSJ
# =========================================================

with col_wsj:

    st.markdown(
        "#### WSJ"
    )

    if wsj_news:

        st.markdown(
            '<div class="news-status">'
            f'公开可见 Headlines · {len(wsj_news)} 条'
            '</div>',
            unsafe_allow_html=True
        )

        st.markdown(
            '<div class="news-box">',
            unsafe_allow_html=True
        )

        for item in wsj_news:

            news_title = html.escape(
                str(item.get("title", ""))
            )

            news_url = html.escape(
                str(item.get("url", ""))
            )

            st.markdown(
                f"""
                <div class="news-item">
                    <a href="{news_url}" target="_blank">
                        {news_title}
                    </a>
                    <div class="news-source">
                        The Wall Street Journal
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )

        st.markdown(
            '</div>',
            unsafe_allow_html=True
        )

    else:

        st.warning(
            "WSJ公开新闻暂时无法获取。"
        )

        if wsj_error:

            st.caption(
                f"错误：{wsj_error}"
            )

    add_source(
        "WSJ Finance",
        "https://www.wsj.com/finance"
    )


# =========================================================
# Divider
# =========================================================

st.markdown(
    '<div class="chart-divider"></div>',
    unsafe_allow_html=True
)


# =========================================================
# 1. Policy Rate Corridor
# =========================================================

st.markdown(
    '<div class="section-title">'
    '🏦 1. Fed Policy Rate & Money Market'
    '</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="section-description">'
    'IORB、ON RRP Rate、EFFR 与 SOFR'
    '</div>',
    unsafe_allow_html=True
)


corridor_range = st.radio(
    "时间范围",
    ["5Y", "1Y", "6M", "3M", "1M"],
    horizontal=True,
    index=1,
    key="corridor_range"
)


corridor_start = get_start_date(
    corridor_range
)


corridor = (
    get_iorb()
    .merge(
        get_rrp_rate(),
        on="observation_date",
        how="outer"
    )
    .merge(
        get_effr(),
        on="observation_date",
        how="outer"
    )
    .merge(
        get_sofr(),
        on="observation_date",
        how="outer"
    )
    .sort_values("observation_date")
)


corridor = corridor[
    corridor["observation_date"] >= corridor_start
]


fig1 = go.Figure()


for series_id, name, width in [

    ("IORB", "IORB", 2.6),

    (
        "RRPONTSYAWARD",
        "ON RRP",
        2.6
    ),

    ("EFFR", "EFFR", 2.6),

    ("SOFR", "SOFR", 2.2),

]:

    fig1.add_trace(
        go.Scatter(
            x=corridor["observation_date"],
            y=corridor[series_id],
            name=name,
            mode="lines",
            line=dict(width=width)
        )
    )


fig1.update_layout(
    yaxis_title="Rate (%)"
)


fig1 = apply_chart_style(
    fig1,
    220 if compact_mode else 470
)


st.plotly_chart(
    fig1,
    use_container_width=True
)


if compact_mode:

    st.markdown(
        '<div class="mini-description">'
        'IORB / ON RRP构成政策利率走廊，'
        'EFFR观察联邦基金市场，SOFR观察隔夜担保融资。'
        '</div>',
        unsafe_allow_html=True
    )


add_source(
    "FRED — Policy Rate Corridor",
    "https://fred.stlouisfed.org/graph/?graph_id=1547733&rn=698"
)


st.markdown(
    '<div class="chart-divider"></div>',
    unsafe_allow_html=True
)


# =========================================================
# 2. 10Y Yield Structure
# =========================================================

st.markdown(
    '<div class="section-title">'
    '2. 10Y Yield Structure'
    '</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="section-description">'
    '10Y Nominal / 10Y Real / 10Y Breakeven'
    '</div>',
    unsafe_allow_html=True
)


yield10_range = st.radio(
    "时间范围",
    ["5Y", "1Y", "6M", "3M", "1M"],
    horizontal=True,
    index=1,
    key="yield10_range"
)


yield10_start = get_start_date(
    yield10_range
)


yield10 = (
    get_dgs10()
    .merge(
        get_dfii10(),
        on="observation_date",
        how="inner"
    )
    .sort_values("observation_date")
)


yield10 = yield10[
    yield10["observation_date"] >= yield10_start
]


yield10["Breakeven"] = (
    yield10["DGS10"]
    - yield10["DFII10"]
)


fig2 = go.Figure()


fig2.add_trace(
    go.Scatter(
        x=yield10["observation_date"],
        y=yield10["DGS10"],
        name="10Y Nominal",
        mode="lines",
        line=dict(width=2.8)
    )
)


fig2.add_trace(
    go.Scatter(
        x=yield10["observation_date"],
        y=yield10["DFII10"],
        name="10Y Real",
        mode="lines",
        line=dict(width=2.6)
    )
)


fig2.add_trace(
    go.Scatter(
        x=yield10["observation_date"],
        y=yield10["Breakeven"],
        name="10Y Breakeven",
        mode="lines",
        line=dict(
            width=2.5,
            dash="dot"
        )
    )
)


fig2.update_layout(
    yaxis_title="Yield (%)"
)


fig2 = apply_chart_style(
    fig2,
    220 if compact_mode else 470
)


st.plotly_chart(
    fig2,
    use_container_width=True
)


if compact_mode:

    st.markdown(
        '<div class="mini-description">'
        '10Y Nominal − 10Y Real = 10Y Breakeven，'
        '用于观察市场隐含通胀预期。'
        '</div>',
        unsafe_allow_html=True
    )


add_source(
    "FRED — 10Y Treasury / 10Y TIPS",
    "https://fred.stlouisfed.org/"
)


st.markdown(
    '<div class="chart-divider"></div>',
    unsafe_allow_html=True
)


# =========================================================
# 3. Treasury Yield & Curve Spread
# =========================================================

st.markdown(
    '<div class="section-title">'
    '3. Treasury Yield & Curve Spread'
    '</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="section-description">'
    '3M、2Y、10Y Treasury Yield 与 10Y−2Y / 10Y−3M Spread'
    '</div>',
    unsafe_allow_html=True
)


treasury_range = st.radio(
    "时间范围",
    ["5Y", "1Y", "6M", "3M", "1M"],
    horizontal=True,
    index=1,
    key="treasury_range"
)


treasury_start = get_start_date(
    treasury_range
)


treasury = (
    get_dgs3mo()
    .merge(
        get_dgs2(),
        on="observation_date",
        how="outer"
    )
    .merge(
        get_dgs10(),
        on="observation_date",
        how="outer"
    )
    .sort_values("observation_date")
)


treasury = treasury[
    treasury["observation_date"] >= treasury_start
]


treasury["10Y-2Y"] = (
    treasury["DGS10"]
    - treasury["DGS2"]
) * 100


treasury["10Y-3M"] = (
    treasury["DGS10"]
    - treasury["DGS3MO"]
) * 100


fig3 = go.Figure()


fig3.add_trace(
    go.Scatter(
        x=treasury["observation_date"],
        y=treasury["DGS3MO"],
        name="3M",
        mode="lines",
        line=dict(width=2.3)
    )
)


fig3.add_trace(
    go.Scatter(
        x=treasury["observation_date"],
        y=treasury["DGS2"],
        name="2Y",
        mode="lines",
        line=dict(width=2.5)
    )
)


fig3.add_trace(
    go.Scatter(
        x=treasury["observation_date"],
        y=treasury["DGS10"],
        name="10Y",
        mode="lines",
        line=dict(width=2.8)
    )
)


fig3.update_layout(
    yaxis=dict(
        title="Yield (%)",
        side="left"
    ),
    yaxis2=dict(
        title="Spread (bp)",
        overlaying="y",
        side="right",
        showgrid=False,
        zeroline=True,
        zerolinecolor="#9ca3af"
    )
)


fig3.add_trace(
    go.Scatter(
        x=treasury["observation_date"],
        y=treasury["10Y-2Y"],
        name="10Y−2Y",
        mode="lines",
        line=dict(width=2.2, dash="dot"),
        yaxis="y2"
    )
)


fig3.add_trace(
    go.Scatter(
        x=treasury["observation_date"],
        y=treasury["10Y-3M"],
        name="10Y−3M",
        mode="lines",
        line=dict(width=2.2, dash="dash"),
        yaxis="y2"
    )


fig3 = apply_chart_style(
    fig3,
    230 if compact_mode else 500
)


st.plotly_chart(
    fig3,
    use_container_width=True
)


if compact_mode:

    st.markdown(
        '<div class="mini-description">'
        '曲线斜率：10Y−2Y、10Y−3M；正值代表正常向上倾斜，负值代表倒挂。'
        '</div>',
        unsafe_allow_html=True
    )


add_source(
    "FRED — Treasury Constant Maturity Rates",
    "https://fred.stlouisfed.org/"
)


# =========================================================
# 4. System Diagnostics
# =========================================================

st.markdown(
    '<div class="chart-divider"></div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="section-title">'
    '4. System Diagnostics'
    '</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="section-description">'
    '用于确认 Dashboard、FRED 与新闻数据链路是否正常。'
    '</div>',
    unsafe_allow_html=True
)


diag_col1, diag_col2, diag_col3 = st.columns(3)

with diag_col1:
    st.success("Dashboard：页面已执行到 Diagnostics")

with diag_col2:
    try:
        diag_fred = get_dgs10()
        if diag_fred is not None and not diag_fred.empty:
            st.success(f"FRED：正常 · DGS10 {len(diag_fred)} 条")
        else:
            st.warning("FRED：无数据")
    except Exception as exc:
        st.error(f"FRED：失败 · {exc}")

with diag_col3:
    try:
        diag_sina, diag_sina_error = get_sina_news(limit=1)
        if diag_sina:
            st.success("Sina 7×24：正常")
        else:
            st.warning(f"Sina 7×24：无数据 · {diag_sina_error or '未知原因'}")
    except Exception as exc:
        st.error(f"Sina 7×24：失败 · {exc}")


diag_col4, diag_col5, diag_col6 = st.columns(3)

with diag_col4:
    try:
        diag_eastmoney, diag_eastmoney_error = get_sina_news(limit=1)
        if diag_eastmoney:
            st.success("7×24：数据链路可用")
        else:
            st.warning(f"7×24：无数据 · {diag_eastmoney_error or '未知原因'}")
    except Exception as exc:
        st.error(f"7×24：失败 · {exc}")

with diag_col5:
    try:
        diag_wsj, diag_wsj_error = get_wsj_news(limit=1)
        if diag_wsj:
            st.success("WSJ：正常")
        else:
            st.warning(f"WSJ：无公开 Headlines · {diag_wsj_error or '正常限制'}")
    except Exception as exc:
        st.error(f"WSJ：失败 · {exc}")

with diag_col6:
    st.info(f"Compact Mode：{'ON' if compact_mode else 'OFF'}")

st.caption(
    f"Diagnostics timestamp: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}"
)


# =========================================================
# Footer
# =========================================================

st.markdown(
    '<div class="chart-divider"></div>',
    unsafe_allow_html=True
)

st.caption(
    "Macro Dashboard · Data sources: FRED / Sina Finance / WSJ"
)
