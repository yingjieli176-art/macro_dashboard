import streamlit as st
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
        padding-top: 2rem;
        padding-bottom: 4rem;
        max-width: 1400px;
    }

    .dashboard-title {
        font-size: 2rem;
        font-weight: 700;
        margin-bottom: 0.2rem;
    }

    .dashboard-subtitle {
        color: #6b7280;
        font-size: 0.95rem;
        margin-bottom: 1.2rem;
    }

    .section-title {
        font-size: 1.35rem;
        font-weight: 650;
        margin-top: 1rem;
        margin-bottom: 0.15rem;
    }

    .section-description {
        color: #6b7280;
        font-size: 0.9rem;
        margin-bottom: 0.5rem;
    }

    .formula-box {
        background: #f8fafc;
        border-left: 4px solid #64748b;
        padding: 10px 14px;
        margin-top: 5px;
        margin-bottom: 8px;
        font-size: 0.86rem;
        line-height: 1.6;
    }

    .parameter-box {
        background: #fafafa;
        border: 1px solid #e5e7eb;
        border-radius: 6px;
        padding: 10px 14px;
        margin-top: 8px;
        margin-bottom: 28px;
        font-size: 0.82rem;
        line-height: 1.65;
        color: #4b5563;
    }

    .source-text {
        color: #6b7280;
        font-size: 0.78rem;
        margin-top: 4px;
        margin-bottom: 18px;
    }

    .chart-divider {
        margin-top: 1rem;
        margin-bottom: 2rem;
        border-top: 1px solid #e5e7eb;
    }

    .news-item {
        padding: 7px 4px;
        border-bottom: 1px solid #eeeeee;
        line-height: 1.45;
        font-size: 0.88rem;
    }

    .news-time {
        color: #6b7280;
        font-size: 0.78rem;
        margin-right: 10px;
        white-space: nowrap;
    }

    .news-source {
        color: #9ca3af;
        font-size: 0.72rem;
        margin-top: 2px;
    }

    </style>
    """,
    unsafe_allow_html=True
)


# =========================================================
# Header
# =========================================================

st.markdown(
    '<div class="dashboard-title">Macro Dashboard</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="dashboard-subtitle">'
    'US monetary policy, Treasury yields and inflation expectations'
    '</div>',
    unsafe_allow_html=True
)


# =========================================================
# Detail Mode
# =========================================================

detail_mode = st.toggle(
    "展开详细说明",
    value=False,
    help="开启后显示计算公式、参数中文释义和经济含义。"
)


# =========================================================
# Helper Functions
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


def apply_chart_style(fig, height=470):

    fig.update_layout(
        height=height,
        template="plotly_white",
        hovermode="x unified",

        margin=dict(
            l=55,
            r=70,
            t=55,
            b=50
        ),

        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0
        ),

        hoverlabel=dict(
            bgcolor="white",
            font_size=13
        ),

        font=dict(
            size=13
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
                {text}
            </a>
        </div>
        """,
        unsafe_allow_html=True
    )


def add_parameter_notes(html_text):

    if detail_mode:

        st.markdown(
            f"""
            <div class="parameter-box">
                <b>参数备注 / 中文释义</b><br>
                {html_text}
            </div>
            """,
            unsafe_allow_html=True
        )


def add_formula(html_text):

    if detail_mode:

        st.markdown(
            f"""
            <div class="formula-box">
                {html_text}
            </div>
            """,
            unsafe_allow_html=True
        )


# =========================================================
# 1. Policy Rate Corridor
# =========================================================

