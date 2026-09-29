from __future__ import annotations

import io
from typing import Iterable

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

from macro_platform.chart_axes import RANGE_OFFSETS, apply_time_axis

CHINA_TREASURY_URL = "https://datacenter.eastmoney.com/api/data/get"
JAPAN_CURRENT_URL = "https://www.mof.go.jp/jgbs/reference/interest_rate/jgbcm.csv"
JAPAN_HISTORY_URL = "https://www.mof.go.jp/jgbs/reference/interest_rate/data/jgbcm_all.csv"

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; MacroDashboard/1.0)",
    "Accept": "*/*",
}


def _empty_frame(prefix: str) -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "observation_date",
            f"{prefix}_2y",
            f"{prefix}_10y",
            f"{prefix}_10y_2y_bp",
        ]
    )


def _cutoff_date() -> pd.Timestamp:
    return pd.Timestamp.now(tz="Asia/Hong_Kong").tz_localize(None).normalize() - pd.DateOffset(years=5, days=14)


@st.cache_data(ttl=3600, show_spinner=False, refresh_mode="background")
def load_china_gov_yields() -> pd.DataFrame:
    """Daily China 2Y / 10Y government yields from Eastmoney's macro dataset."""
    rows: list[dict] = []
    cutoff = _cutoff_date()

    try:
        for page in range(1, 8):
            params = {
                "type": "RPTA_WEB_TREASURYYIELD",
                "sty": "ALL",
                "st": "SOLAR_DATE",
                "sr": "-1",
                "token": "894050c76af8597a853f5b408b759f5d",
                "p": str(page),
                "ps": "500",
                "pageNo": str(page),
                "pageNum": str(page),
            }
            response = requests.get(
                CHINA_TREASURY_URL,
                params=params,
                headers=HTTP_HEADERS,
                timeout=(3.0, 10.0),
            )
            response.raise_for_status()
            payload = response.json() or {}
            result = payload.get("result") or {}
            page_rows = result.get("data") or []
            if not page_rows:
                break
            rows.extend(page_rows)

            dates = pd.to_datetime(
                [item.get("SOLAR_DATE") for item in page_rows],
                errors="coerce",
            )
            if dates.notna().any() and dates.min() <= cutoff:
                break

            total_pages = int(result.get("pages") or page)
            if page >= total_pages:
                break
    except Exception:
        if not rows:
            return _empty_frame("china")

    if not rows:
        return _empty_frame("china")

    frame = pd.DataFrame(rows)
    out = pd.DataFrame(
        {
            "observation_date": pd.to_datetime(frame.get("SOLAR_DATE"), errors="coerce"),
            "china_2y": pd.to_numeric(frame.get("EMM00588704"), errors="coerce"),
            "china_10y": pd.to_numeric(frame.get("EMM00166466"), errors="coerce"),
        }
    )
    out["china_10y_2y_bp"] = (out["china_10y"] - out["china_2y"]) * 100.0
    out = (
        out.dropna(subset=["observation_date"])
        .sort_values("observation_date")
        .drop_duplicates("observation_date", keep="last")
    )
    return out[out["observation_date"] >= cutoff].reset_index(drop=True)


def _parse_japanese_date(value: object) -> pd.Timestamp:
    text = str(value or "").strip()
    if not text:
        return pd.NaT

    # Current MOF files use Japanese eras, e.g. R8.9.28. Handle western
    # dates too so the loader survives a future publication-format change.
    if text[:4].isdigit():
        parsed = pd.to_datetime(text, errors="coerce")
        return pd.Timestamp(parsed) if not pd.isna(parsed) else pd.NaT

    era_base = {"S": 1925, "H": 1988, "R": 2018}
    era = text[:1]
    base = era_base.get(era)
    try:
        year_part, month_part, day_part = text[1:].split(".")
        if base is None:
            return pd.NaT
        return pd.Timestamp(
            year=base + int(year_part),
            month=int(month_part),
            day=int(day_part),
        )
    except Exception:
        return pd.NaT


def _read_japan_csv(url: str) -> pd.DataFrame:
    response = requests.get(url, headers=HTTP_HEADERS, timeout=(3.0, 10.0))
    response.raise_for_status()
    raw = pd.read_csv(
        io.BytesIO(response.content),
        encoding="cp932",
        skiprows=1,
        na_values=["-", ""],
    )
    if raw.empty or "基準日" not in raw.columns:
        return _empty_frame("japan")

    two_col = "2年" if "2年" in raw.columns else None
    ten_col = "10年" if "10年" in raw.columns else None
    if two_col is None or ten_col is None:
        return _empty_frame("japan")

    out = pd.DataFrame(
        {
            "observation_date": raw["基準日"].map(_parse_japanese_date),
            "japan_2y": pd.to_numeric(raw[two_col], errors="coerce"),
            "japan_10y": pd.to_numeric(raw[ten_col], errors="coerce"),
        }
    )
    out["japan_10y_2y_bp"] = (out["japan_10y"] - out["japan_2y"]) * 100.0
    return out.dropna(subset=["observation_date"])


