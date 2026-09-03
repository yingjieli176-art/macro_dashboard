import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from data import (
    get_dgs10,
    get_dfii10,
    get_sofr,
    get_iorb,
    get_effr,
    get_rrp,
    get_dgs2,
    get_dgs5,
)


# =========================
# Page
# =========================

st.set_page_config(
    page_title="Macro Dashboard",
    layout="wide"
)

st.title("Macro Dashboard")


# =========================
# Load data
# =========================

dgs10 = get_dgs10()
dfii10 = get_dfii10()

sofr = get_sofr()
iorb = get_iorb()
effr = get_effr()
rrp = get_rrp()

dgs2 = get_dgs2()
dgs5 = get_dgs5()


# =========================
# Clean data
# =========================

dgs10 = dgs10.dropna(subset=["DGS10"]).copy()
dfii10 = dfii10.dropna(subset=["DFII10"]).copy()

sofr = sofr.dropna(subset=["SOFR"]).copy()
iorb = iorb.dropna(subset=["IORB"]).copy()
effr = effr.dropna(subset=["EFFR"]).copy()
rrp = rrp.dropna(subset=["RRPONTSYD"]).copy()

dgs2 = dgs2.dropna(subset=["DGS2"]).copy()
dgs5 = dgs5.dropna(subset=["DGS5"]).copy()


# =========================
# 10Y Yield Structure
# =========================

yield_data = (
    dgs10
    .merge(
        dfii10,
        on="observation_date",
        how="outer"
    )
    .sort_values("observation_date")
)

yield_data["BREAKEVEN10"] = (
    yield_data["DGS10"]
    - yield_data["DFII10"]
)


# =========================
# Funding / Liquidity
# =========================

liquidity_data = (
    sofr
    .merge(
        iorb,
        on="observation_date",
        how="outer"
    )
    .merge(
        effr,
        on="observation_date",
        how="outer"
    )
    .merge(
        rrp,
        on="observation_date",
        how="outer"
    )
    .sort_values("observation_date")
)


# =========================
# Treasury Yield Spread
# =========================

curve_data = (
    dgs2
    .merge(
        dgs5,
        on="observation_date",
        how="outer"
    )
    .merge(
        dgs10,
        on="observation_date",
        how="outer"
    )
    .sort_values("observation_date")
)

# Yield spread
curve_data["SPREAD_2S10S"] = (
    curve_data["DGS10"]
    - curve_data["DGS2"]
)

curve_data["SPREAD_5S10S"] = (
    curve_data["DGS10"]
    - curve_data["DGS5"]
)


# =========================
# Time Range
# =========================

period = st.radio(
    "Time Range",
    ["5Y", "1Y", "6M", "3M", "1M"],
    horizontal=True,
    index=0
)

days_map = {
    "5Y": 365 * 5,
    "1Y": 365,
    "6M": 180,
    "3M": 90,
    "1M": 30,
}

days = days_map[period]

latest_date = max(
    yield_data["observation_date"].max(),
    liquidity_data["observation_date"].max(),
    curve_data["observation_date"].max()
)

start_date = latest_date - pd.Timedelta(days=days)


yield_plot = yield_data[
    yield_data["observation_date"] >= start_date
].copy()

liquidity_plot = liquidity_data[
    liquidity_data["observation_date"] >= start_date
].copy()

curve_plot = curve_data[
    curve_data["observation_date"] >= start_date
].copy()


# ============================================================
# Chart 1
# Funding / Liquidity
# ============================================================

st.subheader("Funding / Liquidity")

fig1 = go.Figure()


# SOFR
fig1.add_trace(
    go.Scatter(
        x=liquidity_plot["observation_date"],
        y=liquidity_plot["SOFR"],
        name="SOFR",
        mode="lines",
        yaxis="y1",
    )
)


# IORB
fig1.add_trace(
    go.Scatter(
        x=liquidity_plot["observation_date"],
        y=liquidity_plot["IORB"],
        name="IORB",
        mode="lines",
        yaxis="y1",
    )
)


# EFFR
fig1.add_trace(
    go.Scatter(
        x=liquidity_plot["observation_date"],
        y=liquidity_plot["EFFR"],
        name="EFFR",
        mode="lines",
        yaxis="y1",
    )
)


# ON RRP amount
fig1.add_trace(
    go.Bar(
        x=liquidity_plot["observation_date"],
        y=liquidity_plot["RRPONTSYD"],
        name="ON RRP",
        opacity=0.35,
        yaxis="y2",
    )
)


