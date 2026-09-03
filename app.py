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
# PAGE
# =========================================================

st.set_page_config(
    page_title="Macro Dashboard",
    page_icon="📊",
    layout="wide",
)


# =========================================================
# CONSTANTS
# =========================================================

# 东方财富红字焦点快讯页面
EASTMONEY_FOCUS_URL = "https://kuaixun.eastmoney.com/"


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

    html,
    body,
    [class*="css"] {
        font-family:
            "Noto Sans TC",
            "Noto Sans CJK TC",
            "Microsoft JhengHei",
            "PingFang TC",
            "Segoe UI",
            sans-serif;
    }

    .dashboard-title {
        font-size: 2rem;
        font-weight: 700;
        letter-spacing: -0.02em;
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
        letter-spacing: -0.01em;
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
        line-height: 1.5;
        margin: 2px 0 8px;
    }

    .source-text {
        color: #6b7280;
        font-size: 0.76rem;
        margin: 3px 0 12px;
        line-height: 1.5;
    }

    .source-text a {
        color: #6b7280;
        text-decoration: none !important;
        white-space: nowrap;
    }

    .source-text a:hover {
        color: #374151;
        text-decoration: underline !important;
    }

    .source-sep {
        color: #d1d5db;
        margin: 0 5px;
    }

    .chart-divider {
        margin: 1rem 0 1.5rem;
        border-top: 1px solid #e5e7eb;
    }

    .compact-title {
        font-size: 1rem;
        font-weight: 650;
        margin-bottom: 0.2rem;
    }

    .compact-description {
        color: #6b7280;
        font-size: 0.75rem;
        line-height: 1.4;
        margin-bottom: 0.25rem;
    }

    .news-status {
        color: #6b7280;
        font-size: 0.75rem;
        margin-bottom: 0.5rem;
    }

    .news-box {
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 6px 10px;
        background: #ffffff;
        max-height: 650px;
        overflow-y: auto;
    }

    .news-item {
        display: flex;
        align-items: flex-start;
        padding: 8px 3px;
        border-bottom: 1px solid #eeeeee;
        line-height: 1.5;
        font-size: 0.84rem;
    }

    .news-item:last-child {
        border-bottom: none;
    }

    .news-index {
        flex: 0 0 32px;
        width: 32px;
        color: #9ca3af;
        font-size: 0.72rem;
        font-family: "Segoe UI", sans-serif;
        padding-top: 2px;
    }

    .news-time {
        flex: 0 0 72px;
        width: 72px;
        color: #6b7280;
        font-size: 0.72rem;
        white-space: nowrap;
        padding-top: 2px;
        margin-right: 6px;
    }

    .news-content {
        flex: 1;
        min-width: 0;
    }

    .news-content a {
        color: #374151;
        text-decoration: none !important;
    }

    .news-content a:hover {
        color: #111827;
        text-decoration: none !important;
    }

    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# TITLE
# =========================================================

st.markdown(
    '<div class="dashboard-title">'
    "Macro Dashboard"
    "</div>",
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="dashboard-subtitle">'
    "US monetary policy, Treasury yields and inflation expectations"
    "</div>",
    unsafe_allow_html=True,
)


# =========================================================
# COMPACT MODE
# =========================================================

compact_mode = st.toggle(
    "缩小图表 / 快速浏览",
    value=True,
    help="开启后，三个核心图表横向并排显示。",
)


# =========================================================
# COMMON
# =========================================================

def get_start_date(
    range_name,
):

    today = (
        pd.Timestamp.today()
        .normalize()
    )

    offsets = {
        "5Y": pd.DateOffset(
            years=5
        ),
        "1Y": pd.DateOffset(
            years=1
        ),
        "6M": pd.DateOffset(
            months=6
        ),
        "3M": pd.DateOffset(
            months=3
        ),
        "1M": pd.DateOffset(
            months=1
        ),
    }

    return today - offsets.get(
        range_name,
        pd.DateOffset(
            years=1
        ),
    )


# =========================================================
# PLOTLY READ-ONLY CONFIG
# =========================================================

def plotly_readonly_config():

    return {
        # 不显示 Plotly 操作栏
        "displayModeBar": False,

        # 禁止滚轮缩放
        "scrollZoom": False,

        # 禁止双击操作
        "doubleClick": False,

        # 禁止编辑
        "editable": False,

        # 不显示 Plotly logo
        "displaylogo": False,
    }