st.markdown(
    '<div class="section-title">1. Policy Rate Corridor</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="section-description">'
    '政策利率走廊：IORB、ON RRP Rate、EFFR 与 SOFR'
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


fig1.add_trace(
    go.Scatter(
        x=corridor["observation_date"],
        y=corridor["IORB"],
        name="IORB",
        mode="lines",
        line=dict(width=2.8)
    )
)


fig1.add_trace(
    go.Scatter(
        x=corridor["observation_date"],
        y=corridor["RRPONTSYAWARD"],
        name="ON RRP",
        mode="lines",
        line=dict(width=2.8)
    )
)


fig1.add_trace(
    go.Scatter(
        x=corridor["observation_date"],
        y=corridor["EFFR"],
        name="EFFR",
        mode="lines",
        line=dict(width=2.8)
    )
)


fig1.add_trace(
    go.Scatter(
        x=corridor["observation_date"],
        y=corridor["SOFR"],
        name="SOFR",
        mode="lines",
        line=dict(width=2.2)
    )
)


fig1.update_layout(
    yaxis_title="Interest Rate (%)"
)


fig1 = apply_chart_style(
    fig1,
    470
)


st.plotly_chart(
    fig1,
    use_container_width=True
)


add_parameter_notes(
    """
    <b>IORB</b>：Interest on Reserve Balances，准备金余额利率。<br>
    <b>ON RRP</b>：Overnight Reverse Repurchase Agreement Rate，隔夜逆回购利率。<br>
    <b>EFFR</b>：Effective Federal Funds Rate，联邦基金有效利率。<br>
    <b>SOFR</b>：Secured Overnight Financing Rate，有担保隔夜融资利率。<br>
    <b>单位</b>：全部为 %
    """
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
    '<div class="section-title">2. 10Y Yield Structure</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="section-description">'
    '10年期名义收益率、实际收益率与盈亏平衡通胀率'
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
        line=dict(width=2.8)
    )
)


fig2.add_trace(
    go.Scatter(
        x=yield10["observation_date"],
        y=yield10["Breakeven"],
        name="10Y Breakeven",
        mode="lines",
        line=dict(
            width=2.8,
            dash="dot"
        )
    )
)


fig2.update_layout(
    yaxis_title="Yield / Inflation (%)"
)


fig2 = apply_chart_style(
    fig2,
    470
)


st.plotly_chart(
    fig2,
    use_container_width=True
)


add_formula(
    """
    <b>10Y Breakeven = 10Y Nominal − 10Y Real</b><br>
    即：<b>DGS10 − DFII10</b>
    """
)


add_parameter_notes(
    """
    <b>DGS10</b>：美国10年期国债名义收益率。<br>
    <b>DFII10</b>：美国10年期TIPS实际收益率。<br>
    <b>10Y Breakeven</b>：10年期盈亏平衡通胀率。<br>
    <b>注意</b>：Breakeven不等于纯粹的市场通胀预期，
    还可能包含通胀风险溢价及流动性等因素。
    """
)


add_source(
    "FRED — 10Y Nominal / Real Yield",
    "https://fred.stlouisfed.org/graph/?id=DGS10%2CDFII10"
)


st.markdown(
    '<div class="chart-divider"></div>',
    unsafe_allow_html=True
)


# =========================================================
# 3. Treasury Yield & Curve Spread
# =========================================================

