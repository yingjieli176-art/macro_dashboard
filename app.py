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
# Page Config
# =========================================================

st.set_page_config(
    page_title="Macro Dashboard",
    page_icon="📊",
    layout="wide",
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


    /* =====================================================
       Dashboard Header
       ===================================================== */

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


    /* =====================================================
       Section
       ===================================================== */

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
    }

    .source-text a {
        color: #6b7280;
        text-decoration: none;
    }

    .source-text a:hover {
        text-decoration: underline;
    }

    .chart-divider {
        margin: 1rem 0 1.5rem;
        border-top: 1px solid #e5e7eb;
    }


    /* =====================================================
       Compact Mode
       ===================================================== */

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


    /* =====================================================
       News
       ===================================================== */

    .news-status {
        color: #6b7280;
        font-size: 0.75rem;
        margin-bottom: 0.5rem;
    }

    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# Header
# =========================================================

st.markdown(
    '<div class="dashboard-title">Macro Dashboard</div>',
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="dashboard-subtitle">'
    'US monetary policy, Treasury yields and inflation expectations'
    '</div>',
    unsafe_allow_html=True,
)


# =========================================================
# Compact Mode
# 默认开启
# =========================================================

compact_mode = st.toggle(
    "缩小图表 / 快速浏览",
    value=True,
    help="开启后，三个核心图表横向并排显示。",
)


# =========================================================
# Helper Functions
# =========================================================

def get_start_date(range_name):

    today = pd.Timestamp.today().normalize()

    offsets = {
        "5Y": pd.DateOffset(years=5),
        "1Y": pd.DateOffset(years=1),
        "6M": pd.DateOffset(months=6),
        "3M": pd.DateOffset(months=3),
        "1M": pd.DateOffset(months=1),
    }

    return today - offsets.get(
        range_name,
        pd.DateOffset(years=1),
    )


def apply_chart_style(fig, height):

    fig.update_layout(
        height=height,
        template="plotly_white",
        hovermode="x unified",

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
            size=10 if compact_mode else 12
        ),

        xaxis=dict(
            showgrid=False,
            showline=True,
            linecolor="#d1d5db",
        ),

        yaxis=dict(
            showgrid=True,
            gridcolor="#eeeeee",
            zeroline=False,
        ),
    )

    return fig


def add_source(text, url):

    safe_text = html.escape(text)
    safe_url = html.escape(
        url,
        quote=True,
    )

    st.markdown(
        f"""
        <div class="source-text">
            Source:
            <a
                href="{safe_url}"
                target="_blank"
                rel="noopener noreferrer"
            >
                {safe_text}
            </a>
        </div>
        """,
        unsafe_allow_html=True,
    )


# =========================================================
# Build Chart 1
# =========================================================

def build_fig1(corridor_range):

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
        corridor["observation_date"]
        >= get_start_date(corridor_range)
    ]

    fig = go.Figure()

    for series_id, name, width in [
        ("IORB", "IORB", 2.6),
        (
            "RRPONTSYAWARD",
            "ON RRP",
            2.6,
        ),
        ("EFFR", "EFFR", 2.6),
        ("SOFR", "SOFR", 2.2),
    ]:

        fig.add_trace(
            go.Scatter(
                x=corridor[
                    "observation_date"
                ],
                y=corridor[
                    series_id
                ],
                name=name,
                mode="lines",
                line=dict(
                    width=width
                ),
            )
        )

    fig.update_layout(
        yaxis_title="Rate (%)"
    )

    apply_chart_style(
        fig,
        190 if compact_mode else 470,
    )

    return fig


# =========================================================
# Build Chart 2
# =========================================================

