from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from macro_platform.chart_axes import RANGE_OFFSETS, apply_time_axis

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_PATH = ROOT / "data_snapshots" / "copper_market_daily.json"

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


def _base_figure(date_range: str, *, inventory_title: str, price_title: str) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        height=440,
        margin=dict(l=68, r=86, t=72, b=38, pad=2),
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
            bgcolor="rgba(255,255,255,0.82)",
        ),
        xaxis=dict(domain=[0.0, 0.92]),
        yaxis=dict(
            title=inventory_title,
            showgrid=True,
            gridcolor="#e5e7eb",
            griddash="dot",
            zeroline=False,
            fixedrange=True,
            tickfont=dict(size=10),
        ),
        yaxis2=dict(
            title=price_title,
            overlaying="y",
            side="right",
            anchor="free",
            position=0.99,
            showgrid=False,
            zeroline=False,
            fixedrange=True,
            tickfont=dict(size=9),
            ticks="outside",
            ticklen=3,
        ),
    )
    return apply_time_axis(fig, date_range)


def _add_missing(fig: go.Figure, text: str) -> None:
    current = list((fig.layout.meta or {}).get("missing_series", [])) if isinstance(fig.layout.meta, dict) else []
    current.append(text)
    fig.update_layout(meta={"missing_series": current})


def _finish(fig: go.Figure, date_range: str, inventory_title: str, price_title: str) -> go.Figure:
    fig = apply_time_axis(fig, date_range)
    fig.update_layout(
        xaxis=dict(domain=[0.0, 0.92]),
        yaxis=dict(title=inventory_title, tickformat=",.0f"),
        yaxis2=dict(
            title=price_title,
            overlaying="y",
            side="right",
            anchor="free",
            position=0.99,
            showgrid=False,
            fixedrange=True,
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


def build_comex_copper_figure(date_range: str) -> go.Figure:
    data = _slice(load_copper_snapshot(), date_range)
    fig = go.Figure()

    inventory = data.dropna(subset=["comex_stock_t"]).copy() if "comex_stock_t" in data else pd.DataFrame()
    if not inventory.empty:
        inventory["comex_stock_kt"] = inventory["comex_stock_t"] / 1000.0
        fig.add_trace(
            go.Scatter(
                x=inventory["observation_date"],
                y=inventory["comex_stock_kt"],
                mode="lines",
                name="COMEX 库存",
                line=dict(width=2.8),
                hovertemplate="COMEX 库存: %{y:,.1f} kt<extra></extra>",
            )
        )
    else:
        _add_missing(fig, "COMEX 库存")

    price = data.dropna(subset=["comex_price_usd_lb"]).copy() if "comex_price_usd_lb" in data else pd.DataFrame()
    if not price.empty:
        fig.add_trace(
            go.Scatter(
                x=price["observation_date"],
                y=price["comex_price_usd_lb"],
                mode="lines",
                name="COMEX 铜价 · HG (R1)",
                yaxis="y2",
                line=dict(width=2.5, dash="dot"),
                hovertemplate="COMEX HG: $%{y:.4f}/lb<extra></extra>",
            )
        )
    else:
        _add_missing(fig, "COMEX 铜价")

    return _finish(fig, date_range, "COMEX Inventory · kt", "HG · USD/lb")


def build_lme_copper_figure(date_range: str) -> go.Figure:
    data = _slice(load_copper_snapshot(), date_range)
    fig = go.Figure()

    inventory = data.dropna(subset=["lme_stock_t"]).copy() if "lme_stock_t" in data else pd.DataFrame()
    if not inventory.empty:
        inventory["lme_stock_kt"] = inventory["lme_stock_t"] / 1000.0
        fig.add_trace(
            go.Scatter(
                x=inventory["observation_date"],
                y=inventory["lme_stock_kt"],
                mode="lines",
                name="LME 铜库存",
                line=dict(width=2.8),
                hovertemplate="LME 铜库存: %{y:,.1f} kt<extra></extra>",
            )
        )
    else:
        _add_missing(fig, "LME 铜库存")

    cash = data.dropna(subset=["lme_cash_usd_t"]).copy() if "lme_cash_usd_t" in data else pd.DataFrame()
    if not cash.empty:
        fig.add_trace(
            go.Scatter(
                x=cash["observation_date"],
                y=cash["lme_cash_usd_t"],
                mode="lines",
                name="LME Cash 铜价 (R1)",
                yaxis="y2",
                line=dict(width=2.6),
                hovertemplate="LME Cash: $%{y:,.0f}/t<extra></extra>",
            )
        )
    else:
        _add_missing(fig, "LME Cash 铜价")

    three_month = data.dropna(subset=["lme_3m_usd_t"]).copy() if "lme_3m_usd_t" in data else pd.DataFrame()
    if not three_month.empty:
        fig.add_trace(
            go.Scatter(
                x=three_month["observation_date"],
                y=three_month["lme_3m_usd_t"],
                mode="lines",
                name="LME 3M 铜价 (R1)",
                yaxis="y2",
                line=dict(width=2.0, dash="dot"),
                hovertemplate="LME 3M: $%{y:,.0f}/t<extra></extra>",
            )
        )
    else:
        _add_missing(fig, "LME 3M 铜价")

    return _finish(fig, date_range, "LME Inventory · kt", "Copper · USD/t")
