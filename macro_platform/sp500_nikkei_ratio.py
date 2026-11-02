"""S&P 500 market-cap-weighted index / Nikkei 225 relative-price ratio."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from macro_platform.market_history import completed_daily_closes
from macro_platform.request_runtime import http_get, observed_cache

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
ROOT = Path(__file__).resolve().parents[1]
US_EQUITY_SNAPSHOT = ROOT / "data_snapshots/us_equity_daily.json"
NIKKEI_SNAPSHOT = ROOT / "data_snapshots/nikkei225_daily.json"
SERIES = {
    "SP500": {"symbol": "^GSPC", "currency": "USD", "label": "S&P 500（市值加权）"},
    "NIKKEI": {"symbol": "^N225", "currency": "JPY", "label": "日经225"},
}


def _empty():
    return pd.DataFrame(columns=["observation_date", "SP500", "NIKKEI", "ratio"])


def _load_index(key: str) -> pd.DataFrame:
    config = SERIES[key]
    response = http_get(
        YAHOO_CHART_URL.format(symbol="%5EGSPC" if key == "SP500" else "%5EN225"),
        params={"range": "5y", "interval": "1d", "events": "history"},
        headers={"User-Agent": "Mozilla/5.0 (compatible; MacroDashboard/1.0)"},
        timeout=(3.0, 12.0),
    )
    response.raise_for_status()
    payload = response.json() or {}
    nodes = ((payload.get("chart") or {}).get("result") or [])
    if len(nodes) != 1:
        raise ValueError(f"{key}: Yahoo Finance returned no unique history")
    node = nodes[0]
    meta = node.get("meta") or {}
    if meta.get("symbol") != config["symbol"] or meta.get("currency") != config["currency"]:
        raise ValueError(f"{key}: unexpected index symbol or currency")
    if meta.get("instrumentType") != "INDEX" or meta.get("dataGranularity") != "1d":
        raise ValueError(f"{key}: expected daily index closes")
    frame = completed_daily_closes(node)
    if frame.empty:
        raise ValueError(f"{key}: no completed daily closes")
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame = frame.loc[frame["close"].gt(0), ["observation_date", "close"]]
    return frame.rename(columns={"close": key})


def _load_snapshot_index(key: str) -> pd.DataFrame:
    """Read a last-good raw-close history when the live quote endpoint is down."""
    try:
        if key == "SP500":
            payload = json.loads(US_EQUITY_SNAPSHOT.read_text())
            records = payload["series"]["SPX"]["records"]
            frame = pd.DataFrame(records).rename(columns={"date": "observation_date", "close": key})
        else:
            payload = json.loads(NIKKEI_SNAPSHOT.read_text())
            records = payload["records"]
            frame = pd.DataFrame(records).rename(columns={"date": "observation_date", "close": key})
        frame["observation_date"] = pd.to_datetime(frame["observation_date"], errors="coerce")
        frame[key] = pd.to_numeric(frame[key], errors="coerce")
        frame = frame.dropna(subset=["observation_date", key])
        frame = frame.loc[frame[key].gt(0), ["observation_date", key]]
        return frame.sort_values("observation_date").drop_duplicates(
            "observation_date", keep="last"
        ).reset_index(drop=True)
    except (OSError, ValueError, KeyError, TypeError):
        return pd.DataFrame(columns=["observation_date", key])


def _load_index_with_snapshot(key: str) -> pd.DataFrame:
    snapshot = _load_snapshot_index(key)
    try:
        live = _load_index(key)
    except Exception:
        if snapshot.empty:
            raise
        logging.exception("%s live history unavailable; using last-good daily snapshot", key)
        return snapshot
    if snapshot.empty:
        return live
    combined = pd.concat([snapshot, live], ignore_index=True)
    return combined.sort_values("observation_date").drop_duplicates(
        "observation_date", keep="last"
    ).reset_index(drop=True)


@observed_cache(paths=lambda: (US_EQUITY_SNAPSHOT, NIKKEI_SNAPSHOT), ttl=900)
def load_sp500_nikkei_ratio() -> pd.DataFrame:
    """Join same-date completed closes; never forward-fill a closed market."""
    try:
        sp500 = _load_index_with_snapshot("SP500")
        nikkei = _load_index_with_snapshot("NIKKEI")
    except Exception:
        logging.exception("S&P 500 / Nikkei 225 history unavailable")
        return _empty()

    data = sp500.merge(nikkei, on="observation_date", how="inner")
    if data.empty:
        return _empty()
    # Index legs are displayed as integer points; the ratio is calculated
    # from those same integer observations for a transparent, reproducible basis.
    data["SP500"] = data["SP500"].round().astype("int64")
    data["NIKKEI"] = data["NIKKEI"].round().astype("int64")
    data = data.loc[data["NIKKEI"].gt(0) & data["SP500"].gt(0)].copy()
    data["ratio"] = data["SP500"] / data["NIKKEI"]
    return data.sort_values("observation_date").drop_duplicates(
        "observation_date", keep="last"
    ).reset_index(drop=True)


def build_sp500_nikkei_ratio_figure(date_range="5Y") -> go.Figure:
    data = load_sp500_nikkei_ratio()
    fig = go.Figure()
    if data.empty:
        fig.add_annotation(
            text="暂无可用的同日收盘数据", x=0.5, y=0.5, xref="paper", yref="paper",
            showarrow=False, font={"color": "#64748b", "size": 14},
        )
    else:
        # Keep every series in its original unit and scale. Each gets its own
        # axis so the index levels remain directly readable without rebasing.
        fig.add_trace(go.Scatter(
            x=data["observation_date"],
            y=data["ratio"],
            name="比值：S&P 500 ÷ Nikkei 225",
            mode="lines",
            connectgaps=False,
            yaxis="y",
            line={"color": "#7c3aed", "width": 2.6},
            hovertemplate=(
                "%{x|%Y-%m-%d}<br>比值：%{y:.4f}<extra></extra>"
            ),
        ))
        fig.add_trace(go.Scatter(
            x=data["observation_date"],
            y=data["SP500"],
            name="分子：S&P 500（指数点位）",
            mode="lines",
            connectgaps=False,
            yaxis="y2",
            line={"color": "#2563eb", "width": 2},
            hovertemplate=(
                "%{x|%Y-%m-%d}<br>S&P 500：%{y:,.0f} 点<extra></extra>"
            ),
        ))
        fig.add_trace(go.Scatter(
            x=data["observation_date"],
            y=data["NIKKEI"],
            name="分母：日经225（指数点位）",
            mode="lines",
            connectgaps=False,
            yaxis="y3",
            line={"color": "#ea580c", "width": 2},
            hovertemplate=(
                "%{x|%Y-%m-%d}<br>日经225：%{y:,.0f} 点<extra></extra>"
            ),
        ))
    fig.update_layout(
        height=430,
        margin={"l": 72, "r": 142, "t": 62, "b": 42},
        hovermode="x unified",
        legend={"orientation": "h", "y": 1.17, "x": 0},
        xaxis={
            "title": None,
            "showgrid": False,
            "rangeslider": {"visible": False},
            "domain": [0.0, 0.82],
        },
        yaxis={
            "title": "指数点位比值（倍）",
            "showgrid": True,
            "gridcolor": "#e5e7eb",
            "griddash": "dot",
            "zeroline": False,
            "tickformat": ".3f",
        },
        yaxis2={
            "title": "S&P 500（点）",
            "overlaying": "y",
            "side": "right",
            "anchor": "free",
            "position": 0.88,
            "showgrid": False,
            "zeroline": False,
            "tickformat": ",.0f",
        },
        yaxis3={
            "title": "日经225（点）",
            "overlaying": "y",
            "side": "right",
            "anchor": "free",
            "position": 0.99,
            "showgrid": False,
            "zeroline": False,
            "tickformat": ",.0f",
        },
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig
