import html

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
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
# PAGE CONFIG
# =========================================================

st.set_page_config(
    page_title="Macro & Market Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# =========================================================
# CONSTANTS
# =========================================================

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

EASTMONEY_URL = (
    "https://kuaixun.eastmoney.com/"
)


# =========================================================
# CSS
# =========================================================

st.markdown(
    """
    <style>

    /* =====================================================
       GLOBAL
       ===================================================== */

    .block-container {
        padding-top: 1.2rem;
        padding-bottom: 2rem;
        max-width: 1500px;
    }

    h1 {
        margin-bottom: 0.2rem !important;
    }

    h2 {
        margin-top: 1.2rem !important;
        margin-bottom: 0.4rem !important;
    }

    h3 {
        margin-top: 0.8rem !important;
        margin-bottom: 0.3rem !important;
    }


    /* =====================================================
       SOURCE LINKS
       ===================================================== */

    .source-row {
        font-size: 0.78rem;
        line-height: 1.5;
        margin-top: -0.25rem;
        margin-bottom: 0.7rem;
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


    /* =====================================================
       NEWS
       ===================================================== */

    .news-container {
        border-top: 1px solid rgba(128, 128, 128, 0.22);
    }

    .news-item {
        padding: 9px 4px 10px 4px;
        border-bottom: 1px solid rgba(128, 128, 128, 0.16);
    }

    .news-time {
        display: inline-block;
        width: 70px;
        color: #888;
        font-size: 0.78rem;
        vertical-align: top;
        padding-top: 1px;
    }

    .news-title {
        color: inherit;
        font-size: 0.91rem;
        line-height: 1.5;
        text-decoration: none !important;
    }

    .news-title:hover {
        text-decoration: none !important;
    }

    .news-content {
        margin-left: 70px;
        margin-top: 3px;
        color: #777;
        font-size: 0.79rem;
        line-height: 1.45;
    }

    .news-meta {
        color: #888;
        font-size: 0.75rem;
        margin-top: 4px;
    }


    /* =====================================================
       SMALL TEXT
       ===================================================== */

    .muted {
        color: #888;
        font-size: 0.8rem;
    }

    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# TITLE
# =========================================================

st.title(
    "📊 Macro & Market Dashboard"
)

st.caption(
    "US monetary policy · Treasury yields · yield curve · focus financial news"
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

def get_start_date(
    compact,
):
    """
    Compact:
        最近 1 年

    Normal:
        最近 3 年
    """

    if compact:
        return (
            pd.Timestamp.today()
            - pd.Timedelta(
                days=365
            )
        )

    return (
        pd.Timestamp.today()
        - pd.Timedelta(
            days=365 * 3
        )
    )


def apply_chart_style(
    fig,
    compact=True,
):
    """
    统一图表风格。

    关键设置：
        hovermode = x unified
        dragmode  = False

    鼠标停留时只用于查看数据，
    不提供编辑/拖动操作。
    """

    fig.update_layout(
        hovermode="x unified",
        dragmode=False,

        margin=dict(
            l=45,
            r=20,
            t=45,
            b=35,
        ),

        height=330 if compact else 390,

        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
        ),

        hoverlabel=dict(
            namelength=-1,
        ),
    )

    fig.update_xaxes(
        showgrid=False,
        fixedrange=True,
    )

    fig.update_yaxes(
        fixedrange=True,
    )

    return fig


def add_sources(
    sources,
):
    """
    sources:
        [
            ("名称", "URL"),
            ...
        ]
    """

    links = []

    for name, url in sources:

        links.append(
            f'<a href="{html.escape(url)}" '
            f'target="_blank">'
            f'{html.escape(name)}'
            f'</a>'
        )

    st.html(
        '<div class="source-row">'
        + " ".join(links)
        + "</div>"
    )


def plotly_readonly_config():
    """
    Plotly 只读配置。

    禁止：
        - mode bar
        - scroll zoom
        - double click 操作
        - editable
        - logo

    同时图表本身 fixedrange，
    因此用户只能 hover 查看数据。
    """

    return {
        "displayModeBar": False,
        "scrollZoom": False,
        "doubleClick": False,
        "editable": False,
        "displaylogo": False,
    }


def show_chart(
    fig,
):
    """
    所有图表统一使用只读配置。
    """

    st.plotly_chart(
        fig,
        use_container_width=True,
        config=plotly_readonly_config(),
    )


# =========================================================
# CHART 1
# Fed Policy Rate & Money Market
# =========================================================

def build_fig1(
    start_date,
):
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
        df["observation_date"]
        >= start_date
    ]

    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=df["observation_date"],
            y=df["IORB"],
            mode="lines",
            name="IORB",
            connectgaps=False,
        )
    )

    fig.add_trace(
        go.Scatter(
            x=df["observation_date"],
            y=df["RRPONTSYAWARD"],
            mode="lines",
            name="ON RRP",
            connectgaps=False,
        )
    )

    fig.add_trace(
        go.Scatter(
            x=df["observation_date"],
            y=df["EFFR"],
            mode="lines",
            name="EFFR",
            connectgaps=False,
        )
    )

    fig.add_trace(
        go.Scatter(
            x=df["observation_date"],
            y=df["SOFR"],
            mode="lines",
            name="SOFR",
            connectgaps=False,
        )
    )

    fig.update_layout(
        title="Fed Policy Rate & Money Market",
        yaxis_title="Rate (%)",
    )

    apply_chart_style(
        fig,
        compact_mode,
    )

    return fig


# =========================================================
# CHART 2
# 10Y Yield Structure
# =========================================================

def build_fig2(
    start_date,
):
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
        df["observation_date"]
        >= start_date
    ]

    # 10Y Breakeven
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
            connectgaps=False,
        )
    )

    fig.add_trace(
        go.Scatter(
            x=df["observation_date"],
            y=df["DFII10"],
            mode="lines",
            name="10Y Real",
            connectgaps=False,
        )
    )

    fig.add_trace(
        go.Scatter(
            x=df["observation_date"],
            y=df["Breakeven"],
            mode="lines",
            name="10Y Breakeven",
            connectgaps=False,
        )
    )

    fig.update_layout(
        title="10Y Yield Structure",
        yaxis_title="Yield (%)",
    )

    apply_chart_style(
        fig,
        compact_mode,
    )

    return fig


# =========================================================
# CHART 3
# Treasury Yield & Curve Spread
# =========================================================

def build_fig3(
    start_date,
):
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
        df["observation_date"]
        >= start_date
    ]

    # Spread in percentage points
    df["10Y-2Y"] = (
        df["DGS10"]
        - df["DGS2"]
    )

    df["10Y-3M"] = (
        df["DGS10"]
        - df["DGS3MO"]
    )

    fig = make_subplots(
        specs=[
            [
                {
                    "secondary_y": True
                }
            ]
        ]
    )

    # ---------------------------------------------
    # Treasury yields
    # ---------------------------------------------

    fig.add_trace(
        go.Scatter(
            x=df["observation_date"],
            y=df["DGS3MO"],
            mode="lines",
            name="3M",
            connectgaps=False,
        ),
        secondary_y=False,
    )

    fig.add_trace(
        go.Scatter(
            x=df["observation_date"],
            y=df["DGS2"],
            mode="lines",
            name="2Y",
            connectgaps=False,
        ),
        secondary_y=False,
    )

    fig.add_trace(
        go.Scatter(
            x=df["observation_date"],
            y=df["DGS10"],
            mode="lines",
            name="10Y",
            connectgaps=False,
        ),
        secondary_y=False,
    )

    # ---------------------------------------------
    # Curve spreads
    #
    # Convert percentage points to bp
    # ---------------------------------------------

    fig.add_trace(
        go.Scatter(
            x=df["observation_date"],
            y=df["10Y-2Y"] * 100,
            mode="lines",
            name="10Y-2Y",
            connectgaps=False,
        ),
        secondary_y=True,
    )

    fig.add_trace(
        go.Scatter(
            x=df["observation_date"],
            y=df["10Y-3M"] * 100,
            mode="lines",
            name="10Y-3M",
            connectgaps=False,
        ),
        secondary_y=True,
    )

    fig.update_layout(
        title="Treasury Yield & Curve Spread",
    )

    fig.update_yaxes(
        title_text="Yield (%)",
        secondary_y=False,
    )

    fig.update_yaxes(
        title_text="Spread (bp)",
        secondary_y=True,
    )

    apply_chart_style(
        fig,
        compact_mode,
    )

    return fig


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

    # -----------------------------------------------------
    # Chart 1
    # -----------------------------------------------------

    st.subheader(
        "Fed Policy Rate & Money Market"
    )

    fig1 = build_fig1(
        start_date
    )

    show_chart(
        fig1
    )

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

    # -----------------------------------------------------
    # Chart 2
    # -----------------------------------------------------

    st.subheader(
        "10Y Yield Structure"
    )

    fig2 = build_fig2(
        start_date
    )

    show_chart(
        fig2
    )

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

    # -----------------------------------------------------
    # Chart 3
    # -----------------------------------------------------

    st.subheader(
        "Treasury Yield & Curve Spread"
    )

    fig3 = build_fig3(
        start_date
    )

    show_chart(
        fig3
    )

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
# RENDER CORE
# =========================================================

render_core_charts()


# =========================================================
# NEWS
# =========================================================

st.divider()

st.subheader(
    "📰 红字焦点财经快讯"
)

st.caption(
    "东方财富平台筛选的「红字焦点快讯」"
    " · 不进行自定义关键词筛选"
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
    # Refresh button
    # -----------------------------------------------------

    col1, col2 = st.columns(
        [1, 8]
    )

    with col1:

        refresh = st.button(
            "🔄 刷新",
            key="news_refresh",
            use_container_width=True,
        )

    if refresh:

        get_sina_news.clear()

        st.rerun(
            scope="fragment"
        )

    # -----------------------------------------------------
    # Get news
    # -----------------------------------------------------

    news_items, news_error = (
        get_sina_news(
            limit=50
        )
    )

    if news_error:

        st.error(
            news_error
        )

        st.markdown(
            "新闻源："
            + f"[东方财富焦点快讯]"
            f"({EASTMONEY_URL})"
        )

        return

    if not news_items:

        st.info(
            "当前没有取得焦点快讯。"
        )

        return

    # -----------------------------------------------------
    # Status
    # -----------------------------------------------------

    st.caption(
        f"当前显示 {len(news_items)} 条"
        " · 来源：东方财富红字焦点快讯"
    )

    # -----------------------------------------------------
    # News HTML
    # -----------------------------------------------------

    news_html = [
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

        url = html.escape(
            str(
                item.get(
                    "url",
                    EASTMONEY_URL,
                )
            ),
            quote=True,
        )

        if not url.startswith(
            (
                "http://",
                "https://",
            )
        ):
            url = EASTMONEY_URL

        # 如果标题和正文完全一样，
        # 不重复显示正文。
        show_content = (
            content
            and content != title
        )

        news_html.append(
            '<div class="news-item">'
        )

        news_html.append(
            '<span class="news-time">'
            + news_time
            + "</span>"
        )

        news_html.append(
            '<a class="news-title" '
            'href="'
            + url
            + '" '
            'target="_blank">'
            + title
            + "</a>"
        )

        if show_content:

            news_html.append(
                '<div class="news-content">'
                + content
                + "</div>"
            )

        news_html.append(
            "</div>"
        )

    news_html.append(
        "</div>"
    )

    st.html(
        "".join(
            news_html
        )
    )

    # -----------------------------------------------------
    # Source
    # -----------------------------------------------------

    st.html(
        '<div class="source-row">'
        '<a href="'
        + EASTMONEY_URL
        + '" target="_blank">'
        "Source: 东方财富焦点快讯"
        "</a>"
        "</div>"
    )


# =========================================================
# RENDER NEWS
# =========================================================

render_news_panel()
