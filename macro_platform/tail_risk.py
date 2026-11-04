"""Original Cboe SKEW and VVIX daily closes; render without network calls."""
from datetime import datetime, time, timedelta
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SYMBOLS = ("SKEW", "VVIX")
SOURCE_TEMPLATE = "https://cdn-api.cboe.com/api/global/us_indices/daily_prices/{}_History.csv"


def completed_date(now=None):
    local = (now or datetime.now(ZoneInfo("America/New_York"))).astimezone(ZoneInfo("America/New_York"))
    return local.date() if local.time() >= time(16, 15) else local.date() - timedelta(days=1)


def load_tail_risk_snapshot(symbol):
    if symbol not in SYMBOLS:
        raise ValueError(f"Unsupported tail-risk index: {symbol}")
    empty = pd.DataFrame(columns=["observation_date", symbol])
    try:
        payload = json.loads((ROOT / "data_snapshots" / f"{symbol.lower()}_daily.json").read_text())
        if payload.get("symbol") != symbol:
            return empty
        frame = pd.DataFrame(payload["records"])
        frame["observation_date"] = pd.to_datetime(frame["observation_date"], errors="coerce")
        frame[symbol] = pd.to_numeric(frame["close"], errors="coerce")
    except (OSError, ValueError, KeyError, TypeError):
        return empty
    valid = (frame.observation_date.notna() & frame.observation_date.le(pd.Timestamp(completed_date()))
             & frame[symbol].gt(0) & frame[symbol].lt(float("inf")))
    return (frame.loc[valid, ["observation_date", symbol]].sort_values("observation_date")
            .drop_duplicates("observation_date", keep="last"))
