"""Last verified daily closing levels for the TOPIX price index."""
import json
from pathlib import Path

import pandas as pd

SYMBOL = "998405.T"
SOURCE_URL = f"https://finance.yahoo.co.jp/quote/{SYMBOL}/history"
SNAPSHOT_PATH = Path(__file__).resolve().parents[1] / "data_snapshots/topix_daily.json"


def load_topix_snapshot(path=SNAPSHOT_PATH):
    columns = ["observation_date", "topix_close"]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload["symbol"] != SYMBOL:
            raise ValueError("Unexpected index symbol")
        frame = pd.DataFrame(payload["records"]).rename(columns={"close": "topix_close"})
        frame["observation_date"] = pd.to_datetime(frame.observation_date, format="%Y-%m-%d")
        frame["topix_close"] = pd.to_numeric(frame.topix_close, errors="coerce")
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return pd.DataFrame(columns=columns)
    today = pd.Timestamp.now(tz="Asia/Tokyo").tz_localize(None).normalize()
    valid = (frame.observation_date.le(today) & frame.observation_date.dt.dayofweek.lt(5)
             & frame.topix_close.gt(0) & frame.topix_close.lt(float("inf")))
    return (frame.loc[valid, columns].sort_values("observation_date")
            .drop_duplicates("observation_date", keep="last").reset_index(drop=True))