def apply_chart_style(
    fig,
    height,
):

    fig.update_layout(
        height=height,
        template="plotly_white",

        # 鼠标停留：
        # 同一个日期同时显示所有曲线数据
        hovermode="x unified",

        # 禁止拖动
        dragmode=False,

        margin=dict(
            l=35,
            r=35,
            t=30,
            b=35,
        ),

        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.01,
            xanchor="left",
            x=0,
            font=dict(
                size=10
            ),
        ),

        hoverlabel=dict(
            bgcolor="white",
            font_size=11,
        ),

        font=dict(
            size=10
            if compact_mode
            else 12
        ),

        xaxis=dict(
            showgrid=False,
            showline=True,
            linecolor="#d1d5db",

            # X 轴固定
            fixedrange=True,

            # Hover 日期只显示 YYYY-MM-DD
            hoverformat="%Y-%m-%d",
        ),

        yaxis=dict(
            showgrid=True,
            gridcolor="#eeeeee",
            zeroline=False,

            # Y 轴固定
            fixedrange=True,
        ),
    )

    # 二次确保所有轴不能拖动/缩放
    fig.update_xaxes(
        fixedrange=True,
    )

    fig.update_yaxes(
        fixedrange=True,
    )

    return fig


def add_sources(
    sources,
):

    links = []

    for text, url in sources:

        safe_text = html.escape(
            text
        )

        safe_url = html.escape(
            url,
            quote=True,
        )

        links.append(
            f'<a href="{safe_url}" '
            f'target="_blank" '
            f'rel="noopener noreferrer">'
            f'{safe_text}'
            f'</a>'
        )

    st.markdown(
        '<div class="source-text">'
        "Source: "
        + '<span class="source-sep">|</span>'.join(
            links
        )
        + "</div>",
        unsafe_allow_html=True,
    )


# =========================================================
# CHART 1
# =========================================================

def build_fig1(
    date_range,
):

    corridor = (
        get_iorb()
        .merge(
            get_rrp_rate(),
            on="observation_date",
            how="outer",
        )
        .merge(
            get_effr(),
            on="observation_date",
            how="outer",
        )
        .merge(
            get_sofr(),
            on="observation_date",
            how="outer",
        )
        .sort_values(
            "observation_date"
        )
    )

    corridor = corridor[
        corridor[
            "observation_date"
        ]
        >= get_start_date(
            date_range
        )
    ]

    fig = go.Figure()

    for column, name, width in [
        (
            "IORB",
            "IORB",
            2.6,
        ),
        (
            "RRPONTSYAWARD",
            "ON RRP",
            2.6,
        ),
        (
            "EFFR",
            "EFFR",
            2.6,
        ),
        (
            "SOFR",
            "SOFR",
            2.2,
        ),
    ]:

        fig.add_trace(
            go.Scatter(
                x=corridor[
                    "observation_date"
                ],
                y=corridor[
                    column
                ],
                name=name,
                mode="lines",
                line=dict(
                    width=width
                ),
                hovertemplate=(
                    name
                    + ": %{y:.3f}%"
                    + "<extra></extra>"
                ),
            )
        )

    fig.update_layout(
        yaxis_title="Rate (%)"
    )

    return apply_chart_style(
        fig,
        190
        if compact_mode
        else 470,
    )


# =========================================================
# CHART 2
# =========================================================

def build_fig2(
    date_range,
):

    data = (
        get_dgs10()
        .merge(
            get_dfii10(),
            on="observation_date",
            how="inner",
        )
        .sort_values(
            "observation_date"
        )
    )

    data = data[
        data[
            "observation_date"
        ]
        >= get_start_date(
            date_range
        )
    ]

    data["Breakeven"] = (
        data["DGS10"]
        - data["DFII10"]
    )

    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=data[
                "observation_date"
            ],
            y=data[
                "DGS10"
            ],
            name="10Y Nominal",
            mode="lines",
            line=dict(
                width=2.8
            ),
            hovertemplate=(
                "10Y Nominal: %{y:.3f}%"
                "<extra></extra>"
            ),
        )
    )

    fig.add_trace(
        go.Scatter(
            x=data[
                "observation_date"
            ],
            y=data[
                "DFII10"
            ],
            name="10Y Real",
            mode="lines",
            line=dict(
                width=2.6
            ),
            hovertemplate=(
                "10Y Real: %{y:.3f}%"
                "<extra></extra>"
            ),
        )
    )

    fig.add_trace(
        go.Scatter(
            x=data[
                "observation_date"
            ],
            y=data[
                "Breakeven"
            ],
            name="10Y Breakeven",
            mode="lines",
            line=dict(
                width=2.5,
                dash="dot",
            ),
            hovertemplate=(
                "10Y Breakeven: %{y:.3f}%"
                "<extra></extra>"
            ),
        )
    )

    fig.update_layout(
        yaxis_title="Yield (%)"
    )

    return apply_chart_style(
        fig,
        190
        if compact_mode
        else 470,
    )


