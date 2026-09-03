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
# Page config
# =========================================================

st.set_page_config(
    page_title="Macro Dashboard",
    page_icon="📊",
    layout="wide",
)


# =========================================================
# Global CSS
# =========================================================

st.markdown(
    """
<style>

/* =======================================================
   Global font
   ======================================================= */

html,
body,
[class*="css"],
.stApp,
button,
input,
textarea,
select {

    font-family:
        "Noto Sans TC",
        "Noto Sans CJK TC",
        "Microsoft JhengHei",
        "PingFang TC",
        "Segoe UI",
        sans-serif !important;
}


/* =======================================================
   Layout
   ======================================================= */

.block-container {
    padding-top: 1.8rem;
    padding-bottom: 3rem;
    max-width: 1400px;
}


/* =======================================================
   Dashboard title
   ======================================================= */

.dashboard-title {
    font-size: 2rem;
    font-weight: 750;
    letter-spacing: -0.5px;
    margin-bottom: 3px;
}

.dashboard-subtitle {
    font-size: 0.92rem;
    color: #6b7280;
    margin-bottom: 1.1rem;
}


/* =======================================================
   Section
   ======================================================= */

.section-title {
    font-size: 1.3rem;
    font-weight: 700;
    letter-spacing: -0.2px;
    margin-top: 0.8rem;
    margin-bottom: 0.15rem;
}

.section-description {
    font-size: 0.86rem;
    color: #6b7280;
    margin-bottom: 0.45rem;
}


/* =======================================================
   Description
   ======================================================= */

.mini-description {
    font-size: 0.78rem;
    line-height: 1.55;
    color: #6b7280;
    margin: 2px 0 8px;
}


/* =======================================================
   Source
   ======================================================= */

.source-text {
    font-size: 0.74rem;
    color: #9ca3af;
    margin: 3px 0 12px;
}

.source-text a {
    color: #6b7280;
    text-decoration: none;
}

.source-text a:hover {
    text-decoration: underline;
}


/* =======================================================
   Divider
   ======================================================= */

.chart-divider {
    margin: 1.3rem 0 1.6rem;
    border-top: 1px solid #e5e7eb;
}


/* =======================================================
   News
   ======================================================= */

.news-box {
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    padding: 6px 12px;
    background: #ffffff;
    max-height: 560px;
    overflow-y: auto;
}

.news-item {
    padding: 8px 3px;
    border-bottom: 1px solid #eeeeee;
    line-height: 1.5;
    font-size: 0.85rem;
}

.news-item:last-child {
    border-bottom: none;
}

.news-item a {
    color: #1f2937;
    text-decoration: none;
}

.news-item a:hover {
    color: #2563eb;
    text-decoration: underline;
}

.news-time {
    color: #6b7280;
    font-size: 0.72rem;
    margin-right: 8px;
    white-space: nowrap;
    font-family:
        "Segoe UI",
        "Noto Sans TC",
        sans-serif;
}

.news-status {
    color: #6b7280;
    font-size: 0.74rem;
    margin-bottom: 6px;
}


/* =======================================================
   Mobile
   ======================================================= */

@media (max-width: 768px) {

    .dashboard-title {
        font-size: 1.65rem;
    }

    .section-title {
        font-size: 1.15rem;
    }

    .news-item {
        font-size: 0.82rem;
    }
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
    """
    <div class="dashboard-subtitle">
        US monetary policy, Treasury yields and inflation expectations
    </div>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# Display mode
# =========================================================

compact_mode = st.toggle(
    "缩小图表 / 快速浏览",
    value=False,
    help="开启后，三个核心图表横向并排显示。",
)


# =========================================================
# Helper
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
            l=45,
            r=45,
            t=25,
            b=40,
        ),

        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.01,
            xanchor="left",
            x=0,
            font=dict(
                size=10 if compact_mode else 11
            ),
        ),

        hoverlabel=dict(
            bgcolor="white",
            font_size=11,
        ),

        font=dict(
            family=(
                "Noto Sans TC, "
                "Noto Sans CJK TC, "
                "Microsoft JhengHei, "
                "PingFang TC, "
                "sans-serif"
            ),
            size=10 if compact_mode else 12,
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

    st.markdown(
        f"""
        <div class="source-text">
            Source:
            <a href="{url}" target="_blank">
                {safe_text}
            </a>
        </div>
        """,
        unsafe_allow_html=True,
    )


# =========================================================
# =========================================================
# 1. Fed Policy Rate & Money Market
# =========================================================
# =========================================================

st.markdown(
    '<div class="section-title">1. Fed Policy Rate & Money Market</div>',
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="section-description">
        IORB、ON RRP Rate、EFFR 与 SOFR
    </div>
    """,
    unsafe_allow_html=True,
)

corridor_range = st.radio(
    "时间范围",
    ["5Y", "1Y", "6M", "3M", "1M"],
    horizontal=True,
    index=1,
    key="corridor_range",
)


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
    .sort_values("observation_date")
)

corridor = corridor[
    corridor["observation_date"]
    >= get_start_date(corridor_range)
]


fig1 = go.Figure()

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

    fig1.add_trace(
        go.Scatter(
            x=corridor["observation_date"],
            y=corridor[series_id],
            name=name,
            mode="lines",
            line=dict(width=width),
        )
    )


fig1.update_layout(
    yaxis_title="Rate (%)"
)

apply_chart_style(
    fig1,
    190 if compact_mode else 470,
)


# =========================================================
# 2. 10Y Yield Structure
# =========================================================

st.markdown(
    '<div class="section-title">2. 10Y Yield Structure</div>',
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="section-description">
        10Y Nominal / 10Y Real / 10Y Breakeven
    </div>
    """,
    unsafe_allow_html=True,
)

yield10_range = st.radio(
    "时间范围",
    ["5Y", "1Y", "6M", "3M", "1M"],
    horizontal=True,
    index=1,
    key="yield10_range",
)


yield10 = (
    get_dgs10()
    .merge(
        get_dfii10(),
        on="observation_date",
        how="inner",
    )
    .sort_values("observation_date")
)

yield10 = yield10[
    yield10["observation_date"]
    >= get_start_date(yield10_range)
]

yield10["Breakeven"] = (
    yield10["DGS10"]
    - yield10["DFII10"]
)


fig2 = go.Figure()

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

    line = {
        "width": width
    }

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


fig2.update_layout(
    yaxis_title="Yield (%)"
)

apply_chart_style(
    fig2,
    190 if compact_mode else 470,
)


# =========================================================
# 3. Treasury Yield & Curve Spread
# =========================================================

st.markdown(
    '<div class="section-title">3. Treasury Yield & Curve Spread</div>',
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="section-description">
        3M、2Y、10Y Treasury Yield 与曲线利差
    </div>
    """,
    unsafe_allow_html=True,
)

treasury_range = st.radio(
    "时间范围",
    ["5Y", "1Y", "6M", "3M", "1M"],
    horizontal=True,
    index=1,
    key="treasury_range",
)


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
    .sort_values("observation_date")
)

treasury = treasury[
    treasury["observation_date"]
    >= get_start_date(treasury_range)
]

treasury["10Y-2Y"] = (
    treasury["DGS10"]
    - treasury["DGS2"]
)

treasury["10Y-3M"] = (
    treasury["DGS10"]
    - treasury["DGS3MO"]
)


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
        line=dict(
            width=2.2,
            dash="dot",
        ),
        yaxis="y2",
    )
)


fig3.add_trace(
    go.Scatter(
        x=treasury["observation_date"],
        y=treasury["10Y-3M"] * 100,
        name="10Y−3M",
        mode="lines",
        line=dict(
            width=2.2,
            dash="dash",
        ),
        yaxis="y2",
    )
)


fig3.update_layout(
    yaxis=dict(
        title="Yield (%)",
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
    fig3,
    200 if compact_mode else 500,
)


# =========================================================
# Chart display
#
# 注意：
# 1 / 2 / 3 现在和 fig1 / fig2 / fig3 一一对应。
# =========================================================

if compact_mode:

    chart_col1, chart_col2, chart_col3 = st.columns(
        3,
        gap="small",
    )

    with chart_col1:

        st.markdown(
            "**1. Fed Policy Rate & Money Market**"
        )

        st.plotly_chart(
            fig1,
            use_container_width=True,
        )

        st.caption(
            "IORB / ON RRP / EFFR / SOFR"
        )

        add_source(
            "FRED",
            "https://fred.stlouisfed.org/",
        )


    with chart_col2:

        st.markdown(
            "**2. 10Y Yield Structure**"
        )

        st.plotly_chart(
            fig2,
            use_container_width=True,
        )

        st.caption(
            "10Y Nominal / Real / Breakeven"
        )

        add_source(
            "FRED",
            "https://fred.stlouisfed.org/",
        )


    with chart_col3:

        st.markdown(
            "**3. Treasury Yield & Curve Spread**"
        )

        st.plotly_chart(
            fig3,
            use_container_width=True,
        )

        st.caption(
            "3M / 2Y / 10Y / 10Y−2Y / 10Y−3M"
        )

        add_source(
            "FRED",
            "https://fred.stlouisfed.org/",
        )


else:

    # -----------------------------------------------------
    # Chart 1
    # -----------------------------------------------------

    st.plotly_chart(
        fig1,
        use_container_width=True,
    )

    st.markdown(
        """
        <div class="mini-description">
            IORB / ON RRP 构成政策利率走廊，
            EFFR 观察联邦基金市场，
            SOFR 观察隔夜担保融资。
        </div>
        """,
        unsafe_allow_html=True,
    )

    add_source(
        "FRED — Policy Rate Corridor",
        "https://fred.stlouisfed.org/",
    )


    st.markdown(
        '<div class="chart-divider"></div>',
        unsafe_allow_html=True,
    )


    # -----------------------------------------------------
    # Chart 2
    # -----------------------------------------------------

    st.plotly_chart(
        fig2,
        use_container_width=True,
    )

    st.markdown(
        """
        <div class="mini-description">
            10Y Breakeven = 10Y Nominal − 10Y Real，
            用于观察市场隐含通胀预期。
        </div>
        """,
        unsafe_allow_html=True,
    )

    add_source(
        "FRED — Treasury & Real Yield Data",
        "https://fred.stlouisfed.org/",
    )


    st.markdown(
        '<div class="chart-divider"></div>',
        unsafe_allow_html=True,
    )


    # -----------------------------------------------------
    # Chart 3
    # -----------------------------------------------------

    st.plotly_chart(
        fig3,
        use_container_width=True,
    )

    st.markdown(
        """
        <div class="mini-description">
            曲线斜率：10Y−2Y、10Y−3M；
            正值代表正常向上倾斜，
            负值代表倒挂。
        </div>
        """,
        unsafe_allow_html=True,
    )

    add_source(
        "FRED — Treasury Constant Maturity Rates",
        "https://fred.stlouisfed.org/",
    )


# =========================================================
# 7×24 Market News
# =========================================================

st.markdown(
    '<div class="chart-divider"></div>',
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="section-title">📰 7×24 Market News</div>',
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="section-description">
        实时财经文字快讯 · 每 60 秒自动刷新
    </div>
    """,
    unsafe_allow_html=True,
)


@st.fragment(run_every="60s")
def render_news_panel():

    if st.button(
        "🔄 立即刷新 7×24",
        key="refresh_7x24",
    ):
        get_sina_news.clear()
        st.rerun()


    news, news_error = get_sina_news(
        limit=30
    )


    st.markdown(
        "#### 新浪财经 7×24"
    )


    if news:

        st.markdown(
            f"""
            <div class="news-status">
                最新 {len(news)} 条 · 自动刷新中
            </div>
            """,
            unsafe_allow_html=True,
        )


        st.markdown(
            '<div class="news-box">',
            unsafe_allow_html=True,
        )


        # -------------------------------------------------
        # 新闻编号在这里生成
        # -------------------------------------------------
        # 注意：
        # 图表目前没有使用新闻编号，因此不会再产生
        # 新闻列表与两个新闻源之间的错位问题。
        # -------------------------------------------------

        for index, item in enumerate(
            news,
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

            news_url = html.escape(
                str(
                    item.get(
                        "url",
                        "",
                    )
                )
            )


            st.markdown(
                f"""
                <div class="news-item">

                    <span
                        style="
                            display:inline-block;
                            width:25px;
                            color:#9ca3af;
                            font-size:.72rem;
                            font-family:
                                'Segoe UI',
                                sans-serif;
                        "
                    >
                        {index}.
                    </span>

                    <span class="news-time">
                        {news_time}
                    </span>

                    <a
                        href="{news_url}"
                        target="_blank"
                        rel="noopener noreferrer"
                    >
                        {news_title}
                    </a>

                </div>
                """,
                unsafe_allow_html=True,
            )


        st.markdown(
            "</div>",
            unsafe_allow_html=True,
        )


    else:

        st.warning(
            "7×24 新闻暂时无法获取。"
        )

        if news_error:

            st.caption(
                f"错误：{news_error}"
            )


    add_source(
        "新浪财经 7×24",
        "https://finance.sina.com.cn/7x24/",
    )


render_news_panel()
