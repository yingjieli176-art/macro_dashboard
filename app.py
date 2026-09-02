import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from data import (
    get_sofr,
    get_iorb,
    get_effr,
    get_rrp,
    get_dgs10,
    get_dfii10
)


# =========================
# 页面设置
# =========================

st.set_page_config(
    page_title="Macro Dashboard",
    page_icon="📊",
    layout="wide"
)

st.title("Macro Dashboard")
st.caption("US Rates & Macro Market Monitor")


# =========================
# 获取 Funding 数据
# =========================

sofr = get_sofr()
iorb = get_iorb()
effr = get_effr()
rrp = get_rrp()


# =========================
# 获取 Yield 数据
# =========================

dgs10 = get_dgs10()
dfii10 = get_dfii10()


# =========================
# Funding 数据清洗
# =========================

funding = sofr.merge(
    iorb,
    on="observation_date",
    how="outer"
)

funding = funding.merge(
    effr,
    on="observation_date",
    how="outer"
)

funding = funding.merge(
    rrp,
    on="observation_date",
    how="outer"
)

funding = funding.sort_values(
    "observation_date"
)


for col in ["SOFR", "IORB", "EFFR", "RRPONTSYAWARD"]:
    funding[col] = pd.to_numeric(
        funding[col],
        errors="coerce"
    )


# =========================
# Yield 数据清洗
# =========================

dgs10 = dgs10.dropna(
    subset=["DGS10"]
).copy()

dfii10 = dfii10.dropna(
    subset=["DFII10"]
).copy()

dgs10["observation_date"] = pd.to_datetime(
    dgs10["observation_date"]
)

dfii10["observation_date"] = pd.to_datetime(
    dfii10["observation_date"]
)


# =========================
# Yield 合并
# =========================

yield_data = pd.merge(
    dgs10[
        ["observation_date", "DGS10"]
    ],
    dfii10[
        ["observation_date", "DFII10"]
    ],
    on="observation_date",
    how="inner"
)

yield_data = yield_data.sort_values(
    "observation_date"
)

yield_data["BREAKEVEN10"] = (
    yield_data["DGS10"]
    - yield_data["DFII10"]
)


# =========================================================
# ① FUNDING / LIQUIDITY
# =========================================================

st.subheader("Funding / Liquidity")


period = st.radio(
    "Time Range",
    ["5Y", "1Y", "6M", "3M", "1M"],
    index=1,
    horizontal=True,
    key="funding_period"
)


period_days = {
    "5Y": 1825,
    "1Y": 365,
    "6M": 183,
    "3M": 92,
    "1M": 31
}


days = period_days[period]


latest_funding_date = funding[
    "observation_date"
].max()


funding_start_date = (
    latest_funding_date
    - pd.Timedelta(days=days)
)


funding_chart = funding[
    funding["observation_date"]
    >= funding_start_date
].copy()


funding_chart = funding_chart.sort_values(
    "observation_date"
)


funding_chart["day_index"] = range(
    len(funding_chart)
)


funding_chart["date_label"] = (
    funding_chart["observation_date"]
    .dt.strftime("%m/%d/%y")
)


# =========================
# Funding 图
# =========================

fig_funding = go.Figure()


# SOFR
fig_funding.add_trace(
    go.Scatter(
        x=funding_chart["day_index"],
        y=funding_chart["SOFR"],
        mode="lines",
        name="SOFR",
        line=dict(width=2),
        customdata=funding_chart["date_label"],
        hovertemplate=(
            "Date: %{customdata}"
            "<br>SOFR: %{y:.2f}%"
            "<extra></extra>"
        )
    )
)


# IORB
fig_funding.add_trace(
    go.Scatter(
        x=funding_chart["day_index"],
        y=funding_chart["IORB"],
        mode="lines",
        name="IORB",
        line=dict(width=2),
        customdata=funding_chart["date_label"],
        hovertemplate=(
            "Date: %{customdata}"
            "<br>IORB: %{y:.2f}%"
            "<extra></extra>"
        )
    )
)


# EFFR
fig_funding.add_trace(
    go.Scatter(
        x=funding_chart["day_index"],
        y=funding_chart["EFFR"],
        mode="lines",
        name="EFFR",
        line=dict(width=2),
        customdata=funding_chart["date_label"],
        hovertemplate=(
            "Date: %{customdata}"
            "<br>EFFR: %{y:.2f}%"
            "<extra></extra>"
        )
    )
)


# RRP rate
fig_funding.add_trace(
    go.Scatter(
        x=funding_chart["day_index"],
        y=funding_chart["RRPONTSYAWARD"],
        mode="lines",
        name="ON RRP Rate",
        line=dict(width=2, dash="dot"),
        customdata=funding_chart["date_label"],
        hovertemplate=(
            "Date: %{customdata}"
            "<br>ON RRP Rate: %{y:.2f}%"
            "<extra></extra>"
        )
    )
)


# =========================
# X 轴
# =========================

if period == "1M":
    step = 2
elif period == "3M":
    step = 7
elif period == "6M":
    step = 15
elif period == "1Y":
    step = 30
else:
    step = 90


tick_positions = (
    funding_chart["day_index"][::step]
)

tick_labels = (
    funding_chart["date_label"][::step]
)