fig1.update_layout(
    height=500,
    hovermode="x unified",

    xaxis=dict(
        title="Date"
    ),

    yaxis=dict(
        title="Interest Rate (%)",
        side="left",
    ),

    yaxis2=dict(
        title="ON RRP ($B)",
        side="right",
        overlaying="y",
        showgrid=False,
    ),

    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="left",
        x=0
    )
)

st.plotly_chart(
    fig1,
    use_container_width=True
)


# ============================================================
# Chart 2
# 10Y Yield Structure
# ============================================================

st.subheader("10Y Yield Structure")

fig2 = go.Figure()


# Breakeven
fig2.add_trace(
    go.Bar(
        x=yield_plot["observation_date"],
        y=yield_plot["BREAKEVEN10"],
        name="10Y Breakeven",
        opacity=0.35,
    )
)


# 10Y nominal
fig2.add_trace(
    go.Scatter(
        x=yield_plot["observation_date"],
        y=yield_plot["DGS10"],
        name="10Y Treasury",
        mode="lines",
    )
)


# 10Y real yield
fig2.add_trace(
    go.Scatter(
        x=yield_plot["observation_date"],
        y=yield_plot["DFII10"],
        name="10Y TIPS Real Yield",
        mode="lines",
    )
)


fig2.update_layout(
    height=500,
    hovermode="x unified",

    xaxis=dict(
        title="Date"
    ),

    yaxis=dict(
        title="Yield (%)"
    ),

    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="left",
        x=0
    )
)

st.plotly_chart(
    fig2,
    use_container_width=True
)


# ============================================================
# Chart 3
# Treasury Yield Curve & Spreads
# ============================================================

st.subheader("Treasury Yield Curve & Spreads")

fig3 = go.Figure()


# -------------------------
# Left axis: Treasury yields
# -------------------------

fig3.add_trace(
    go.Scatter(
        x=curve_plot["observation_date"],
        y=curve_plot["DGS2"],
        name="2Y Treasury",
        mode="lines",
        yaxis="y1",
    )
)


fig3.add_trace(
    go.Scatter(
        x=curve_plot["observation_date"],
        y=curve_plot["DGS5"],
        name="5Y Treasury",
        mode="lines",
        yaxis="y1",
    )
)


fig3.add_trace(
    go.Scatter(
        x=curve_plot["observation_date"],
        y=curve_plot["DGS10"],
        name="10Y Treasury",
        mode="lines",
        yaxis="y1",
    )
)


# -------------------------
# Right axis: spreads
# -------------------------

fig3.add_trace(
    go.Bar(
        x=curve_plot["observation_date"],
        y=curve_plot["SPREAD_2S10S"],
        name="2s10s Spread",
        opacity=0.45,
        yaxis="y2",
    )
)


fig3.add_trace(
    go.Bar(
        x=curve_plot["observation_date"],
        y=curve_plot["SPREAD_5S10S"],
        name="5s10s Spread",
        opacity=0.45,
        yaxis="y2",
    )
)


fig3.update_layout(
    height=550,
    hovermode="x unified",

    xaxis=dict(
        title="Date"
    ),

    # 左轴：收益率
    yaxis=dict(
        title="Treasury Yield (%)",
        side="left",
    ),

    # 右轴：利差
    yaxis2=dict(
        title="Spread (pp)",
        side="right",
        overlaying="y",
        showgrid=False,
        zeroline=True,
    ),

    barmode="group",

    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="left",
        x=0
    )
)

st.plotly_chart(
    fig3,
    use_container_width=True
)


# =========================
# Data Sources
# =========================

st.subheader("Data Sources")

st.markdown(
    """
- [SOFR / Secured Overnight Financing Rate | FRED](https://fred.stlouisfed.org/graph/?graph_id=1547733&rn=698)
- [DGS10 / 10-Year Treasury Yield | FRED](https://fred.stlouisfed.org/series/DGS10)
- [DFII10 / 10-Year TIPS Real Yield | FRED](https://fred.stlouisfed.org/series/DFII10)
- [DGS2 / 2-Year Treasury Yield | FRED](https://fred.stlouisfed.org/series/DGS2)
- [DGS5 / 5-Year Treasury Yield | FRED](https://fred.stlouisfed.org/series/DGS5)
- [IORB | FRED](https://fred.stlouisfed.org/series/IORB)
- [EFFR | FRED](https://fred.stlouisfed.org/series/EFFR)
- [RRPONTSYD / ON RRP | FRED](https://fred.stlouisfed.org/series/RRPONTSYD)
"""
)