st.markdown(
    '<div class="section-title">3. Treasury Yield & Curve Spread</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="section-description">'
    '3个月、2年、10年美国国债收益率，以及10Y−2Y与10Y−3M期限利差'
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


# =========================================================
# Calculate Spreads
# =========================================================

treasury["10Y-2Y"] = (
    treasury["DGS10"]
    - treasury["DGS2"]
) * 100


treasury["10Y-3M"] = (
    treasury["DGS10"]
    - treasury["DGS3MO"]
) * 100


# =========================================================
# Chart
# =========================================================

fig3 = go.Figure()


# 3M
fig3.add_trace(
    go.Scatter(
        x=treasury["observation_date"],
        y=treasury["DGS3MO"],
        name="3M",
        mode="lines",
        line=dict(width=2.2),
        yaxis="y"
    )
)


# 2Y
fig3.add_trace(
    go.Scatter(
        x=treasury["observation_date"],
        y=treasury["DGS2"],
        name="2Y",
        mode="lines",
        line=dict(width=2.4),
        yaxis="y"
    )
)


# 10Y
fig3.add_trace(
    go.Scatter(
        x=treasury["observation_date"],
        y=treasury["DGS10"],
        name="10Y",
        mode="lines",
        line=dict(width=2.8),
        yaxis="y"
    )
)


# 10Y−2Y
fig3.add_trace(
    go.Bar(
        x=treasury["observation_date"],
        y=treasury["10Y-2Y"],
        name="10Y−2Y",
        opacity=0.58,
        yaxis="y2"
    )
)


# 10Y−3M
fig3.add_trace(
    go.Bar(
        x=treasury["observation_date"],
        y=treasury["10Y-3M"],
        name="10Y−3M",
        opacity=0.42,
        yaxis="y2"
    )
)


fig3.update_layout(

    yaxis=dict(
        title="Treasury Yield (%)",
        showgrid=True,
        gridcolor="#eeeeee",
        zeroline=False
    ),

    yaxis2=dict(
        title="Spread (bp)",
        overlaying="y",
        side="right",
        zeroline=True,
        zerolinecolor="#666666",
        zerolinewidth=1
    ),

    barmode="group"
)


fig3 = apply_chart_style(
    fig3,
    500
)


st.plotly_chart(
    fig3,
    use_container_width=True
)


add_formula(
    """
    <b>10Y−2Y = DGS10 − DGS2</b><br>
    <b>10Y−3M = DGS10 − DGS3MO</b><br><br>

    <b>单位：</b>bp（基点）<br>
    1个百分点 = 100 bp
    """
)


add_parameter_notes(
    """
    <b>DGS3MO</b>：美国3个月国债收益率，
    对当前货币政策和短端资金利率环境较敏感。<br>

    <b>DGS2</b>：美国2年期国债收益率，
    对未来短期政策利率路径预期较敏感。<br>

    <b>DGS10</b>：美国10年期国债收益率，
    是长期无风险利率的重要基准。<br>

    <b>10Y−2Y</b>：10年期收益率减2年期收益率，
    即传统意义上的2s10s。<br>

    <b>10Y−3M</b>：10年期收益率减3个月收益率，
    更直接反映长期利率与当前短端政策环境之间的差异。<br>

    <b>Spread > 0</b>：收益率曲线对应区间向上。<br>

    <b>Spread < 0</b>：对应区间倒挂。
    """
)


add_source(
    "FRED — 3M / 2Y / 10Y Treasury Yields",
    "https://fred.stlouisfed.org/graph/?id=DGS3MO%2CDGS2%2CDGS10"
)


st.markdown(
    '<div class="chart-divider"></div>',
    unsafe_allow_html=True
)


# =========================================================
# 4. 7×24 Market News
# =========================================================

st.markdown(
    '<div class="section-title">4. 7×24 Market News</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="section-description">'
    '实时财经文字快讯：新浪财经 + WSJ公开市场新闻'
    '</div>',
    unsafe_allow_html=True
)


# =========================================================
# Refresh
# =========================================================

news_col1, news_col2 = st.columns([1, 6])


with news_col1:

    refresh_news = st.button(
        "🔄 刷新新闻",
        key="refresh_news"
    )


if refresh_news:

    get_sina_news.clear()
    get_wsj_news.clear()


# =========================================================
# Load News
# =========================================================

sina_news = get_sina_news(
    limit=20
)

wsj_news = get_wsj_news(
    limit=12
)


news_col1, news_col2 = st.columns(
    2,
    gap="large"
)


# =========================================================
# Sina
# =========================================================

with news_col1:

    st.markdown(
        "### 新浪财经 7×24"
    )

    if sina_news:

        for item in sina_news:

            title = item["title"]
            time_text = item["time"]
            url = item["url"]

            st.markdown(
                f"""
                <div class="news-item">
                    <span class="news-time">
                        {time_text}
                    </span>
                    <a href="{url}" target="_blank">
                        {title}
                    </a>
                </div>
                """,
                unsafe_allow_html=True
            )

    else:

        st.info(
            "暂时无法获取新浪财经7×24数据。"
        )

    st.markdown("")

    add_source(
        "新浪财经 7×24",
        "https://finance.sina.com.cn/7x24/"
    )


# =========================================================
# WSJ
# =========================================================

with news_col2:

    st.markdown(
        "### WSJ"
    )

    if wsj_news:

        for item in wsj_news:

            title = item["title"]
            url = item["url"]

            st.markdown(
                f"""
                <div class="news-item">
                    <a href="{url}" target="_blank">
                        {title}
                    </a>
                    <div class="news-source">
                        The Wall Street Journal
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )

    else:

        st.info(
            "暂时无法获取WSJ公开新闻。"
        )

    st.markdown("")

    add_source(
        "WSJ Finance",
        "https://www.wsj.com/finance"
    )


# =========================================================
# Footer
# =========================================================

st.markdown(
    """
    <div style="
        margin-top: 2rem;
        padding-top: 1rem;
        border-top: 1px solid #e5e7eb;
        color: #9ca3af;
        font-size: 0.75rem;
    ">
        Data source: Federal Reserve Economic Data (FRED)
        · News: Sina Finance / The Wall Street Journal
    </div>
    """,
    unsafe_allow_html=True
)
