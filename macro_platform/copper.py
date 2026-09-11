from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from macro_platform.chart_axes import RANGE_OFFSETS, apply_time_axis

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_PATH = ROOT / "data_snapshots" / "copper_market_daily.json"
LB_PER_METRIC_TONNE = 2204.62262185

COLUMNS = [
    "observation_date",
    "comex_price_usd_lb",
    "comex_stock_t",
    "lme_cash_usd_t",
    "lme_3m_usd_t",
    "lme_stock_t",
]


def load_copper_snapshot() -> pd.DataFrame:
    try:
        payload = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
        rows = payload.get("records") if isinstance(payload, dict) else payload
        frame = pd.DataFrame(rows or [])
    except Exception:
        return pd.DataFrame(columns=COLUMNS)

    if frame.empty or "date" not in frame.columns:
        return pd.DataFrame(columns=COLUMNS)

    frame = frame.rename(columns={"date": "observation_date"})
    frame["observation_date"] = pd.to_datetime(frame["observation_date"], errors="coerce")
    for col in COLUMNS[1:]:
        if col not in frame.columns:
            frame[col] = pd.NA
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    return (
        frame.dropna(subset=["observation_date"])
        .sort_values("observation_date")
        .drop_duplicates("observation_date", keep="last")[COLUMNS]
    )


def copper_snapshot_metadata() -> dict:
    try:
        payload = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    return {key: value for key, value in payload.items() if key != "records"}


def _slice(frame: pd.DataFrame, date_range: str) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    latest = frame["observation_date"].max()
    offset = RANGE_OFFSETS.get(date_range, RANGE_OFFSETS["1Y"])
    return frame[frame["observation_date"] >= latest - offset].copy()


def _add_missing(fig: go.Figure, text: str) -> None:
    current = list((fig.layout.meta or {}).get("missing_series", [])) if isinstance(fig.layout.meta, dict) else []
    current.append(text)
    fig.update_layout(meta={"missing_series": current})


def _finish_combined(fig: go.Figure, date_range: str) -> go.Figure:
    fig = apply_time_axis(fig, date_range)
    fig.update_layout(
        height=500,
        margin=dict(l=70, r=132, t=76, b=38, pad=2),
        paper_bgcolor="white",
        plot_bgcolor="white",
        hovermode="x unified",
        hoverlabel=dict(bgcolor="white", font_size=12),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.09,
            xanchor="left",
            x=0.01,
            font=dict(size=10),
            bgcolor="rgba(255,255,255,0.84)",
        ),
        xaxis=dict(domain=[0.0, 0.86]),
        yaxis=dict(
            title="Exchange inventory · kt",
            showgrid=True,
            gridcolor="#e5e7eb",
            griddash="dot",
            zeroline=False,
            fixedrange=True,
            tickformat=",.0f",
            tickfont=dict(size=10),
        ),
        yaxis2=dict(
            title="Copper price · USD/t",
            overlaying="y",
            side="right",
            anchor="free",
            position=0.91,
            showgrid=False,
            zeroline=False,
            fixedrange=True,
            tickformat=",.0f",
            tickfont=dict(size=9),
            ticks="outside",
            ticklen=3,
        ),
        yaxis3=dict(
            title="COMEX−LME 3M · USD/t",
            overlaying="y",
            side="right",
            anchor="free",
            position=0.995,
            showgrid=False,
            zeroline=True,
            zerolinecolor="#94a3b8",
            zerolinewidth=1,
            fixedrange=True,
            tickformat=",.0f",
            tickfont=dict(size=9),
            ticks="outside",
            ticklen=3,
        ),
    )

    missing = list((fig.layout.meta or {}).get("missing_series", [])) if isinstance(fig.layout.meta, dict) else []
    if missing:
        fig.add_annotation(
            text="⚠ 数据缺失：" + " · ".join(missing),
            x=0.006,
            y=0.988,
            xref="paper",
            yref="paper",
            xanchor="left",
            yanchor="top",
            showarrow=False,
            font=dict(size=10, color="#991b1b"),
            bgcolor="rgba(254,242,242,0.94)",
            bordercolor="#fecaca",
            borderwidth=1,
            borderpad=3,
        )
    return fig


