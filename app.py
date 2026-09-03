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

    /* Main page */
    .block-container {
        padding-top: 2rem;
        padding-bottom: 4rem;
        max-width: 1400px;
    }

    /* Main title */
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

    /* Section title */
    .section-title {
        font-size: 1.35rem;
        font-weight: 650;
        margin-top: 1.5rem;
        margin-bottom: 0.15rem;
    }

    .section-description {
        color: #6b7280;
        font-size: 0.9rem;
        margin-bottom: 0.7rem;
    }

    /* Source */
    .source-text {
        color: #6b7280;
        font-size: 0.78rem;
        margin-top: -0.3rem;
        margin-bottom: 2.2rem;
    }

    /* Divider */
    .chart-divider {
        margin-top: 0.5rem;
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
# Time Range
# =========================================================

time_range = st.radio(
    "Time range",
    ["5Y", "1Y", "6M", "3M", "1M"],
    horizontal=True,
    index=1
)


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


start_date = get_start_date(time_range)


# =========================================================
# Common Chart Style
# =========================================================

def apply_chart_style(fig, height=480):

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
            linecolor="#d1d5db",
            rangeslider=dict(
                visible=False
            )
        ),

        yaxis=dict(
            showgrid=True,
            gridcolor="#eeeeee",
            zeroline=False,
            showline=False
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


# =========================================================
# Load Data
# =========================================================

dgs2 = get_dgs2()
dgs5 = get_dgs5()
dgs10 = get_dgs10()

dfii10 = get_dfii10()

sofr = get_sofr()
iorb = get_iorb()
effr = get_effr()
rrp = get_rrp_rate()


# =========================================================
# 1. Policy Rate Corridor
# =========================================================

st.markdown(
    '<div class="section-title">Policy Rate Corridor</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="section-description">'
    'IORB, ON RRP rate, EFFR and SOFR'
    '</div>',
    unsafe_allow_html=True
)


corridor = (
    iorb
    .merge(
        rrp,
        on="observation_date",
        how="outer"
    )
    .merge(
        effr,
        on="observation_date",
        how="outer"
    )
    .merge(
        sofr,
        on="observation_date",
        how="outer"
    )
    .sort_values("observation_date")
)


corridor = corridor[
    corridor["observation_date"] >= start_date
]


fig1 = go.Figure()


# IORB
fig1.add_trace(
    go.Scatter(
        x=corridor["observation_date"],
        y=corridor["IORB"],
        name="IORB",
        mode="lines",
        line=dict(
            width=2.5
        )
    )
)


# ON RRP Rate
fig1.add_trace(
    go.Scatter(
        x=corridor["observation_date"],
        y=corridor["RRPONTSYAWARD"],
        name="ON RRP Rate",
        mode="lines",
        line=dict(
            width=2.5
        )
    )
)


# EFFR
fig1.add_trace(
    go.Scatter(
        x=corridor["observation_date"],
        y=corridor["EFFR"],
        name="EFFR",
        mode="lines",
        line=dict(
            width=2.5
        )
    )
)


# SOFR
fig1.add_trace(
    go.Scatter(
        x=corridor["observation_date"],
        y=corridor["SOFR"],
        name="SOFR",
        mode="lines",
        line=dict(
            width=2
        )
    )
)


fig1.update_layout(
    title="",
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


add_source(
    "FRED — Policy Rate Corridor",
    "https://fred.stlouisfed.org/graph/?graph_id=1547733&rn=698"
)


# =========================================================
# Divider
# =========================================================

st.markdown(
    '<div class="chart-divider"></div>',
    unsafe_allow_html=True
)


# =========================================================
# 2. 10Y Yield Structure
# =========================================================

st.markdown(
    '<div class="section-title">10Y Yield Structure</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="section-description">'
    'Nominal yield, real yield and 10Y breakeven inflation'
    '</div>',
    unsafe_allow_html=True
)


yield10 = (
    dgs10
    .merge(
        dfii10,
        on="observation_date",
        how="inner"
    )
    .sort_values("observation_date")
)


yield10 = yield10[
    yield10["observation_date"] >= start_date
]


yield10["Breakeven"] = (
    yield10["DGS10"]
    - yield10["DFII10"]
)


fig2 = go.Figure()


# 10Y Nominal
fig2.add_trace(
    go.Scatter(
        x=yield10["observation_date"],
        y=yield10["DGS10"],
        name="10Y Nominal",
        mode="lines",
        line=dict(
            width=2.5
        )
    )
)


# 10Y Real
fig2.add_trace(
    go.Scatter(
        x=yield10["observation_date"],
        y=yield10["DFII10"],
        name="10Y Real",
        mode="lines",
        line=dict(
            width=2.5
        )
    )
)


# Breakeven
fig2.add_trace(
    go.Scatter(
        x=yield10["observation_date"],
        y=yield10["Breakeven"],
        name="10Y Breakeven",
        mode="lines",
        line=dict(
            width=2.5,
            dash="dot"
        )
    )
)


fig2.update_layout(
    title="",
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


add_source(
    "FRED — 10Y Nominal / Real Yield",
    "https://fred.stlouisfed.org/graph/?graph_id=145245"
)


# =========================================================
# Divider
# =========================================================

st.markdown(
    '<div class="chart-divider"></div>',
    unsafe_allow_html=True
)


# =========================================================
# 3. Treasury Yield & Curve Spreads
# =========================================================

st.markdown(
    '<div class="section-title">Treasury Yield & Curve Spreads</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="section-description">'
    '2Y / 5Y / 10Y Treasury yields with 2s10s and 5s10s spreads'
    '</div>',
    unsafe_allow_html=True
)


treasury = (
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


treasury = treasury[
    treasury["observation_date"] >= start_date
]


# Spread calculation
treasury["2s10s"] = (
    treasury["DGS10"]
    - treasury["DGS2"]
) * 100


treasury["5s10s"] = (
    treasury["DGS10"]
    - treasury["DGS5"]
) * 100


fig3 = go.Figure()


# =========================================================
# Left Axis: Treasury Yields
# =========================================================

fig3.add_trace(
    go.Scatter(
        x=treasury["observation_date"],
        y=treasury["DGS2"],
        name="2Y",
        mode="lines",
        line=dict(
            width=2.2
        ),
        yaxis="y"
    )
)


fig3.add_trace(
    go.Scatter(
        x=treasury["observation_date"],
        y=treasury["DGS5"],
        name="5Y",
        mode="lines",
        line=dict(
            width=2.2
        ),
        yaxis="y"
    )
)


fig3.add_trace(
    go.Scatter(
        x=treasury["observation_date"],
        y=treasury["DGS10"],
        name="10Y",
        mode="lines",
        line=dict(
            width=2.5
        ),
        yaxis="y"
    )
)


# =========================================================
# Right Axis: Spreads
# =========================================================

fig3.add_trace(
    go.Bar(
        x=treasury["observation_date"],
        y=treasury["2s10s"],
        name="2s10s",
        opacity=0.30,
        yaxis="y2"
    )
)


fig3.add_trace(
    go.Bar(
        x=treasury["observation_date"],
        y=treasury["5s10s"],
        name="5s10s",
        opacity=0.30,
        yaxis="y2"
    )
)


fig3.update_layout(
    title="",

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
        zerolinecolor="#999999",
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
