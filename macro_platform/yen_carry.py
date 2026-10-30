"""Observed carry incentives and FX pressure; no inferred positioning or P&L."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from macro_platform.chart_axes import RANGE_OFFSETS, apply_time_axis

SPREAD_NAME = "US−Japan 2Y spread"
FX_NAME = "USD/JPY (R1)"
PRESSURE_NAME = "JPY 20-session appreciation (R2)"
POSITION_NAME = "CFTC JPY speculative net (R3)"


def _observations(frame, column):
    if frame is None or not {"observation_date", column}.issubset(frame.columns):
        return pd.DataFrame(columns=["observation_date", column])
    out = frame[["observation_date", column]].copy()
    out["observation_date"] = pd.to_datetime(out.observation_date, errors="coerce", utc=True).dt.tz_localize(None).dt.normalize()
    out[column] = pd.to_numeric(out[column], errors="coerce").replace([np.inf, -np.inf], np.nan)
    return out.dropna(subset=["observation_date"]).sort_values("observation_date", kind="stable").drop_duplicates("observation_date", keep="last").reset_index(drop=True)


def carry_observations(us, japan, fx):
    """Match yields by date only; calculate FX returns before viewport slicing.

    Twenty sessions means twenty intervals between valid observed FX closes.
    Null current quotes remain null. No forward fill across holiday calendars.
    """
    rates = _observations(us, "DGS2").merge(
        _observations(japan, "japan_2y"), on="observation_date", how="outer").sort_values("observation_date")
    rates["spread_pp"] = rates.DGS2 - rates.japan_2y
    exchange = _observations(fx, "usd_jpy_close")
    exchange.loc[exchange.usd_jpy_close.le(0), "usd_jpy_close"] = np.nan
    valid = exchange.usd_jpy_close.dropna()
    exchange["yen_appreciation_pct"] = (valid.shift(20) / valid - 1) * 100
    return rates, exchange


def build_yen_carry_figure(date_range, *, us, japan, fx, positions=None):
    rates, exchange = carry_observations(us, japan, fx)
    positioning = _observations(positions, "net_contracts")
    positioning["net_10k_contracts"] = positioning.net_contracts / 10000
    sources = ((rates, "spread_pp", SPREAD_NAME, "y", "#536178", "solid", " pp"),
               (exchange, "usd_jpy_close", FX_NAME, "y2", "#4e6cf5", "solid", " JPY/USD"),
               (exchange, "yen_appreciation_pct", PRESSURE_NAME, "y3", "#e88939", "dash", "%"),
               (positioning, "net_10k_contracts", POSITION_NAME, "y4", "#8a61c4", "dot", " 万张"))
    latest_dates = [frame.loc[frame[column].notna(), "observation_date"].max()
                    for frame, column, *_ in sources if frame[column].notna().any()]
    latest = max(latest_dates) if latest_dates else None
    start = latest - RANGE_OFFSETS.get(date_range, RANGE_OFFSETS["1Y"]) if latest is not None else None
    fig = go.Figure()
    missing = []
    for frame, column, name, axis, color, dash, suffix in sources:
        view = frame.loc[frame.observation_date.ge(start)] if start is not None else frame
        if not view[column].notna().any():
            missing.append(name)
            continue
        common = dict(x=view.observation_date, y=view[column], name=name, yaxis=axis,
                      hovertemplate=f"{name}: %{{y:.2f}}{suffix}<extra></extra>")
        if name == POSITION_NAME:
            fig.add_trace(go.Bar(**common, marker=dict(color=color, opacity=0.6), width=4*86400000))
        else:
            fig.add_trace(go.Scatter(**common, mode="lines", connectgaps=False,
                                     line=dict(color=color, width=2.3, dash=dash)))
    fig.update_layout(
        template="plotly_white", height=470, hovermode="x unified", dragmode=False,
        margin=dict(l=64, r=160, t=74, b=36),
        legend=dict(orientation="h", yanchor="bottom", y=1.09, font=dict(size=10)),
        xaxis=dict(domain=[0, 0.81]),
        yaxis=dict(title="US−Japan 2Y · pp", fixedrange=True, tickformat=".2f", zeroline=True),
        yaxis2=dict(title="R1 · JPY/USD", overlaying="y", side="right", anchor="free",
                    position=0.83, showgrid=False, fixedrange=True, tickformat=".1f"),
        yaxis3=dict(title="R2 · %", overlaying="y", side="right", anchor="free",
                    position=0.91, showgrid=False, fixedrange=True, tickformat=".1f", zeroline=True),
        yaxis4=dict(title="R3 · 万张", overlaying="y", side="right", anchor="free",
                    position=0.995, showgrid=False, fixedrange=True, tickformat=".1f", zeroline=True),
        meta={"missing_series": missing},
    )
    if latest is None:
        fig.add_annotation(text="数据暂不可用", x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False)
        return fig
    return apply_time_axis(fig, date_range, latest=latest)
