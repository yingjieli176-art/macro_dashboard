"""Published SqueezeMetrics SPX dollar GEX; no invented dealer inventory."""
from io import StringIO
import json
from pathlib import Path

import numpy as np
import pandas as pd

from macro_platform.tail_risk import completed_date

SOURCE_URL = "https://squeezemetrics.com/monitor/static/DIX.csv"
PAGE_URL = "https://squeezemetrics.com/monitor/dix"
SNAPSHOT = Path(__file__).resolve().parents[1] / "data_snapshots/spx_gex_daily.json"
SERIES_NAME = "GEX 做市商伽马（十亿美元，R5）"
IDENTITY = {"symbol": "SPX_GEX", "source": "SqueezeMetrics", "unit": "USD per SPX point",
            "methodology": "Published SPX dollar GEX; display divides by 1e9"}


def _records(records, now=None):
    frame = pd.DataFrame(records)
    if frame.empty or not {"observation_date", "gex_usd", "spx_close"}.issubset(frame):
        raise ValueError("Missing dated GEX observations")
    dates = pd.to_datetime(frame.observation_date, format="%Y-%m-%d", errors="raise")
    if dates.isna().any() or dates.duplicated().any() or dates.gt(pd.Timestamp(completed_date(now))).any():
        raise ValueError("Invalid, duplicate or future GEX date")
    for column in ("gex_usd", "spx_close"):
        if frame[column].map(lambda v: isinstance(v, bool)).any():
            raise ValueError("Boolean is not a GEX observation")
        frame[column] = pd.to_numeric(frame[column], errors="raise")
        if not np.isfinite(frame[column]).all():
            raise ValueError("Nonfinite GEX observation")
    if frame.spx_close.le(0).any():
        raise ValueError("Invalid source SPX close")
    frame["observation_date"] = dates.dt.strftime("%Y-%m-%d")
    return frame[["observation_date", "gex_usd", "spx_close"]].sort_values("observation_date").to_dict("records")


def parse_csv(text, now=None):
    frame = pd.read_csv(StringIO(text))
    if not {"date", "price", "dix", "gex"}.issubset(frame):
        raise ValueError("Not the public SqueezeMetrics DIX/GEX file")
    return _records(frame.rename(columns={"date": "observation_date", "gex": "gex_usd",
                                         "price": "spx_close"}).to_dict("records"), now)


def prepare_snapshot(text, previous=None, now=None):
    incoming = parse_csv(text, now)
    prior = []
    if previous is not None:
        if any(previous.get(key) != value for key, value in IDENTITY.items()):
            raise ValueError("Wrong GEX snapshot identity or unit")
        prior = _records(previous.get("records", []), now)
        if incoming[-1]["observation_date"] < prior[-1]["observation_date"]:
            raise ValueError("GEX source date moved backwards")
    merged = {row["observation_date"]: row for row in prior}
    merged.update({row["observation_date"]: row for row in incoming})
    records = [merged[day] for day in sorted(merged)]
    if records == prior:
        return None
    stamp = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    return {**IDENTITY, "source_url": SOURCE_URL, "updated_at": stamp.isoformat(),
            "coverage_start": records[0]["observation_date"],
            "coverage_end": records[-1]["observation_date"],
            "record_count": len(records), "records": records}


def load_gex_snapshot(path=SNAPSHOT, now=None):
    empty = pd.DataFrame(columns=["observation_date", "GEX_BN"])
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if any(payload.get(key) != value for key, value in IDENTITY.items()):
            return empty
        frame = pd.DataFrame(_records(payload["records"], now))
        frame["observation_date"] = pd.to_datetime(frame.observation_date)
        frame["GEX_BN"] = frame.gex_usd / 1_000_000_000
        return frame[["observation_date", "GEX_BN"]]
    except (OSError, ValueError, KeyError, TypeError):
        return empty
