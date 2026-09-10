from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
VIXEQ_SNAPSHOT_PATH = ROOT / "data_snapshots" / "vixeq_daily.json"


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