# =========================
# Funding 图样式
# =========================

fig_funding.update_layout(
    height=500,

    margin=dict(
        l=20,
        r=20,
        t=30,
        b=50
    ),

    hovermode="x unified",

    xaxis=dict(
        title="Trading Day",
        type="linear",
        tickmode="array",
        tickvals=tick_positions,
        ticktext=tick_labels,
        showgrid=True,
        gridcolor="rgba(0,0,0,0.08)"
    ),

    yaxis=dict(
        title="Rate (%)",
        ticksuffix="%",
        showgrid=True,
        zeroline=False
    ),

    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="left",
        x=0
    ),

    plot_bgcolor="white",
    paper_bgcolor="white"
)


st.plotly_chart(
    fig_funding,
    use_container_width=True
)


# =========================================================
# ② 10Y YIELD STRUCTURE
# =========================================================

st.subheader("10Y Yield Structure")


yield_period = st.radio(
    "Time Range",
    ["5Y", "1Y", "6M", "3M", "1M"],
    index=1,
    horizontal=True,
    key="yield_period"
)


yield_days = period_days[
    yield_period
]


latest_yield_date = yield_data[
    "observation_date"
].max()


yield_start_date = (
    latest_yield_date
    - pd.Timedelta(days=yield_days)
)


yield_chart = yield_data[
    yield_data["observation_date"]
    >= yield_start_date
].copy()


yield_chart = yield_chart.sort_values(
    "observation_date"
)


yield_chart["day_index"] = range(
    len(yield_chart)
)


yield_chart["date_label"] = (
    yield_chart["observation_date"]
    .dt.strftime("%m/%d/%y")
)


# =========================
# Yield 图
# =========================

fig_yield = go.Figure()


# Breakeven
fig_yield.add_trace(
    go.Bar(
        x=yield_chart["day_index"],
        y=yield_chart["BREAKEVEN10"],
        name="10Y Treasury − 10Y TIPS",
        opacity=0.30,
        customdata=yield_chart["date_label"],
        hovertemplate=(
            "Date: %{customdata}"
            "<br>10Y Treasury − 10Y TIPS: "
            "%{y:.2f}%"
            "<extra></extra>"
        )
    )
)


# 10Y Treasury
fig_yield.add_trace(
    go.Scatter(
        x=yield_chart["day_index"],
        y=yield_chart["DGS10"],
        mode="lines+markers",
        name="10Y Treasury",
        line=dict(width=2),
        marker=dict(size=4),
        customdata=yield_chart["date_label"],
        hovertemplate=(
            "Date: %{customdata}"
            "<br>10Y Treasury: "
            "%{y:.2f}%"
            "<extra></extra>"
        )
    )
)


# 10Y TIPS
fig_yield.add_trace(
    go.Scatter(
        x=yield_chart["day_index"],
        y=yield_chart["DFII10"],
        mode="lines+markers",
        name="10Y TIPS Real Yield",
        line=dict(width=2),
        marker=dict(size=4),
        customdata=yield_chart["date_label"],
        hovertemplate=(
            "Date: %{customdata}"
            "<br>10Y TIPS Real Yield: "
            "%{y:.2f}%"
            "<extra></extra>"
        )
    )
)


# =========================
# X 轴
# =========================

if yield_period == "1M":
    step = 2
elif yield_period == "3M":
    step = 7
elif yield_period == "6M":
    step = 15
elif yield_period == "1Y":
    step = 30
else:
    step = 90


tick_positions = (
    yield_chart["day_index"][::step]
)

tick_labels = (
    yield_chart["date_label"][::step]
)


# =========================
# Yield 图样式
# =========================

fig_yield.update_layout(
    height=560,

    margin=dict(
        l=20,
        r=20,
        t=30,
        b=50
    ),

    hovermode="x unified",

    xaxis=dict(
        title="Trading Day",
        type="linear",
        tickmode="array",
        tickvals=tick_positions,
        ticktext=tick_labels,
        showgrid=True,
        gridcolor="rgba(0,0,0,0.08)"
    ),

    yaxis=dict(
        title="Yield / Inflation (%)",
        ticksuffix="%",
        showgrid=True,
        zeroline=False
    ),

    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="left",
        x=0
    ),

    bargap=0.15,

    plot_bgcolor="white",
    paper_bgcolor="white"
)


st.plotly_chart(
    fig_yield,
    use_container_width=True
)


# =========================
# 数据来源
# =========================

st.markdown("### Data Sources")

st.markdown(
    """
**Funding / Liquidity**

- SOFR — FRED / Federal Reserve Bank of New York
- IORB — FRED / Board of Governors of the Federal Reserve System
- EFFR — FRED / Federal Reserve Bank of New York
- ON RRP — FRED

**Yield**

- 10Y Treasury (DGS10) — FRED
- 10Y TIPS Real Yield (DFII10) — FRED
- 10Y Treasury − 10Y TIPS — Calculated directly
"""
)


# =========================
# 数据状态
# =========================

st.caption(
    f"Funding latest available data: "
    f"{latest_funding_date.strftime('%Y-%m-%d')}  |  "
    f"Yield latest available data: "
    f"{latest_yield_date.strftime('%Y-%m-%d')}  |  "
    f"Source: FRED"
)