def build_fig2(yield10_range):

    yield10 = (
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

    yield10 = yield10[
        yield10["observation_date"]
        >= get_start_date(
            yield10_range
        )
    ]

    yield10["Breakeven"] = (
        yield10["DGS10"]
        - yield10["DFII10"]
    )

    fig = go.Figure()

    for col, name, width, dash in [
        (
            "DGS10",
            "10Y Nominal",
            2.8,
            None,
        ),
        (
            "DFII10",
            "10Y Real",
            2.6,
            None,
        ),
        (
            "Breakeven",
            "10Y Breakeven",
            2.5,
            "dot",
        ),
    ]:

        line = dict(
            width=width
        )

        if dash:
            line["dash"] = dash

        fig.add_trace(
            go.Scatter(
                x=yield10[
                    "observation_date"
                ],
                y=yield10[col],
                name=name,
                mode="lines",
                line=line,
            )
        )

    fig.update_layout(
        yaxis_title="Yield (%)"
    )

    apply_chart_style(
        fig,
        190 if compact_mode else 470,
    )

    return fig


# =========================================================
# Build Chart 3
# =========================================================

def build_fig3(treasury_range):

    treasury = (
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

    treasury = treasury[
        treasury["observation_date"]
        >= get_start_date(
            treasury_range
        )
    ]

    treasury["10Y-2Y"] = (
        treasury["DGS10"]
        - treasury["DGS2"]
    )

    treasury["10Y-3M"] = (
        treasury["DGS10"]
        - treasury["DGS3MO"]
    )

    fig = go.Figure()

    # 3M
    fig.add_trace(
        go.Scatter(
            x=treasury[
                "observation_date"
            ],
            y=treasury[
                "DGS3MO"
            ],
            name="3M",
            mode="lines",
            line=dict(
                width=2.2
            ),
        )
    )

    # 2Y
    fig.add_trace(
        go.Scatter(
            x=treasury[
                "observation_date"
            ],
            y=treasury[
                "DGS2"
            ],
            name="2Y",
            mode="lines",
            line=dict(
                width=2.4
            ),
        )
    )

    # 10Y
    fig.add_trace(
        go.Scatter(
            x=treasury[
                "observation_date"
            ],
            y=treasury[
                "DGS10"
            ],
            name="10Y",
            mode="lines",
            line=dict(
                width=2.8
            ),
        )
    )

    # 10Y - 2Y
    fig.add_trace(
        go.Scatter(
            x=treasury[
                "observation_date"
            ],
            y=treasury[
                "10Y-2Y"
            ] * 100,
            name="10Y−2Y",
            mode="lines",
            line=dict(
                width=2.2,
                dash="dot",
            ),
            yaxis="y2",
        )
    )

    # 10Y - 3M
    fig.add_trace(
        go.Scatter(
            x=treasury[
                "observation_date"
            ],
            y=treasury[
                "10Y-3M"
            ] * 100,
            name="10Y−3M",
            mode="lines",
            line=dict(
                width=2.2,
                dash="dash",
            ),
            yaxis="y2",
        )
    )

    fig.update_layout(
        yaxis=dict(
            title="Yield (%)"
        ),

        yaxis2=dict(
            title="Spread (bp)",
            overlaying="y",
            side="right",
            showgrid=False,
            zeroline=True,
            zerolinecolor="#9ca3af",
        ),
    )

    apply_chart_style(
        fig,
        200 if compact_mode else 500,
    )

    return fig


# =========================================================
# CORE CHARTS
# =========================================================

if compact_mode:

    # =====================================================
    # COMPACT MODE
    #
    # 每个 column 完整对应一个 chart
    #
    # Column 1:
    # 1 + 时间范围 + Fig1
    #
    # Column 2:
    # 2 + 时间范围 + Fig2
    #
    # Column 3:
    # 3 + 时间范围 + Fig3
    # =====================================================

    col1, col2, col3 = st.columns(
        3,
        gap="small",
    )


    # =====================================================
    # 1. Fed
    # =====================================================

    with col1:

        st.markdown(
            '<div class="compact-title">'
            '🏦 1. Fed Policy Rate'
            '</div>',
            unsafe_allow_html=True,
        )

        st.markdown(
            '<div class="compact-description">'
            'IORB / ON RRP / EFFR / SOFR'
            '</div>',
            unsafe_allow_html=True,
        )

        corridor_range = st.radio(
            "时间范围",
            [
                "5Y",
                "1Y",
                "6M",
                "3M",
                "1M",
            ],
            horizontal=True,
            index=1,
            key="compact_corridor_range",
        )

        fig1 = build_fig1(
            corridor_range
        )

        st.plotly_chart(
            fig1,
            use_container_width=True,
        )

        st.caption(
            "政策利率走廊 / 货币市场利率"
        )


    # =====================================================
    # 2. 10Y
    # =====================================================

    with col2:

        st.markdown(
            '<div class="compact-title">'
            '2. 10Y Yield Structure'
            '</div>',
            unsafe_allow_html=True,
        )

        st.markdown(
            '<div class="compact-description">'
            '10Y Nominal / Real / Breakeven'
            '</div>',
            unsafe_allow_html=True,
        )

        yield10_range = st.radio(
            "时间范围",
            [
                "5Y",
                "1Y",
                "6M",
                "3M",
                "1M",
            ],
            horizontal=True,
            index=1,
            key="compact_yield10_range",
        )

        fig2 = build_fig2(
            yield10_range
        )

        st.plotly_chart(
            fig2,
            use_container_width=True,
        )

        st.caption(
            "名义利率 / 实际利率 / 通胀预期"
        )


    # =====================================================
    # 3. Treasury
    # =====================================================

    with col3:

        st.markdown(
            '<div class="compact-title">'
            '3. Treasury Yield'
            '</div>',
            unsafe_allow_html=True,
        )

        st.markdown(
            '<div class="compact-description">'
            '3M / 2Y / 10Y / Curve Spread'
            '</div>',
            unsafe_allow_html=True,
        )

        treasury_range = st.radio(
            "时间范围",
            [
                "5Y",
                "1Y",
                "6M",
                "3M",
                "1M",
            ],
            horizontal=True,
            index=1,
            key="compact_treasury_range",
        )

        fig3 = build_fig3(
            treasury_range
        )

        st.plotly_chart(
            fig3,
            use_container_width=True,
        )

        st.caption(
            "3M / 2Y / 10Y / 10Y−2Y / 10Y−3M"
        )


else:

    # =====================================================
    # NORMAL MODE
    #
    # 严格：
    # 标题1 → 时间1 → 图1
    # 标题2 → 时间2 → 图2
    # 标题3 → 时间3 → 图3
    # =====================================================


    # =====================================================
    # 1. Fed Policy Rate
    # =====================================================

    st.markdown(
        '<div class="section-title">'
        '🏦 1. Fed Policy Rate & Money Market'
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="section-description">'
        'IORB、ON RRP Rate、EFFR 与 SOFR'
        '</div>',
        unsafe_allow_html=True,
    )

    corridor_range = st.radio(
        "时间范围",
        [
            "5Y",
            "1Y",
            "6M",
            "3M",
            "1M",
        ],
        horizontal=True,
        index=1,
        key="normal_corridor_range",
    )

    fig1 = build_fig1(
        corridor_range
    )

    st.plotly_chart(
        fig1,
        use_container_width=True,
    )

    st.markdown(
        '<div class="mini-description">'
        'IORB / ON RRP构成政策利率走廊，'
        'EFFR观察联邦基金市场，'
        'SOFR观察隔夜担保融资。'
        '</div>',
        unsafe_allow_html=True,
    )

    add_source(
        "FRED — Policy Rate Corridor",
        "https://fred.stlouisfed.org/graph/?graph_id=1547733&rn=698",
    )


    # =====================================================
    # Divider
    # =====================================================

    st.markdown(
        '<div class="chart-divider"></div>',
        unsafe_allow_html=True,
    )


    # =====================================================
    # 2. 10Y Yield Structure
    # =====================================================

    st.markdown(
        '<div class="section-title">'
        '2. 10Y Yield Structure'
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="section-description">'
        '10Y Nominal / 10Y Real / 10Y Breakeven'
        '</div>',
        unsafe_allow_html=True,
    )

    yield10_range = st.radio(
        "时间范围",
        [
            "5Y",
            "1Y",
            "6M",
            "3M",
            "1M",
        ],
        horizontal=True,
        index=1,
        key="normal_yield10_range",
    )

    fig2 = build_fig2(
        yield10_range
    )

    st.plotly_chart(
        fig2,
        use_container_width=True,
    )

    st.markdown(
        '<div class="mini-description">'
        '10Y Breakeven = 10Y Nominal − 10Y Real，'
        '用于观察市场隐含通胀预期。'
        '</div>',
        unsafe_allow_html=True,
    )

    add_source(
        "FRED — Treasury & Real Yield Data",
        "https://fred.stlouisfed.org/",
    )


    # =====================================================
    # Divider
    # =====================================================

    st.markdown(
        '<div class="chart-divider"></div>',
        unsafe_allow_html=True,
    )


    # =====================================================
    # 3. Treasury Yield
    # =====================================================

    st.markdown(
        '<div class="section-title">'
        '3. Treasury Yield & Curve Spread'
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="section-description">'
        '3M、2Y、10Y Treasury Yield 与曲线利差'
        '</div>',
        unsafe_allow_html=True,
    )

    treasury_range = st.radio(
        "时间范围",
        [
            "5Y",
            "1Y",
            "6M",
            "3M",
            "1M",
        ],
        horizontal=True,
        index=1,
        key="normal_treasury_range",
    )

    fig3 = build_fig3(
        treasury_range
    )

    st.plotly_chart(
        fig3,
        use_container_width=True,
    )

    st.markdown(
        '<div class="mini-description">'
        '曲线斜率：10Y−2Y、10Y−3M；'
        '正值代表正常向上倾斜，负值代表倒挂。'
        '</div>',
        unsafe_allow_html=True,
    )

    add_source(
        "FRED — Treasury Constant Maturity Rates",
        "https://fred.stlouisfed.org/",
    )


# =========================================================
# 7×24 MARKET NEWS
# =========================================================

st.markdown(
    '<div class="chart-divider"></div>',
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="section-title">'
    '📰 7×24 Market News'
    '</div>',
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="section-description">'
    '实时财经文字快讯 · 每 60 秒自动刷新'
    '</div>',
    unsafe_allow_html=True,
)


# =========================================================
# News Panel
# =========================================================

@st.fragment(run_every="60s")
def render_news_panel():

    # -----------------------------------------------------
    # Refresh Button
    # -----------------------------------------------------

    if st.button(
        "🔄 立即刷新7×24",
        key="refresh_7x24",
    ):
        get_sina_news.clear()

    # -----------------------------------------------------
    # Get News
    # -----------------------------------------------------

    sina_news, sina_error = get_sina_news(
        limit=20
    )

    # -----------------------------------------------------
    # News Result
    # -----------------------------------------------------

    if sina_news:

        st.markdown(
            f"""
            <div class="news-status">
                最新 {len(sina_news)} 条 · 自动刷新中
            </div>
            """,
            unsafe_allow_html=True,
        )

        # -------------------------------------------------
        # IMPORTANT
        #
        # 新闻这里完全不使用：
        # <span>
        # <div>
        # <a>
        #
        # 避免 Streamlit 把 HTML 原始代码显示出来。
        # -------------------------------------------------

        for idx, item in enumerate(
            sina_news,
            start=1,
        ):

            news_time = str(
                item.get(
                    "time",
                    "",
                )
            ).strip()

            news_title = str(
                item.get(
                    "title",
                    "",
                )
            ).strip()

            news_url = str(
                item.get(
                    "url",
                    "",
                )
            ).strip()

            # -------------------------------------------------
            # 使用 Streamlit 原生 Markdown
            # -------------------------------------------------

            if news_url:

                st.markdown(
                    f"{idx}. **{news_time}**  "
                    f"[{news_title}]({news_url})"
                )

            else:

                st.markdown(
                    f"{idx}. **{news_time}**  "
                    f"{news_title}"
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
        "https://finance.sina.com.cn/7x24/",
    )


render_news_panel()
