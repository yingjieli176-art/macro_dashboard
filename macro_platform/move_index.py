"""ICE BofA MOVE index closes distributed through Yahoo's ^MOVE feed."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from macro_platform.market_history import completed_daily_closes
from macro_platform.tail_risk import completed_date

SYMBOL = "^MOVE"
SERIES_NAME = "MOVE 债市波动率（R4）"
SOURCE_URL = "https://finance.yahoo.com/quote/%5EMOVE/history/"
METHOD_URL = "https://developer.ice.com/fixed-income-data-services/catalog/ice-data-indices-move-index"
SNAPSHOT = Path(__file__).resolve().parents[1] / "data_snapshots/move_daily.json"


def validate_records(records, now=None):
    frame = pd.DataFrame(records)
    if frame.empty or not {"observation_date", "close"}.issubset(frame):
        raise ValueError("Missing MOVE observations")
    dates = pd.to_datetime(frame.observation_date, format="%Y-%m-%d", errors="raise")
    values = pd.to_numeric(frame.close, errors="raise")
    if (dates.isna().any() or dates.duplicated().any()
            or dates.gt(pd.Timestamp(completed_date(now))).any()
            or not np.isfinite(values).all() or values.le(0).any()
            or frame.close.map(lambda value: isinstance(value, bool)).any()):
        raise ValueError("Invalid MOVE dates or closes")
    frame["observation_date"] = dates.dt.strftime("%Y-%m-%d")
    frame["close"] = values
    return frame[["observation_date", "close"]].sort_values("observation_date").to_dict("records")


def parse_yahoo(payload, now=None):
    chart = payload.get("chart") or {}
    result = chart.get("result") or []
    if chart.get("error") or len(result) != 1:
        raise ValueError("Invalid MOVE chart response")
    meta = result[0].get("meta") or {}
    if meta.get("symbol") != SYMBOL or meta.get("instrumentType") != "INDEX":
        raise ValueError("Wrong index; expected ^MOVE")
    # Yahoo currently mislabels the longName. Use the symbol's dated close
    # series, cross-checked against MOVE at EODData/Fidelity, never that name.
    return validate_records(completed_daily_closes(result[0], now).to_dict("records"), now)


def prepare_snapshot(payload, previous=None, now=None):
    incoming = parse_yahoo(payload, now)
    prior = []
    if previous is not None:
        if previous.get("symbol") != SYMBOL or previous.get("unit") != "index points":
            raise ValueError("Wrong MOVE snapshot identity")
        prior = validate_records(previous["records"], now)
        if incoming[-1]["observation_date"] < prior[-1]["observation_date"]:
            raise ValueError("MOVE source regressed")
    records = {row["observation_date"]: row for row in prior}
    records.update({row["observation_date"]: row for row in incoming})
    records = [records[day] for day in sorted(records)]
    if records == prior:
        return None
    stamp = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    return {"symbol": SYMBOL, "name": "ICE BofA MOVE Index", "unit": "index points",
            "source": "Yahoo Finance daily ^MOVE closes", "source_url": SOURCE_URL,
            "methodology_url": METHOD_URL, "updated_at": stamp.isoformat(),
            "coverage_start": records[0]["observation_date"], "coverage_end": records[-1]["observation_date"],
            "record_count": len(records), "records": records}


def load_move_snapshot(path=SNAPSHOT, now=None):
    empty = pd.DataFrame(columns=["observation_date", "MOVE"])
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("symbol") != SYMBOL or payload.get("unit") != "index points":
            return empty
        frame = pd.DataFrame(validate_records(payload["records"], now))
        frame["observation_date"] = pd.to_datetime(frame.observation_date)
        return frame.rename(columns={"close": "MOVE"})
    except (OSError, ValueError, TypeError, KeyError):
        return empty
