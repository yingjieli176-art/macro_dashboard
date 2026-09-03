import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from data import (
    get_dgs2,
    get_dgs5,
    get_dgs10,
    get_dfii10,
    get_sofr,
    get_iorb,
    get_effr,
    get_rrp_rate,
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
# Custom CSS
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
        margin-bottom: 1.5rem;
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
            r=55,
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

    st.markdown(
        f"""
        <div class="parameter-box">
            <b>参数备注 / 中文释义</b><br>
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


# Individual time control
corridor_range = st.radio(
    "时间范围",
    ["5Y", "1Y", "6M", "3M", "1M"],
    horizontal=True,
    index=1,
    key="corridor_range"
)

corridor_start = get_start_date(corridor_range)


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
        name="ON RRP Rate",
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
    height=470
)

st.plotly_chart(
    fig1,
    use_container_width=True
)


add_parameter_notes(
    """
    <b>IORB</b>：Interest on Reserve Balances，银行存放在美联储的准备金余额利率，
    可理解为美联储管理联邦基金利率的重要上方政策利率。<br>

    <b>ON RRP Rate</b>：Overnight Reverse Repurchase Agreement Rate，
    隔夜逆回购利率，可理解为货币市场利率的重要下方利率。<br>

    <b>EFFR</b>：Effective Federal Funds Rate，
    联邦基金有效利率，代表银行间实际成交的联邦基金利率水平。<br>

    <b>SOFR</b>：Secured Overnight Financing Rate，
    有担保隔夜融资利率，主要反映美国国债抵押融资市场的隔夜资金成本。<br>

    <b>本图单位</b>：全部为 %
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


# Individual time control
yield10_range = st.radio(
    "时间范围",
    ["5Y", "1Y", "6M", "3M", "1M"],
    horizontal=True,
    index=1,
    key="yield10_range"
)

yield10_start = get_start_date(yield10_range)


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


# 10Y Breakeven
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
    height=470
)

st.plotly_chart(
    fig2,
    use_container_width=True
)


add_parameter_notes(
    """
    <b>DGS10</b>：10-Year Treasury Constant Maturity Rate，
    美国10年期国债名义收益率。<br>

    <b>DFII10</b>：10-Year Treasury Inflation-Indexed Security，
    美国10年期TIPS实际收益率，可作为市场实际利率的重要观察指标。<br>

    <b>10Y Breakeven</b>：
    <b>DGS10 − DFII10</b>，
    10年期盈亏平衡通胀率（Breakeven Inflation Rate）。<br>

    <b>经济含义</b>：
    名义10年期国债收益率与TIPS实际收益率之间的差额，
    可用于观察市场隐含的长期通胀补偿。
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
# 3. Treasury Yield & Curve Spreads
# =========================================================

st.markdown(
    '<div class="section-title">3. Treasury Yield & Curve Spreads</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="section-description">'
    '2年、5年、10年国债收益率，以及2s10s / 5s10s期限利差'
    '</div>',
    unsafe_allow_html=True
)


# Individual time control
treasury_range = st.radio(
    "时间范围",
    ["5Y", "1Y", "6M", "3M", "1M"],
    horizontal=True,
    index=1,
    key="treasury_range"
)

treasury_start = get_start_date(treasury_range)


treasury = (
    get_dgs2()
    .merge(
        get_dgs5(),
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
# Spread Calculation
# =========================================================

# 2s10s = 10Y - 2Y
treasury["2s10s"] = (
    treasury["DGS10"]
    - treasury["DGS2"]
) * 100


# 5s10s = 10Y - 5Y
treasury["5s10s"] = (
    treasury["DGS10"]
    - treasury["DGS5"]
) * 100


fig3 = go.Figure()


# =========================================================
# Treasury Yields
# =========================================================

fig3.add_trace(
    go.Scatter(
        x=treasury["observation_date"],
        y=treasury["DGS2"],
        name="2Y",
        mode="lines",
        line=dict(width=2.2),
        yaxis="y"
    )
)


fig3.add_trace(
    go.Scatter(
        x=treasury["observation_date"],
        y=treasury["DGS5"],
        name="5Y",
        mode="lines",
        line=dict(width=2.2),
        yaxis="y"
    )
)


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


# =========================================================
# Spread Bars
# =========================================================

fig3.add_trace(
    go.Bar(
        x=treasury["observation_date"],
        y=treasury["2s10s"],
        name="2s10s",
        opacity=0.48,
        yaxis="y2"
    )
)


fig3.add_trace(
    go.Bar(
        x=treasury["observation_date"],
        y=treasury["5s10s"],
        name="5s10s",
        opacity=0.48,
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
    height=500
)

st.plotly_chart(
    fig3,
    use_container_width=True
)


# =========================================================
# Spread Formula / Parameter Notes
# =========================================================

st.markdown(
    """
    <div class="formula-box">
        <b>利差计算方式</b><br>
        <b>2s10s = 10Y − 2Y</b>
        → 10年期国债收益率减去2年期国债收益率<br>

        <b>5s10s = 10Y − 5Y</b>
        → 10年期国债收益率减去5年期国债收益率<br>

        <b>单位转换</b>：
        FRED收益率单位为 %，因此
        <b>1个百分点 = 100 bp</b>。
        代码中将差值 × 100 后以 bp 显示。
    </div>
    """,
    unsafe_allow_html=True
)


add_parameter_notes(
    """
    <b>DGS2</b>：2-Year Treasury Constant Maturity Rate，
    美国2年期国债收益率。通常对短期政策利率预期较敏感。<br>

    <b>DGS5</b>：5-Year Treasury Constant Maturity Rate，
    美国5年期国债收益率，可观察中期利率定价。<br>

    <b>DGS10</b>：10-Year Treasury Constant Maturity Rate，
    美国10年期国债收益率，是长期无风险利率的重要基准。<br>

    <b>2s10s</b>：10Y − 2Y，
    观察2年与10年期限之间的收益率曲线斜率。<br>

    <b>5s10s</b>：10Y − 5Y，
    观察5年与10年期限之间的收益率曲线斜率。<br>

    <b>Spread > 0</b>：长期收益率高于短期收益率，曲线向上。<br>

    <b>Spread < 0</b>：长期收益率低于短期收益率，曲线倒挂。
    """
)


add_source(
    "FRED — 2Y / 5Y / 10Y Treasury Yields",
    "https://fred.stlouisfed.org/graph/?id=DGS2%2CDGS5%2CDGS10"
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
    </div>
    """,
    unsafe_allow_html=True
)
