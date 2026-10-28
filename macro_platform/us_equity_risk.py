from __future__ import annotations

import json
import math
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
VIXEQ_SNAPSHOT_PATH = ROOT / "data_snapshots" / "vixeq_daily.json"
CORRELATION_SYMBOLS = ("COR1M", "COR3M")


def load_correlation_snapshot(symbol: str) -> pd.DataFrame:
    """Read original Cboe closes without requests, interpolation or scaling."""
    if symbol not in CORRELATION_SYMBOLS:
        raise ValueError(f"Unsupported correlation index: {symbol}")
    empty = pd.DataFrame(columns=["observation_date", symbol])
    path = ROOT / "data_snapshots" / f"{symbol.lower()}_daily.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("symbol") != symbol:
            return empty
        frame = pd.DataFrame(payload.get("records") or [])
        frame["observation_date"] = pd.to_datetime(frame["observation_date"], errors="coerce")
        frame[symbol] = pd.to_numeric(frame["close"], errors="coerce")
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return empty
    # Today's bar is incomplete until the US cash market close. Retain
    # genuine historical dates only; correlation points are not vol points.
    now = datetime.now(ZoneInfo("America/New_York"))
    cutoff = now.date() if now.time() >= time(16, 15) else now.date() - timedelta(days=1)
    valid = (frame["observation_date"].le(pd.Timestamp(cutoff))
             & frame[symbol].map(math.isfinite) & frame[symbol].between(-100, 100))
    return (frame.loc[valid].dropna(subset=["observation_date", symbol])
            .sort_values("observation_date").drop_duplicates("observation_date", keep="last")
            [["observation_date", symbol]])


def load_vixeq_snapshot() -> pd.DataFrame:
    """Load the persisted Cboe VIXEQ daily close history.

    VIXEQ measures market-cap-weighted 30-day implied volatility across a
    basket of S&P 500 constituent stocks. The dashboard deliberately reads a
    repository snapshot instead of depending on a live Cboe request at render
    time, so transient network failures do not blank the chart.
    """
    try:
        payload = json.loads(VIXEQ_SNAPSHOT_PATH.read_text(encoding="utf-8"))
        rows = payload.get("records") if isinstance(payload, dict) else payload
        frame = pd.DataFrame(rows or [])
    except Exception:
        return pd.DataFrame(columns=["observation_date", "VIXEQ"])

    if frame.empty or "observation_date" not in frame.columns or "close" not in frame.columns:
        return pd.DataFrame(columns=["observation_date", "VIXEQ"])

    frame["observation_date"] = pd.to_datetime(frame["observation_date"], errors="coerce")
    frame["VIXEQ"] = pd.to_numeric(frame["close"], errors="coerce")
    now = datetime.now(ZoneInfo("America/New_York"))
    cutoff = now.date() if now.time() >= time(16, 15) else now.date() - timedelta(days=1)
    frame = frame.loc[frame.observation_date.le(pd.Timestamp(cutoff))
                      & frame.VIXEQ.gt(0) & frame.VIXEQ.lt(float("inf"))]
    return (
        frame.dropna(subset=["observation_date", "VIXEQ"])
        .sort_values("observation_date")
        .drop_duplicates("observation_date", keep="last")[["observation_date", "VIXEQ"]]
    )


def vixeq_snapshot_metadata() -> dict:
    try:
        payload = json.loads(VIXEQ_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    return {key: value for key, value in payload.items() if key != "records"}
