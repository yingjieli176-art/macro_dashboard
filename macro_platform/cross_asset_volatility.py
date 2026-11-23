"""Cross-asset option-implied volatility, with independently sourced observations.

OVX: FRED OVXCLS (30-day oil ETF option volatility).
MOVE: existing validated ICE BofA ^MOVE daily-close snapshot.
EUR/USD: Saxo Bank *one-month ATM* implied-volatility quotes, never EVZ or
realized EUR/USD volatility. Missing quotes stay missing, not estimated.
"""
from datetime import datetime, timezone
import json
import logging
import math
import os
from pathlib import Path
import threading

import pandas as pd
import plotly.graph_objects as go

from macro_platform import jpy_implied_vol as saxobank
from macro_platform import move_index
from macro_platform.chart_axes import apply_time_axis

SAXO_URL = saxobank.SOURCE_URL
FRED_URL = "https://fred.stlouisfed.org/series/OVXCLS"
MOVE_URL = move_index.SOURCE_URL
CME_REFERENCE_URL = "https://www.cmegroup.com/markets/fx/g10/euro-fx/quotes/options"
SNAPSHOT = Path(__file__).resolve().parents[1] / "data_snapshots/eurusd_1m_atm_saxo.json"
IDENTITY = {"symbol": "EURUSD_1M_ATM_SAXO", "source": "Saxo Bank", "pair": "EURUSD",
            "tenor": "1M", "quote_type": "ATM", "unit": "percent"}
LOCK = threading.RLock()


def _validate_records(payload, now=None):
    if any(payload.get(k) != v for k, v in IDENTITY.items()):
        raise ValueError("Unexpected EURUSD 1M ATM snapshot identity")
    records = [saxobank._validate_record(row, now) for row in payload.get("records", ())]
    dates = [row["observation_date"] for row in records]
    if dates != sorted(set(dates)):
        raise ValueError("Duplicate or unsorted EURUSD implied volatility dates")
    return records


def load_eurusd_snapshot(path=SNAPSHOT):
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return _validate_records(payload)
    except (OSError, ValueError, KeyError, TypeError, OverflowError):
        return []


def accept_saxo_report(document, path=SNAPSHOT, now=None):
    """Append exactly dated, source-validated 1M ATM observations."""
    quote = saxobank.parse_quote(document, now=now, tenor="1m", pair="EURUSD")
    with LOCK:
        prior = load_eurusd_snapshot(path)
        if prior and quote["observation_timestamp"] < prior[-1]["observation_timestamp"]:
            return prior
        combined = {row["observation_date"]: row for row in prior}
        combined[quote["observation_date"]] = quote
        records = [combined[key] for key in sorted(combined)]
        if records == prior:
            return records
        path.parent.mkdir(parents=True, exist_ok=True)
        stamped = pd.Timestamp(now if now is not None else datetime.now(timezone.utc))
        if stamped.tzinfo is None:
            stamped = stamped.tz_localize("UTC")
        payload = dict(IDENTITY, source_url=SAXO_URL,
                       updated_at=stamped.isoformat(), records=records)
        temp = path.with_suffix(".tmp")
        try:
            temp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)
        return records


def _valid_series(frame, column, minimum=0, maximum=10000):
    if frame is None or frame.empty or not {"observation_date", column}.issubset(frame.columns):
        return pd.DataFrame(columns=["observation_date", column])
    data = frame[["observation_date", column]].copy()
    data["observation_date"] = pd.to_datetime(data["observation_date"], errors="coerce")
    data[column] = pd.to_numeric(data[column], errors="coerce")
    data = data.dropna(subset=["observation_date", column])
    data = data.loc[data[column].gt(minimum) & data[column].lt(maximum)]
    return data.drop_duplicates("observation_date", keep="last").sort_values("observation_date")


def build_figure(date_range="5Y", *, ovx=None, move=None, eurusd_records=None):
    fig = go.Figure()
    sources = (
        ("OVXCLS", ovx, "OVX · 原油30天隐含波动率", "#ea580c", "y", "%"),
        ("MOVE", move, "MOVE · 美债期权波动率", "#0e7490", "y2", "指数点"),
    )
    missing = []
    for column, frame, label, color, axis, unit in sources:
        valid = _valid_series(frame, column)
        if valid.empty:
            missing.append(label)
            continue
        fig.add_trace(go.Scatter(x=valid.observation_date, y=valid[column],
            name=label, yaxis=axis, mode="lines", connectgaps=False,
            line={"color":color,"width":2.8},
            meta={"observation_cadence":"daily"},
            hovertemplate="%{x|%Y-%m-%d}<br>"+label+": %{y:.2f} "+unit+"<extra></extra>"))
    name = "EUR/USD 1M ATM 隐含波动率（Saxo）"
    rows = eurusd_records if eurusd_records is not None else load_eurusd_snapshot()
    if rows:
        try:
            validated = _validate_records(dict(IDENTITY, records=rows))
        except (ValueError, KeyError, TypeError, OverflowError):
            validated = []
        if validated:
            fig.add_trace(go.Scatter(
                x=[row["observation_date"] for row in validated],
                y=[row["value"] for row in validated],
                customdata=[row["observation_timestamp"] for row in validated],
                name=name, yaxis="y3", mode="lines+markers", connectgaps=False,
                marker={"size":5}, line={"color":"#7c3aed","width":2.6},
                meta={"observation_cadence":"daily"},
                hovertemplate="EUR/USD 1M ATM: %{y:.2f}%<br>Saxo: %{customdata}<extra></extra>"))
        else:
            missing.append(name)
    else:
        missing.append(name)
    fig.update_layout(
        yaxis={"title":"L · OVX · 年化%", "showgrid":True},
        yaxis2={"title":"R1 · MOVE · 指数点", "overlaying":"y","side":"right",
                "anchor":"free","position":0.84,"showgrid":False},
        yaxis3={"title":"R2 · EUR/USD 1M ATM · 年化%", "overlaying":"y",
                "side":"right","anchor":"free","position":0.98,"showgrid":False},
        xaxis={"domain":[0.0,0.8]},
        margin={"l":66,"r":160,"t":95,"b":45},
        legend={"orientation":"h","x":0,"y":1.13},
        meta={"missing_series":missing, "axis_order":["y","y2","y3"],
              "preserve_axis_titles":["y","y2","y3"]},
    )
    return apply_time_axis(fig, date_range) if fig.data else fig
