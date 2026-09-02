import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from data import (
    get_dgs10,
    get_dfii10,
    get_sofr,
    get_iorb,
    get_effr,
    get_rrp
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
# 获取数据
# =========================

dgs10 = get_dgs10()
dfii10 = get_dfii10()

sofr = get_sofr()
iorb = get_iorb()
effr = get_effr()
rrp = get_rrp()


# =========================
# 数据清洗
# =========================

for df in [dgs10, dfii10, sofr, iorb, effr, rrp]:
    df["observation_date"] = pd.to_datetime(
        df["observation_date"]
    )


dgs10 = dgs10.dropna(subset=["DGS10"]).copy()
dfii10 = dfii10.dropna(subset=["DFII10"]).copy()

sofr = sofr.dropna(subset=["SOFR"]).copy()
iorb = iorb.dropna(subset=["IORB"]).copy()
effr = effr.dropna(subset=["EFFR"]).copy()
rrp = rrp.dropna(subset=["RRPONTSYD"]).copy()


# =========================
# 10Y Yield Structure
# =========================

data = pd.merge(
    dgs10[["observation_date", "DGS10"]],
    dfii10[["observation_date", "DFII10"]],
    on="observation_date",
    how="inner"
)

data = data.sort_values("observation_date")

data["BREAKEVEN10"] = (
    data["DGS10"] - data["DFII10"]
)


# =========================
# Funding / Liquidity
# =========================

liquidity = sofr.merge(
    iorb,
    on="observation_date",
    how="outer"
)

liquidity = liquidity.merge(
    effr,
    on="observation_date",
    how="outer"
)

liquidity = liquidity.merge(
    rrp,
    on="observation_date",
    how="outer"
)

liquidity = liquidity.sort_values(
    "observation_date"
)


# =========================
# 最新日期
# =========================

latest_date = max(
    data["observation_date"].max(),
    liquidity["observation_date"].max()
)


# =========================
# 时间范围
# =========================

period = st.radio(
    "Time Range",
    ["5Y", "1Y", "6M", "3M", "1M"],
    index=1,
    horizontal=True
)

period_days = {
    "5Y": 1825,
    "1Y": 365,
    "6M": 183,
    "3M": 92,
    "1M": 31
}

days = period_days[period]

start_date = (
    latest_date
    - pd.Timedelta(days=days)
)


# =========================================================
# Chart 1 — Funding / Liquidity
# =========================================================

st.subheader("Funding / Liquidity")

liquidity_chart = liquidity[
    liquidity["observation_date"] >= start_date
].copy()

liquidity_chart = liquidity_chart.sort_values(
    "observation_date"
)

liquidity_chart["day_index"] = range(
    len(liquidity_chart)
)

liquidity_chart["date_label"] = (
    liquidity_chart["observation_date"]
    .dt.strftime("%m/%d/%y")
)


fig1 = go.Figure()


# SOFR
fig1.add_trace(
    go.Scatter(
        x=liquidity_chart["day_index"],
        y=liquidity_chart["SOFR"],
        mode="lines",
        name="SOFR",
        line=dict(width=2),
        customdata=liquidity_chart["date_label"],
        hovertemplate=(
            "Date: %{customdata}"
            "<br>SOFR: %{y:.2f}%"
            "<extra></extra>"
        )
    )
)


# IORB
fig1.add_trace(
    go.Scatter(
        x=liquidity_chart["day_index"],
        y=liquidity_chart["IORB"],
        mode="lines",
        name="IORB",
        line=dict(width=2),
        customdata=liquidity_chart["date_label"],
        hovertemplate=(
            "Date: %{customdata}"
            "<br>IORB: %{y:.2f}%"
            "<extra></extra>"
        )
    )
)


# EFFR
fig1.add_trace(
    go.Scatter(
        x=liquidity_chart["day_index"],
        y=liquidity_chart["EFFR"],
        mode="lines",
        name="EFFR",
        line=dict(width=2),
        customdata=liquidity_chart["date_label"],
        hovertemplate=(
            "Date: %{customdata}"
            "<br>EFFR: %{y:.2f}%"
            "<extra></extra>"
        )
    )
)


# RRP amount —— 第二纵轴
fig1.add_trace(
    go.Bar(
        x=liquidity_chart["day_index"],
        y=liquidity_chart["RRPONTSYD"],
        name="ON RRP",
        opacity=0.25,
        customdata=liquidity_chart["date_label"],
        hovertemplate=(
            "Date: %{customdata}"
            "<br>ON RRP: %{y:.2f} B"
            "<extra></extra>"
        ),
        yaxis="y2"
    )
)


# =========================
# X 轴标签
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
    liquidity_chart["day_index"][::step]
)

tick_labels = (
    liquidity_chart["date_label"][::step]
)


# =========================
# 图表样式
# =========================

fig1.update_layout(
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

    # 左侧纵轴：利率
    yaxis=dict(
        title="Rate (%)",
        ticksuffix="%",
        showgrid=True,
        zeroline=False
    ),

    # 右侧纵轴：RRP 金额
    yaxis2=dict(
        title="ON RRP ($B)",
        overlaying="y",
        side="right",
        showgrid=False,
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
    fig1,
    use_container_width=True
)


# =========================================================
# Chart 2 — 10Y Yield Structure
# =========================================================

st.subheader("10Y Yield Structure")

yield_chart = data[
    data["observation_date"] >= start_date
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


fig2 = go.Figure()


# Breakeven
fig2.add_trace(
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
fig2.add_trace(
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
            "<br>10Y Treasury: %{y:.2f}%"
            "<extra></extra>"
        )
    )
)


# 10Y TIPS
fig2.add_trace(
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
            "<br>10Y TIPS Real Yield: %{y:.2f}%"
            "<extra></extra>"
        )
    )
)


# =========================
# X 轴标签
# =========================

tick_positions = (
    yield_chart["day_index"][::step]
)

tick_labels = (
    yield_chart["date_label"][::step]
)


# =========================
# 图表样式
# =========================

fig2.update_layout(
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
    fig2,
    use_container_width=True
)


# =========================================================
# Data Sources
# =========================================================

st.markdown("### Data Sources")

st.markdown(
    """
**Funding / Liquidity**

- **SOFR** — [FRED: Secured Overnight Financing Rate](https://fred.stlouisfed.org/series/SOFR)
- **IORB** — [FRED: Interest Rate on Reserve Balances](https://fred.stlouisfed.org/series/IORB)
- **EFFR** — [FRED: Effective Federal Funds Rate](https://fred.stlouisfed.org/series/EFFR)
- **ON RRP** — [FRED: Overnight Reverse Repurchase Agreements](https://fred.stlouisfed.org/series/RRPONTSYD)

**10Y Yield Structure**

- **10Y Treasury** — [FRED: 10-Year Treasury Constant Maturity Rate](https://fred.stlouisfed.org/series/DGS10)
- **10Y TIPS Real Yield** — [FRED: 10-Year Treasury Inflation-Indexed Security](https://fred.stlouisfed.org/series/DFII10)
- **10Y Treasury − 10Y TIPS** — Calculated directly from the two FRED series above.
"""
)


# =========================
# 数据状态
# =========================

st.caption(
    f"Latest available data: "
    f"{latest_date.strftime('%Y-%m-%d')}  |  "
    f"Source: FRED  |  "
    f"Daily trading-day data"
)