# =========================================================
# CHART 3
# =========================================================

def build_fig3(
    date_range,
):

    data = (
        get_dgs3mo()
        .merge(
            get_dgs2(),
            on="observation_date",
            how="outer",
        )
        .merge(
            get_dgs10(),
            on="observation_date",
            how="outer",
        )
        .sort_values(
            "observation_date"
        )
    )

    data = data[
        data[
            "observation_date"
        ]
        >= get_start_date(
            date_range
        )
    ]

    data["10Y-2Y"] = (
        data["DGS10"]
        - data["DGS2"]
    )

    data["10Y-3M"] = (
        data["DGS10"]
        - data["DGS3MO"]
    )

    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=data[
                "observation_date"
            ],
            y=data[
                "DGS3MO"
            ],
            name="3M",
            mode="lines",
            line=dict(
                width=2.2
            ),
            hovertemplate=(
                "3M: %{y:.3f}%"
                "<extra></extra>"
            ),
        )
    )

    fig.add_trace(
        go.Scatter(
            x=data[
                "observation_date"
            ],
            y=data[
                "DGS2"
            ],
            name="2Y",
            mode="lines",
            line=dict(
                width=2.4
            ),
            hovertemplate=(
                "2Y: %{y:.3f}%"
                "<extra></extra>"
            ),
        )
    )

    fig.add_trace(
        go.Scatter(
            x=data[
                "observation_date"
            ],
            y=data[
                "DGS10"
            ],
            name="10Y",
            mode="lines",
            line=dict(
                width=2.8
            ),
            hovertemplate=(
                "10Y: %{y:.3f}%"
                "<extra></extra>"
            ),
        )
    )

    fig.add_trace(
        go.Scatter(
            x=data[
                "observation_date"
            ],
            y=data[
                "10Y-2Y"
            ] * 100,
            name="10Y−2Y",
            mode="lines",
            line=dict(
                width=2.2,
                dash="dot",
            ),
            yaxis="y2",
            hovertemplate=(
                "10Y−2Y: %{y:.1f} bp"
                "<extra></extra>"
            ),
        )
    )

    fig.add_trace(
        go.Scatter(
            x=data[
                "observation_date"
            ],
            y=data[
                "10Y-3M"
            ] * 100,
            name="10Y−3M",
            mode="lines",
            line=dict(
                width=2.2,
                dash="dash",
            ),
            yaxis="y2",
            hovertemplate=(
                "10Y−3M: %{y:.1f} bp"
                "<extra></extra>"
            ),
        )
    )

    fig.update_layout(
        yaxis=dict(
            title="Yield (%)",
            fixedrange=True,
        ),
        yaxis2=dict(
            title="Spread (bp)",
            overlaying="y",
            side="right",
            showgrid=False,
            zeroline=True,
            zerolinecolor="#9ca3af",
            fixedrange=True,
        ),
    )

    return apply_chart_style(
        fig,
        200
        if compact_mode
        else 500,
    )


# =========================================================
# CORE CHARTS
# =========================================================

