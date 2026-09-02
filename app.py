import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from data import get_dgs10, get_dfii10


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


# =========================
# 数据清洗
# =========================

dgs10 = dgs10.dropna(subset=["DGS10"]).copy()
dfii10 = dfii10.dropna(subset=["DFII10"]).copy()

dgs10["observation_date"] = pd.to_datetime(
    dgs10["observation_date"]
)

dfii10["observation_date"] = pd.to_datetime(
    dfii10["observation_date"]
)


# =========================
# 合并数据
# =========================

data = pd.merge(
    dgs10[["observation_date", "DGS10"]],
    dfii10[["observation_date", "DFII10"]],
    on="observation_date",
    how="inner"
)

data = data.sort_values("observation_date")

# 真实相减关系
data["BREAKEVEN10"] = (
    data["DGS10"] - data["DFII10"]
)


# =========================
# 最新数据
# =========================

latest = data.iloc[-1]
previous = data.iloc[-2]

dgs10_change = (
    latest["DGS10"] - previous["DGS10"]
)

dfii10_change = (
    latest["DFII10"] - previous["DFII10"]
)

breakeven_change = (
    latest["BREAKEVEN10"]
    - previous["BREAKEVEN10"]
)


# =========================
# 指标卡
# =========================

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        "10Y Treasury",
        f"{latest['DGS10']:.2f}%",
        f"{dgs10_change:+.2f} pp"
    )

with col2:
    st.metric(
        "10Y TIPS Real Yield",
        f"{latest['DFII10']:.2f}%",
        f"{dfii10_change:+.2f} pp"
    )

with col3:
    st.metric(
        "10Y Treasury − 10Y TIPS",
        f"{latest['BREAKEVEN10']:.2f}%",
        f"{breakeven_change:+.2f} pp"
    )

with col4:
    st.metric(
        "Bitcoin",
        "—",
        "Coming soon"
    )


st.divider()


# =========================
# 时间范围
# =========================

st.subheader("10Y Yield Structure")

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


# =========================
# 筛选数据
# =========================

latest_date = data["observation_date"].max()

start_date = (
    latest_date
    - pd.Timedelta(days=days)
)

chart = data[
    data["observation_date"] >= start_date
].copy()

chart = chart.sort_values("observation_date")


# =========================
# 交易日索引
# =========================

chart["day_index"] = range(len(chart))

chart["date_label"] = chart[
    "observation_date"
].dt.strftime("%m/%d/%y")


# =========================
# 组合图
# =========================

fig = go.Figure()


# Breakeven 柱状图
fig.add_trace(
    go.Bar(
        x=chart["day_index"],
        y=chart["BREAKEVEN10"],
        name="10Y Treasury − 10Y TIPS",
        opacity=0.30,

        customdata=chart["date_label"],

        hovertemplate=(
            "Date: %{customdata}"
            "<br>10Y Treasury − 10Y TIPS: "
            "%{y:.2f}%"
            "<extra></extra>"
        )
    )
)


# 10Y Treasury
fig.add_trace(
    go.Scatter(
        x=chart["day_index"],
        y=chart["DGS10"],
        mode="lines+markers",
        name="10Y Treasury",

        line=dict(width=2),
        marker=dict(size=4),

        customdata=chart["date_label"],

        hovertemplate=(
            "Date: %{customdata}"
            "<br>10Y Treasury: "
            "%{y:.2f}%"
            "<extra></extra>"
        )
    )
)


# 10Y TIPS
fig.add_trace(
    go.Scatter(
        x=chart["day_index"],
        y=chart["DFII10"],
        mode="lines+markers",
        name="10Y TIPS Real Yield",

        line=dict(width=2),
        marker=dict(size=4),

        customdata=chart["date_label"],

        hovertemplate=(
            "Date: %{customdata}"
            "<br>10Y TIPS Real Yield: "
            "%{y:.2f}%"
            "<extra></extra>"
        )
    )
)


# =========================
# X 轴标签频率
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
    # 5Y
    step = 90


tick_positions = chart["day_index"][::step]
tick_labels = chart["date_label"][::step]


# =========================
# 图表样式
# =========================

fig.update_layout(
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
        gridcolor="rgba(0,0,0,0.08)",

        tickangle=0
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


# =========================
# 显示图表
# =========================

st.plotly_chart(
    fig,
    use_container_width=True
)


# =========================
# 数据来源
# =========================

st.markdown("### Data Sources")

st.markdown(
    """
- **10Y Treasury (DGS10)** — 
[FRED: 10-Year Treasury Constant Maturity Rate](https://fred.stlouisfed.org/series/DGS10)

- **10Y TIPS Real Yield (DFII10)** — 
[FRED: 10-Year Treasury Inflation-Indexed Security](https://fred.stlouisfed.org/series/DFII10)

- **10Y Treasury − 10Y TIPS** — 
Calculated directly from the two FRED series above.
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