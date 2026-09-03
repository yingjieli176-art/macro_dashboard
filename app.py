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
)


# =========================================================
# CONFIG
# =========================================================

st.set_page_config(
    page_title="Macro & Market Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# =========================================================
# URL
# =========================================================

SINA_7X24_URL = "https://finance.sina.com.cn/7x24/"
EASTMONEY_FOCUS_URL = "https://kuaixun.eastmoney.com/"


FRED_URLS = {
    "IORB": "https://fred.stlouisfed.org/series/IORB",
    "ON RRP": "https://fred.stlouisfed.org/series/RRPONTSYAWARD",
    "EFFR": "https://fred.stlouisfed.org/series/EFFR",
    "SOFR": "https://fred.stlouisfed.org/series/SOFR",

    "10Y Nominal": "https://fred.stlouisfed.org/series/DGS10",
    "10Y Real": "https://fred.stlouisfed.org/series/DFII10",
    "10Y Breakeven": "https://fred.stlouisfed.org/series/T10YIE",

    "3M": "https://fred.stlouisfed.org/series/DGS3MO",
    "2Y": "https://fred.stlouisfed.org/series/DGS2",
    "10Y": "https://fred.stlouisfed.org/series/DGS10",
    "10Y-2Y": "https://fred.stlouisfed.org/series/T10Y2Y",
    "10Y-3M": "https://fred.stlouisfed.org/series/T10Y3M",
}


# =========================================================
# CSS
# =========================================================

st.markdown(
    """
    <style>

    .block-container {
        padding-top: 1rem;
        padding-bottom: 1.5rem;
    }

    h1 {
        margin-bottom: 0.15rem !important;
    }

    h2 {
        margin-top: 0.7rem !important;
        margin-bottom: 0.25rem !important;
    }

    h3 {
        margin-top: 0.5rem !important;
        margin-bottom: 0.2rem !important;
    }

    .source-row {
        font-size: 0.74rem;
        line-height: 1.35;
        margin-top: -0.35rem;
        margin-bottom: 0.45rem;
        color: #777;
    }

    .source-row a {
        color: #777 !important;
        text-decoration: none !important;
        margin-right: 12px;
    }

    .source-row a:hover {
        color: #444 !important;
        text-decoration: none !important;
    }

    .news-container {
        border-top: 1px solid rgba(128, 128, 128, 0.20);
    }

    .news-item {
        padding: 7px 3px 8px 3px;
        border-bottom: 1px solid rgba(128, 128, 128, 0.14);
    }

    .news-time {
        display: inline-block;
        width: 68px;
        color: #888;
        font-size: 0.76rem;
        vertical-align: top;
        padding-top: 1px;
    }

    .news-title {
        color: inherit !important;
        font-size: 0.88rem;
        line-height: 1.42;
        text-decoration: none !important;
    }

    .news-title:hover {
        text-decoration: none !important;
    }

    .news-content {
        margin-left: 68px;
        margin-top: 2px;
        color: #777;
        font-size: 0.76rem;
        line-height: 1.38;
    }

    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# TITLE
# =========================================================

st.title("📊 Macro & Market Dashboard")

st.caption(
    "US monetary policy · Treasury yields · yield curve · 7×24 focus news"
)


# =========================================================
# COMPACT MODE
# =========================================================

compact_mode = st.toggle(
    "Compact mode",
    value=True,
)


# =========================================================
# HELPERS
# =========================================================

def get_start_date(compact_mode):

    if compact_mode:
        days = 365
    else:
        days = 365 * 3

    return (
        pd.Timestamp.today().normalize()
        - pd.Timedelta(days=days)
    )


def apply_chart_style(fig, compact_mode=True):

    # 保留原来的 compact mode 尺寸逻辑
    if compact_mode:
        height = 280
    else:
        height = 380

    fig.update_layout(
        height=height,

        margin=dict(
            l=42,
            r=18,
            t=42,
            b=30,
        ),

        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.01,
            xanchor="left",
            x=0,
        ),

        # =================================================
        # 鼠标悬停：
        # 只查看日期 + 数据
        # =================================================
        hovermode="x unified",

        # 不允许 drag
        dragmode=False,
    )

    # X / Y 轴不能被鼠标拖动缩放
    fig.update_xaxes(
        fixedrange=True,
        showgrid=False,
    )

    fig.update_yaxes(
        fixedrange=True,
    )

    return fig


def add_sources(sources):

    links = []

    for name, url in sources:

        links.append(
            '<a href="'
            + html.escape(url, quote=True)
            + '" target="_blank">'
            + html.escape(name)
            + "</a>"
        )

    st.html(
        '<div class="source-row">'
        + "".join(links)
        + "</div>"
    )


def chart_config():

    return {
        # 完全隐藏 Plotly toolbar
        "displayModeBar": False,

        # 禁止滚轮缩放
        "scrollZoom": False,

        # 禁止双击 reset / autosize 操作
        "doubleClick": False,

        # 禁止编辑
        "editable": False,

        # 不显示 Plotly logo
        "displaylogo": False,
    }


def show_chart(fig):

    st.plotly_chart(
        fig,
        use_container_width=True,
        config=chart_config(),
    )


# =========================================================
# CHART 1
# Fed Policy Rate & Money Market
# =========================================================

def build_fig1(start_date):

    iorb = get_iorb()
    rrp = get_rrp_rate()
    effr = get_effr()
    sofr = get_sofr()

    df = (
        iorb
        .merge(
            rrp,
            on="observation_date",
            how="outer",
        )
        .merge(
            effr,
            on="observation_date",
            how="outer",
        )
        .merge(
            sofr,
            on="observation_date",
            how="outer",
        )
        .sort_values(
            "observation_date"
        )
    )

    df = df[
        df["observation_date"] >= start_date
    ]

    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=df["observation_date"],
            y=df["IORB"],
            mode="lines",
            name="IORB",
            hovertemplate=(
                "IORB: %{y:.3f}%"
                "<extra></extra>"
            ),
        )
    )

    fig.add_trace(
        go.Scatter(
            x=df["observation_date"],
            y=df["RRPONTSYAWARD"],
            mode="lines",
            name="ON RRP",
            hovertemplate=(
                "ON RRP: %{y:.3f}%"
                "<extra></extra>"
            ),
        )
    )

    fig.add_trace(
        go.Scatter(
            x=df["observation_date"],
            y=df["EFFR"],
            mode="lines",
            name="EFFR",
            hovertemplate=(
                "EFFR: %{y:.3f}%"
                "<extra></extra>"
            ),
        )
    )

    fig.add_trace(
        go.Scatter(
            x=df["observation_date"],
            y=df["SOFR"],
            mode="lines",
            name="SOFR",
            hovertemplate=(
                "SOFR: %{y:.3f}%"
                "<extra></extra>"
            ),
        )
    )

    fig.update_layout(
        title="Fed Policy Rate & Money Market",
        yaxis_title="Rate (%)",
    )

    return apply_chart_style(
        fig,
        compact_mode,
    )


# =========================================================
# CHART 2
# 10Y Yield Structure
# =========================================================

def build_fig2(start_date):

    dgs10 = get_dgs10()
    dfii10 = get_dfii10()

    df = (
        dgs10
        .merge(
            dfii10,
            on="observation_date",
            how="outer",
        )
        .sort_values(
            "observation_date"
        )
    )

    df = df[
        df["observation_date"] >= start_date
    ]

    df["Breakeven"] = (
        df["DGS10"]
        - df["DFII10"]
    )

    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=df["observation_date"],
            y=df["DGS10"],
            mode="lines",
            name="10Y Nominal",
            hovertemplate=(
                "10Y Nominal: %{y:.3f}%"
                "<extra></extra>"
            ),
        )
    )

    fig.add_trace(
        go.Scatter(
            x=df["observation_date"],
            y=df["DFII10"],
            mode="lines",
            name="10Y Real",
            hovertemplate=(
                "10Y Real: %{y:.3f}%"
                "<extra></extra>"
            ),
        )
    )

    fig.add_trace(
        go.Scatter(
            x=df["observation_date"],
            y=df["Breakeven"],
            mode="lines",
            name="10Y Breakeven",
            hovertemplate=(
                "10Y Breakeven: %{y:.3f}%"
                "<extra></extra>"
            ),
        )
    )

    fig.update_layout(
        title="10Y Yield Structure",
        yaxis_title="Yield (%)",
    )

    return apply_chart_style(
        fig,
        compact_mode,
    )


# =========================================================
# CHART 3
# Treasury Yield & Curve Spread
# =========================================================

def build_fig3(start_date):

    dgs3mo = get_dgs3mo()
    dgs2 = get_dgs2()
    dgs10 = get_dgs10()

    df = (
        dgs3mo
        .merge(
            dgs2,
            on="observation_date",
            how="outer",
        )
        .merge(
            dgs10,
            on="observation_date",
            how="outer",
        )
        .sort_values(
            "observation_date"
        )
    )

    df = df[
        df["observation_date"] >= start_date
    ]

    # Percentage points
    df["10Y-2Y"] = (
        df["DGS10"]
        - df["DGS2"]
    )

    df["10Y-3M"] = (
        df["DGS10"]
        - df["DGS3MO"]
    )

    fig = go.Figure()

    # -----------------------------------------------------
    # Yield
    # -----------------------------------------------------

    fig.add_trace(
        go.Scatter(
            x=df["observation_date"],
            y=df["DGS3MO"],
            mode="lines",
            name="3M",
            hovertemplate=(
                "3M: %{y:.3f}%"
                "<extra></extra>"
            ),
        )
    )

    fig.add_trace(
        go.Scatter(
            x=df["observation_date"],
            y=df["DGS2"],
            mode="lines",
            name="2Y",
            hovertemplate=(
                "2Y: %{y:.3f}%"
                "<extra></extra>"
            ),
        )
    )

    fig.add_trace(
        go.Scatter(
            x=df["observation_date"],
            y=df["DGS10"],
            mode="lines",
            name="10Y",
            hovertemplate=(
                "10Y: %{y:.3f}%"
                "<extra></extra>"
            ),
        )
    )

    # -----------------------------------------------------
    # Spread
    # -----------------------------------------------------

    fig.add_trace(
        go.Scatter(
            x=df["observation_date"],
            y=df["10Y-2Y"] * 100,
            mode="lines",
            name="10Y-2Y",
            hovertemplate=(
                "10Y-2Y: %{y:.1f} bp"
                "<extra></extra>"
            ),
        )
    )

    fig.add_trace(
        go.Scatter(
            x=df["observation_date"],
            y=df["10Y-3M"] * 100,
            mode="lines",
            name="10Y-3M",
            hovertemplate=(
                "10Y-3M: %{y:.1f} bp"
                "<extra></extra>"
            ),
        )
    )

    fig.update_layout(
        title="Treasury Yield & Curve Spread",
    )

    fig.update_yaxes(
        title_text="Yield / Spread",
    )

    return apply_chart_style(
        fig,
        compact_mode,
    )


# =========================================================
# CORE CHARTS
# =========================================================

@st.fragment(
    run_every="3600s"
)
def render_core_charts():

    start_date = get_start_date(
        compact_mode
    )

    # =====================================================
    # Chart 1
    # =====================================================

    fig1 = build_fig1(
        start_date
    )

    show_chart(fig1)

    add_sources(
        [
            (
                "IORB",
                FRED_URLS["IORB"],
            ),
            (
                "ON RRP",
                FRED_URLS["ON RRP"],
            ),
            (
                "EFFR",
                FRED_URLS["EFFR"],
            ),
            (
                "SOFR",
                FRED_URLS["SOFR"],
            ),
        ]
    )

    # =====================================================
    # Chart 2
    # =====================================================

    fig2 = build_fig2(
        start_date
    )

    show_chart(fig2)

    add_sources(
        [
            (
                "10Y Nominal",
                FRED_URLS["10Y Nominal"],
            ),
            (
                "10Y Real",
                FRED_URLS["10Y Real"],
            ),
            (
                "10Y Breakeven",
                FRED_URLS["10Y Breakeven"],
            ),
        ]
    )

    # =====================================================
    # Chart 3
    # =====================================================

    fig3 = build_fig3(
        start_date
    )

    show_chart(fig3)

    add_sources(
        [
            (
                "3M",
                FRED_URLS["3M"],
            ),
            (
                "2Y",
                FRED_URLS["2Y"],
            ),
            (
                "10Y",
                FRED_URLS["10Y"],
            ),
            (
                "10Y-2Y",
                FRED_URLS["10Y-2Y"],
            ),
            (
                "10Y-3M",
                FRED_URLS["10Y-3M"],
            ),
        ]
    )


# =========================================================
# RENDER CHARTS
# =========================================================

render_core_charts()


# =========================================================
# NEWS
# =========================================================

st.divider()

st.subheader(
    "📰 7×24 重点财经快讯"
)

st.caption(
    "东方财富「红字焦点快讯」"
    " · 平台已筛选重点"
    " · 每 60 秒自动刷新"
)


# =========================================================
# NEWS PANEL
# =========================================================

@st.fragment(
    run_every="60s"
)
def render_news_panel():

    # -----------------------------------------------------
    # Refresh
    # -----------------------------------------------------

    col1, col2 = st.columns(
        [1, 10]
    )

    with col1:

        if st.button(
            "🔄 刷新",
            key="news_refresh",
            use_container_width=True,
        ):

            get_sina_news.clear()

            st.rerun(
                scope="fragment"
            )

    # -----------------------------------------------------
    # Get platform-selected focus news
    #
    # data.py:
    # type=101
    # = 东方财富「红字焦点快讯」
    #
    # 不做关键词筛选
    # 不做 AI 判断
    # 不自己定义重点
    # -----------------------------------------------------

    news_items, news_error = get_sina_news(
        limit=50
    )

    if news_error:

        st.error(
            news_error
        )

        st.html(
            '<div class="source-row">'
            '<a href="'
            + EASTMONEY_FOCUS_URL
            + '" target="_blank">'
            "Source: 东方财富焦点快讯"
            "</a>"
            "</div>"
        )

        return

    if not news_items:

        st.info(
            "当前没有取得焦点快讯。"
        )

        return

    # -----------------------------------------------------
    # News count
    # -----------------------------------------------------

    st.caption(
        f"当前显示 {len(news_items)} 条"
        " · 平台筛选焦点"
    )

    # -----------------------------------------------------
    # Build HTML
    # -----------------------------------------------------

    output = [
        '<div class="news-container">'
    ]

    for item in news_items:

        title = html.escape(
            str(
                item.get(
                    "title",
                    "",
                )
            )
        )

        content = html.escape(
            str(
                item.get(
                    "content",
                    "",
                )
            )
        )

        news_time = html.escape(
            str(
                item.get(
                    "time",
                    "",
                )
            )
        )

        url = item.get(
            "url",
            EASTMONEY_FOCUS_URL,
        )

        if not isinstance(
            url,
            str,
        ):
            url = EASTMONEY_FOCUS_URL

        if not url.startswith(
            (
                "http://",
                "https://",
            )
        ):
            url = EASTMONEY_FOCUS_URL

        url = html.escape(
            url,
            quote=True,
        )

        output.append(
            '<div class="news-item">'
        )

        output.append(
            '<span class="news-time">'
            + news_time
            + "</span>"
        )

        output.append(
            '<a class="news-title" '
            'href="'
            + url
            + '" '
            'target="_blank">'
            + title
            + "</a>"
        )

        # 标题和正文完全相同的时候不重复显示
        if (
            content
            and content != title
        ):

            output.append(
                '<div class="news-content">'
                + content
                + "</div>"
            )

        output.append(
            "</div>"
        )

    output.append(
        "</div>"
    )

    st.html(
        "".join(output)
    )

    # -----------------------------------------------------
    # Source
    # -----------------------------------------------------

    st.html(
        '<div class="source-row">'
        '<a href="'
        + EASTMONEY_FOCUS_URL
        + '" target="_blank">'
        "Source: 东方财富红字焦点快讯"
        "</a>"
        "</div>"
    )


# =========================================================
# RENDER NEWS
# =========================================================

render_news_panel()