@st.fragment(
    run_every="3600s"
)
def render_core_charts():

    ranges = [
        "5Y",
        "1Y",
        "6M",
        "3M",
        "1M",
    ]

    if compact_mode:

        col1, col2, col3 = (
            st.columns(
                3,
                gap="small",
            )
        )

        # -------------------------------------------------
        # 1
        # -------------------------------------------------

        with col1:

            st.markdown(
                '<div class="compact-title">'
                "🏦 1. Fed Policy Rate"
                "</div>",
                unsafe_allow_html=True,
            )

            st.markdown(
                '<div class="compact-description">'
                "IORB / ON RRP / EFFR / SOFR"
                "</div>",
                unsafe_allow_html=True,
            )

            date_range = st.radio(
                "时间范围",
                ranges,
                horizontal=True,
                index=1,
                key="compact_corridor_range",
            )

            st.plotly_chart(
                build_fig1(
                    date_range
                ),
                use_container_width=True,
                config=plotly_readonly_config(),
            )

            add_sources(
                [
                    (
                        "IORB",
                        "https://fred.stlouisfed.org/series/IORB",
                    ),
                    (
                        "ON RRP",
                        "https://fred.stlouisfed.org/series/RRPONTSYAWARD",
                    ),
                    (
                        "EFFR",
                        "https://fred.stlouisfed.org/series/EFFR",
                    ),
                    (
                        "SOFR",
                        "https://fred.stlouisfed.org/series/SOFR",
                    ),
                ]
            )

        # -------------------------------------------------
        # 2
        # -------------------------------------------------

        with col2:

            st.markdown(
                '<div class="compact-title">'
                "2. 10Y Yield Structure"
                "</div>",
                unsafe_allow_html=True,
            )

            st.markdown(
                '<div class="compact-description">'
                "10Y Nominal / Real / Breakeven"
                "</div>",
                unsafe_allow_html=True,
            )

            date_range = st.radio(
                "时间范围",
                ranges,
                horizontal=True,
                index=1,
                key="compact_yield10_range",
            )

            st.plotly_chart(
                build_fig2(
                    date_range
                ),
                use_container_width=True,
                config=plotly_readonly_config(),
            )

            add_sources(
                [
                    (
                        "DGS10",
                        "https://fred.stlouisfed.org/series/DGS10",
                    ),
                    (
                        "DFII10",
                        "https://fred.stlouisfed.org/series/DFII10",
                    ),
                    (
                        "T10YIE",
                        "https://fred.stlouisfed.org/series/T10YIE",
                    ),
                ]
            )

        # -------------------------------------------------
        # 3
        # -------------------------------------------------

        with col3:

            st.markdown(
                '<div class="compact-title">'
                "3. Treasury Yield"
                "</div>",
                unsafe_allow_html=True,
            )

            st.markdown(
                '<div class="compact-description">'
                "3M / 2Y / 10Y / Curve Spread"
                "</div>",
                unsafe_allow_html=True,
            )

            date_range = st.radio(
                "时间范围",
                ranges,
                horizontal=True,
                index=1,
                key="compact_treasury_range",
            )

            st.plotly_chart(
                build_fig3(
                    date_range
                ),
                use_container_width=True,
                config=plotly_readonly_config(),
            )

            add_sources(
                [
                    (
                        "DGS3MO",
                        "https://fred.stlouisfed.org/series/DGS3MO",
                    ),
                    (
                        "DGS2",
                        "https://fred.stlouisfed.org/series/DGS2",
                    ),
                    (
                        "DGS10",
                        "https://fred.stlouisfed.org/series/DGS10",
                    ),
                    (
                        "T10Y2Y",
                        "https://fred.stlouisfed.org/series/T10Y2Y",
                    ),
                    (
                        "T10Y3M",
                        "https://fred.stlouisfed.org/series/T10Y3M",
                    ),
                ]
            )

    else:

        # -------------------------------------------------
        # 1
        # -------------------------------------------------

        st.markdown(
            '<div class="section-title">'
            "🏦 1. Fed Policy Rate & Money Market"
            "</div>",
            unsafe_allow_html=True,
        )

        st.markdown(
            '<div class="section-description">'
            "IORB、ON RRP Rate、EFFR 与 SOFR"
            "</div>",
            unsafe_allow_html=True,
        )

        date_range = st.radio(
            "时间范围",
            ranges,
            horizontal=True,
            index=1,
            key="normal_corridor_range",
        )

        st.plotly_chart(
            build_fig1(
                date_range
            ),
            use_container_width=True,
            config=plotly_readonly_config(),
        )

        add_sources(
            [
                (
                    "IORB",
                    "https://fred.stlouisfed.org/series/IORB",
                ),
                (
                    "ON RRP",
                    "https://fred.stlouisfed.org/series/RRPONTSYAWARD",
                ),
                (
                    "EFFR",
                    "https://fred.stlouisfed.org/series/EFFR",
                ),
                (
                    "SOFR",
                    "https://fred.stlouisfed.org/series/SOFR",
                ),
            ]
        )

        st.markdown(
            '<div class="chart-divider"></div>',
            unsafe_allow_html=True,
        )

        # -------------------------------------------------
        # 2
        # -------------------------------------------------

        st.markdown(
            '<div class="section-title">'
            "2. 10Y Yield Structure"
            "</div>",
            unsafe_allow_html=True,
        )

        st.markdown(
            '<div class="section-description">'
            "10Y Nominal / 10Y Real / 10Y Breakeven"
            "</div>",
            unsafe_allow_html=True,
        )

        date_range = st.radio(
            "时间范围",
            ranges,
            horizontal=True,
            index=1,
            key="normal_yield10_range",
        )

        st.plotly_chart(
            build_fig2(
                date_range
            ),
            use_container_width=True,
            config=plotly_readonly_config(),
        )

        add_sources(
            [
                (
                    "DGS10",
                    "https://fred.stlouisfed.org/series/DGS10",
                ),
                (
                    "DFII10",
                    "https://fred.stlouisfed.org/series/DFII10",
                ),
                (
                    "T10YIE",
                    "https://fred.stlouisfed.org/series/T10YIE",
                ),
            ]
        )

        st.markdown(
            '<div class="chart-divider"></div>',
            unsafe_allow_html=True,
        )

        # -------------------------------------------------
        # 3
        # -------------------------------------------------

        st.markdown(
            '<div class="section-title">'
            "3. Treasury Yield & Curve Spread"
            "</div>",
            unsafe_allow_html=True,
        )

        st.markdown(
            '<div class="section-description">'
            "3M、2Y、10Y Treasury Yield 与曲线利差"
            "</div>",
            unsafe_allow_html=True,
        )

        date_range = st.radio(
            "时间范围",
            ranges,
            horizontal=True,
            index=1,
            key="normal_treasury_range",
        )

        st.plotly_chart(
            build_fig3(
                date_range
            ),
            use_container_width=True,
            config=plotly_readonly_config(),
        )

        add_sources(
            [
                (
                    "DGS3MO",
                    "https://fred.stlouisfed.org/series/DGS3MO",
                ),
                (
                    "DGS2",
                    "https://fred.stlouisfed.org/series/DGS2",
                ),
                (
                    "DGS10",
                    "https://fred.stlouisfed.org/series/DGS10",
                ),
                (
                    "T10Y2Y",
                    "https://fred.stlouisfed.org/series/T10Y2Y",
                ),
                (
                    "T10Y3M",
                    "https://fred.stlouisfed.org/series/T10Y3M",
                ),
            ]
        )