def build_copper_flow_spread_figure(date_range: str) -> go.Figure:
    """One-view LME/COMEX copper monitor for inventory migration and venue spread.

    COMEX HG is converted from USD/lb to USD/metric-tonne so it can be compared
    directly with LME 3M. The displayed spread is an indicative venue premium:
    COMEX front-month proxy minus LME 3M. It is not an expiry-matched arbitrage
    quote and therefore should be read as a directional stress / flow signal.
    """
    data = _slice(load_copper_snapshot(), date_range)
    fig = go.Figure()

    comex_stock = data.dropna(subset=["comex_stock_t"]).copy() if "comex_stock_t" in data else pd.DataFrame()
    if not comex_stock.empty:
        comex_stock["stock_kt"] = comex_stock["comex_stock_t"] / 1000.0
        fig.add_trace(
            go.Scatter(
                x=comex_stock["observation_date"],
                y=comex_stock["stock_kt"],
                mode="lines",
                name="COMEX 库存",
                line=dict(width=2.8),
                hovertemplate="COMEX 库存: %{y:,.1f} kt<extra></extra>",
            )
        )
    else:
        _add_missing(fig, "COMEX 库存")

    lme_stock = data.dropna(subset=["lme_stock_t"]).copy() if "lme_stock_t" in data else pd.DataFrame()
    if not lme_stock.empty:
        lme_stock["stock_kt"] = lme_stock["lme_stock_t"] / 1000.0
        fig.add_trace(
            go.Scatter(
                x=lme_stock["observation_date"],
                y=lme_stock["stock_kt"],
                mode="lines",
                name="LME 库存",
                line=dict(width=2.8, dash="dash"),
                hovertemplate="LME 库存: %{y:,.1f} kt<extra></extra>",
            )
        )
    else:
        _add_missing(fig, "LME 库存")

    lme_price = data.dropna(subset=["lme_3m_usd_t"]).copy() if "lme_3m_usd_t" in data else pd.DataFrame()
    if not lme_price.empty:
        fig.add_trace(
            go.Scatter(
                x=lme_price["observation_date"],
                y=lme_price["lme_3m_usd_t"],
                mode="lines",
                name="LME 3M 铜价 (R1)",
                yaxis="y2",
                line=dict(width=2.3),
                hovertemplate="LME 3M: $%{y:,.0f}/t<extra></extra>",
            )
        )
    else:
        _add_missing(fig, "LME 3M 铜价")

    comex_price = data.dropna(subset=["comex_price_usd_lb"]).copy() if "comex_price_usd_lb" in data else pd.DataFrame()
    if not comex_price.empty:
        comex_price["comex_usd_t"] = comex_price["comex_price_usd_lb"] * LB_PER_METRIC_TONNE
        fig.add_trace(
            go.Scatter(
                x=comex_price["observation_date"],
                y=comex_price["comex_usd_t"],
                mode="lines",
                name="COMEX HG 换算价 (R1)",
                yaxis="y2",
                line=dict(width=2.3, dash="dot"),
                customdata=comex_price["comex_price_usd_lb"],
                hovertemplate="COMEX HG: $%{y:,.0f}/t · $%{customdata:.4f}/lb<extra></extra>",
            )
        )
    else:
        _add_missing(fig, "COMEX 铜价")

    spread = data[["observation_date", "comex_price_usd_lb", "lme_3m_usd_t"]].dropna().copy()
    if not spread.empty:
        spread["venue_spread_usd_t"] = spread["comex_price_usd_lb"] * LB_PER_METRIC_TONNE - spread["lme_3m_usd_t"]
        fig.add_trace(
            go.Scatter(
                x=spread["observation_date"],
                y=spread["venue_spread_usd_t"],
                mode="lines",
                name="COMEX−LME 3M 价差 (R2)",
                yaxis="y3",
                line=dict(width=1.8),
                fill="tozeroy",
                hovertemplate="COMEX−LME 3M: $%{y:+,.0f}/t<extra></extra>",
            )
        )
    else:
        _add_missing(fig, "COMEX−LME 3M 价差")

    return _finish_combined(fig, date_range)


# Backward-compatible aliases for callers/tests that still import the old names.
def build_comex_copper_figure(date_range: str) -> go.Figure:
    return build_copper_flow_spread_figure(date_range)


def build_lme_copper_figure(date_range: str) -> go.Figure:
    return build_copper_flow_spread_figure(date_range)
