"""NVIDIA USD senior CDS par spreads. Only source-identified 1Y/5Y observations."""
import json
import math
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from macro_platform.chart_axes import RANGE_OFFSETS, apply_time_axis

ROOT = Path(__file__).resolve().parents[1]
TENORS = ("1Y", "5Y")


def validate_quote(row):
    issuer = str(row.get("issuer", "")).upper().replace(".", "").strip()
    if issuer not in {"NVIDIA CORP", "NVIDIA CORPORATION"}:
        raise ValueError("NVIDIA reference entity required")
    if row.get("currency") != "USD" or row.get("seniority") != "SENIOR_UNSECURED":
        raise ValueError("USD senior unsecured CDS required")
    if row.get("tenor") not in TENORS or row.get("quote_type") != "par_spread":
        raise ValueError("An explicit 1Y/5Y CDS par spread is required; coupon/upfront/price is not a spread")
    day = pd.Timestamp(row["observation_date"])
    value = float(row["spread_bps"])
    if pd.isna(day) or day.tzinfo is not None or day.normalize() > pd.Timestamp.now(tz="UTC").tz_localize(None).normalize():
        raise ValueError("Invalid/future CDS observation date")
    if not math.isfinite(value) or value < 0 or not row.get("source") or not str(row.get("source_url", "")).startswith("https://"):
        raise ValueError("A finite bp spread and source attribution are required")
    return {**row, "observation_date": day.strftime("%Y-%m-%d"), "spread_bps": value}


def load_nvidia_cds():
    empty = pd.DataFrame(columns=["observation_date", "tenor", "spread_bps"])
    try:
        payload = json.loads((ROOT / "data_snapshots/nvidia_cds_daily.json").read_text())
        valid = []
        for row in payload.get("records", []):
            try:
                valid.append(validate_quote(row))
            except (ValueError, KeyError, TypeError):
                continue
        if not valid:
            return empty
        frame = pd.DataFrame(valid)
        frame["observation_date"] = pd.to_datetime(frame.observation_date)
        return frame.sort_values("observation_date").drop_duplicates(["observation_date", "tenor"], keep="last")
    except (OSError, ValueError, TypeError):
        return empty


def build_nvidia_cds_figure(date_range="5Y"):
    data = load_nvidia_cds()
    if not data.empty:
        data = data.loc[data.observation_date >= data.observation_date.max() - RANGE_OFFSETS.get(date_range, RANGE_OFFSETS["1Y"])]
    fig = go.Figure()
    missing = []
    for tenor, color in (("1Y", "#5070dd"), ("5Y", "#dc2626")):
        part = data.loc[data.tenor.eq(tenor)]
        if part.empty:
            missing.append("NVIDIA CDS " + tenor)
        else:
            fig.add_trace(go.Scatter(x=part.observation_date, y=part.spread_bps, mode="lines+markers",
                name="NVIDIA CDS " + tenor, line=dict(color=color, width=2.4), connectgaps=False,
                hovertemplate=tenor + ": %{y:.2f} bp<extra></extra>"))
    fig.update_layout(height=420, yaxis_title="CDS par spread · bp", meta={"missing_series": missing},
                      paper_bgcolor="white", plot_bgcolor="white", hovermode="x unified")
    return apply_time_axis(fig, date_range) if fig.data else fig