render_core_charts()


# =========================================================
# NEWS
# =========================================================

st.markdown(
    '<div class="chart-divider"></div>',
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="section-title">'
    "📰 7×24 重点财经快讯"
    "</div>",
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="section-description">'
    "东方财富「红字焦点快讯」 · 平台已筛选重点 · 每60秒自动刷新"
    "</div>",
    unsafe_allow_html=True,
)


@st.fragment(
    run_every="60s"
)
def render_news_panel():

    col1, col2 = st.columns(
        [1, 5]
    )

    with col1:

        if st.button(
            "🔄 立即刷新",
            key="refresh_7x24",
            use_container_width=True,
        ):

            get_sina_news.clear()

            st.rerun()

    # data.py 已经固定：
    # type=101
    # = 东方财富红字焦点快讯
    news_items, news_error = (
        get_sina_news(
            limit=50
        )
    )

    if news_items:

        st.markdown(
            f'<div class="news-status">'
            f"当前显示 {len(news_items)} 条 · "
            f"来源：东方财富红字焦点快讯 · "
            f"60秒自动刷新"
            f"</div>",
            unsafe_allow_html=True,
        )

        news_html = (
            '<div class="news-box">'
        )

        for idx, item in enumerate(
            news_items,
            start=1,
        ):

            news_time = html.escape(
                str(
                    item.get(
                        "time",
                        "",
                    )
                )
            )

            news_title = html.escape(
                str(
                    item.get(
                        "title",
                        "",
                    )
                )
            )

            news_content = html.escape(
                str(
                    item.get(
                        "content",
                        "",
                    )
                )
            )

            news_url = html.escape(
                str(
                    item.get(
                        "url",
                        EASTMONEY_FOCUS_URL,
                    )
                ),
                quote=True,
            )

            if (
                not news_url.startswith(
                    "http://"
                )
                and not news_url.startswith(
                    "https://"
                )
            ):
                news_url = EASTMONEY_FOCUS_URL

            # 标题 + 完整正文都显示，不再只显示标题
            if (
                news_title
                and news_content
                and news_title
                != news_content
            ):

                body = (
                    f"<strong>"
                    f"{news_title}"
                    f"</strong>"
                    f"<div style=\"margin-top:3px;\">"
                    f"{news_content}"
                    f"</div>"
                )

            else:

                body = news_content or news_title

            news_html += f"""
            <div class="news-item">

                <span class="news-index">
                    {idx}.
                </span>

                <span class="news-time">
                    {news_time}
                </span>

                <div class="news-content">

                    <a
                        href="{news_url}"
                        target="_blank"
                        rel="noopener noreferrer"
                    >
                        {body}
                    </a>

                </div>

            </div>
            """

        news_html += (
            "</div>"
        )

        st.html(
            news_html
        )

    else:

        st.warning(
            "暂时无法取得东方财富红字焦点快讯。"
        )

        if news_error:

            st.caption(
                f"错误：{news_error}"
            )

    add_sources(
        [
            (
                "东方财富红字焦点快讯",
                EASTMONEY_FOCUS_URL,
            )
        ]
    )


render_news_panel()
