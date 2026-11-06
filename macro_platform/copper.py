from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from macro_platform.chart_axes import RANGE_OFFSETS, apply_time_axis
from macro_platform.copper_tcrc import load_tcrc_snapshot

TCRC_LINE_HISTORY = True

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
    "wti_usd_bbl",
    "vvix",
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
        # An exchange price or *published physical inventory* cannot be
        # negative. A single isolated "0" after 600k tonnes is an invalid
        # fixing, not a genuine complete withdrawal of all warehouse stock.
        # Keep missing as NA: NEVER forward-fill or interpolate the date.
        frame.loc[~(frame[col].gt(0) & frame[col].lt(float("inf"))), col] = float("nan")
    today = pd.Timestamp.now(tz="Europe/London").tz_localize(None).normalize()
    frame = frame.loc[frame.observation_date.le(today)]
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
    # Keep the suspect value in the original source snapshot for auditability.
    # It is deliberately omitted from the plotted observations.
    if not data.empty:
        # This statement is static; avoid rereading 300KB of JSON on each
        # Streamlit rerun just to compose a source-quality explanation.
        fig.update_layout(meta={"data_quality_notes": [
            "近期 COMEX 库存由 CME 原始日报补充，短吨换算为公吨，并使用库存活动日；COCHILCO 异常零值及未发布日期保持缺失。"
        ]})

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

    for field, name, axis, template, color in (
        ("wti_usd_bbl", "WTI 原油 (R3)", "y4", "WTI: $%{y:.2f}/bbl<extra></extra>", "#b45309"),
    ):
        observed = data.dropna(subset=[field])
        if observed.empty:
            _add_missing(fig, name)
        else:
            fig.add_trace(go.Scatter(x=observed["observation_date"], y=observed[field],
                                     mode="lines", name=name, yaxis=axis,
                                     line=dict(width=2, color=color), hovertemplate=template))

    # Use only matching observed dates. No carry-forward across market holidays.
    ratio = data[["observation_date", "comex_price_usd_lb", "wti_usd_bbl"]].dropna()
    if ratio.empty:
        _add_missing(fig, "铜油比")
    else:
        fig.add_trace(go.Scatter(
            x=ratio["observation_date"],
            y=ratio["comex_price_usd_lb"] * LB_PER_METRIC_TONNE / ratio["wti_usd_bbl"],
            mode="lines", name="铜油比 (R4)", yaxis="y5",
            line=dict(width=2, color="#0891b2"),
            hovertemplate="铜油比: %{y:.2f} bbl/t<extra></extra>"))

    # Join the actual dated fixings visually, without creating observations
    # for the dates between them. The markers identify the available quotes.
    charges = _slice(load_tcrc_snapshot(), date_range)
    for field, name, axis, unit, color, dash in (
        ("tc_usd_dmt", "TC（粗炼费，R5）", "y6", "USD/dmt", "#15803d", "solid"),
        ("rc_cents_lb", "RC（精炼费，TC÷10，R6）", "y7", "US cents/lb", "#be185d", "dash"),
    ):
        if charges.empty:
            _add_missing(fig, name)
            continue
        fig.add_trace(go.Scatter(
            x=charges["observation_date"], y=charges[field], name=name,
            yaxis=axis, mode="lines+markers", line=dict(width=2.6, color=color, dash=dash),
            marker=dict(size=4), connectgaps=False,
            meta={"observation_cadence": "weekly"},
            hovertemplate=name + ": %{y:.3f} " + unit + "<extra></extra>"))

    fig.data = tuple(sorted(fig.data, key=lambda trace: int((trace.yaxis or "y")[1:] or "1")))
    fig = _finish_combined(fig, date_range)
    # Original inventory, copper price and venue spread retain separate units.
    for index, title, position in ((4, "WTI · USD/bbl", 0.86),
                                   (5, "Copper / WTI · bbl/t", 0.98),
                                   (6, "TC · USD/dmt", 0.98),
                                   (7, "RC · US cents/lb", 0.99)):
        fig.update_layout(**{f"yaxis{index}": dict(
            title=title, overlaying="y", side="right", anchor="free",
            position=position, showgrid=False, zeroline=False, fixedrange=True,
            tickformat=",.2f", tickfont=dict(size=9))})
    fig.update_layout(xaxis_domain=[0, 0.60], margin_r=180,
                      yaxis2_position=0.62, yaxis3_position=0.74)
    if not charges.empty:
        fig.update_layout(xaxis_domain=[0, 0.48], margin_r=210,
            yaxis2_position=0.51, yaxis3_position=0.60,
            yaxis4_position=0.69, yaxis5_position=0.78,
            yaxis6_position=0.87, yaxis7_position=0.98)
    return fig


# Backward-compatible aliases for callers/tests that still import the old names.
def build_comex_copper_figure(date_range: str) -> go.Figure:
    return build_copper_flow_spread_figure(date_range)


def build_lme_copper_figure(date_range: str) -> go.Figure:
    return build_copper_flow_spread_figure(date_range)