@st.cache_data(ttl=3600, show_spinner=False, refresh_mode="background")
def load_japan_gov_yields() -> pd.DataFrame:
    """Daily constant-maturity JGB yields published by Japan's Ministry of Finance."""
    frames: list[pd.DataFrame] = []
    for url in (JAPAN_HISTORY_URL, JAPAN_CURRENT_URL):
        try:
            frame = _read_japan_csv(url)
            if not frame.empty:
                frames.append(frame)
        except Exception:
            continue

    if not frames:
        return _empty_frame("japan")

    combined = (
        pd.concat(frames, ignore_index=True)
        .sort_values("observation_date")
        .drop_duplicates("observation_date", keep="last")
    )
    cutoff = _cutoff_date()
    return combined[combined["observation_date"] >= cutoff].reset_index(drop=True)


def _latest_date(frames: Iterable[pd.DataFrame]) -> pd.Timestamp | None:
    candidates: list[pd.Timestamp] = []
    for frame in frames:
        if frame.empty or "observation_date" not in frame.columns:
            continue
        value = pd.to_datetime(frame["observation_date"], errors="coerce").max()
        if not pd.isna(value):
            candidates.append(pd.Timestamp(value))
    return max(candidates) if candidates else None


def _slice(frame: pd.DataFrame, start: pd.Timestamp) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    dates = pd.to_datetime(frame["observation_date"], errors="coerce")
    return frame.loc[dates >= start].copy()


def _add_trace(
    fig: go.Figure,
    frame: pd.DataFrame,
    column: str,
    name: str,
    *,
    width: float,
    dash: str | None = None,
    yaxis: str | None = None,
    suffix: str = "%",
) -> None:
    if frame.empty or column not in frame.columns or frame[column].notna().sum() == 0:
        return
    line = {"width": width}
    if dash:
        line["dash"] = dash
    trace = go.Scatter(
        x=frame["observation_date"],
        y=frame[column],
        name=name,
        mode="lines",
        line=line,
        hovertemplate=f"{name}: %{{y:.2f}}{suffix}<extra></extra>",
    )
    if yaxis:
        trace.update(yaxis=yaxis)
    fig.add_trace(trace)


def build_asia_rates_figure(date_range: str) -> go.Figure:
    china = load_china_gov_yields()
    japan = load_japan_gov_yields()
    latest = _latest_date((china, japan))

    fig = go.Figure()
    if latest is None:
        fig.add_annotation(
            text="亚洲国债收益率数据暂不可用",
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
        )
        fig.update_layout(height=440)
        return fig

    offset = RANGE_OFFSETS.get(date_range, RANGE_OFFSETS["1Y"])
    start = latest - offset
    china = _slice(china, start)
    japan = _slice(japan, start)

    _add_trace(fig, china, "china_2y", "China 2Y", width=2.1)
    _add_trace(fig, china, "china_10y", "China 10Y", width=2.8)
    _add_trace(
        fig,
        china,
        "china_10y_2y_bp",
        "China 10Y−2Y (R1)",
        width=2.0,
        dash="dot",
        yaxis="y2",
        suffix=" bp",
    )

    _add_trace(fig, japan, "japan_2y", "Japan 2Y", width=2.1)
    _add_trace(fig, japan, "japan_10y", "Japan 10Y", width=2.8)
    _add_trace(
        fig,
        japan,
        "japan_10y_2y_bp",
        "Japan 10Y−2Y (R1)",
        width=2.0,
        dash="dot",
        yaxis="y2",
        suffix=" bp",
    )

    fig.update_layout(
        height=470,
        template="plotly_white",
        hovermode="x unified",
        dragmode=False,
        margin=dict(l=64, r=76, t=74, b=36, pad=2),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.09,
            xanchor="left",
            x=0.0,
            font=dict(size=10),
            bgcolor="rgba(255,255,255,0)",
        ),
        yaxis=dict(
            title="Government bond yield (%)",
            showgrid=True,
            gridcolor="#e5e7eb",
            griddash="dot",
            zeroline=False,
            fixedrange=True,
            tickformat=".2f",
        ),
        yaxis2=dict(
            title="10Y−2Y spread · bp",
            overlaying="y",
            side="right",
            showgrid=False,
            zeroline=True,
            zerolinecolor="#94a3b8",
            zerolinewidth=1,
            fixedrange=True,
            tickformat=".0f",
        ),
        paper_bgcolor="white",
        plot_bgcolor="white",
    )

    # Apply the selected viewport last so no later layout update can widen it.
    return apply_time_axis(fig, date_range, latest=latest)
