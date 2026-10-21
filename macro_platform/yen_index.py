"""Original BIS daily broad nominal yen index (2020=100), D.N.B.JP."""
from __future__ import annotations

import io
import json
from pathlib import Path

import pandas as pd

from macro_platform.request_runtime import observed_cache

SERIES = "D.N.B.JP"
SOURCE_URL = "https://data.bis.org/topics/EER/BIS,WS_EER,1.0/D.N.B.JP"
API_URL = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_EER/1.0/D.N.B.JP"
SNAPSHOT = Path(__file__).resolve().parents[1] / "data_snapshots/jpy_neer_daily.json"


def _observations(dates, values, today=None):
    frame = pd.DataFrame({"observation_date": pd.to_datetime(dates, errors="coerce"),
                          "jpy_neer": pd.to_numeric(values, errors="coerce")})
    frame = frame.dropna()
    if ((frame.jpy_neer <= 0) | (frame.jpy_neer == float("inf"))).any():
        raise ValueError("Invalid BIS yen index observation")
    today = pd.Timestamp(today) if today is not None else pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
    frame = frame.loc[frame.observation_date < today]
    return frame.sort_values("observation_date").drop_duplicates("observation_date", keep="last").reset_index(drop=True)


def parse_bis_yen_csv(text, today=None):
    raw = pd.read_csv(io.StringIO(text))
    expected = {"FREQ": "D", "EER_TYPE": "N", "EER_BASKET": "B", "REF_AREA": "JP"}
    if not set(expected).union({"TIME_PERIOD", "OBS_VALUE", "UNIT_MEASURE"}).issubset(raw.columns):
        raise ValueError("BIS yen response is missing series metadata")
    # Reject an accidental real/monthly/narrow/other-country response.
    if raw.empty or any(not raw[column].eq(value).all() for column, value in expected.items()):
        raise ValueError("Unexpected BIS series; expected D.N.B.JP")
    if not raw.UNIT_MEASURE.astype(str).eq("882").all():
        raise ValueError("Unexpected BIS base; expected index 2020=100 (882)")
    return _observations(raw.TIME_PERIOD, raw.OBS_VALUE, today)


@observed_cache(paths=lambda: (SNAPSHOT,))
def load_yen_index():
    """Read the verified source snapshot without blocking a chart on a network call."""
    try:
        payload = json.loads(SNAPSHOT.read_text())
        if payload.get("series_id") != SERIES or payload.get("unit") != "Index, 2020=100":
            raise ValueError("Wrong yen index snapshot metadata")
        rows = pd.DataFrame(payload["records"])
        frame = _observations(rows["date"], rows["value"])
        frame.attrs.update({"source": SOURCE_URL, "fetched_at": payload.get("fetched_at")})
        return frame
    except (OSError, ValueError, KeyError, TypeError):
        return pd.DataFrame(columns=["observation_date", "jpy_neer"])
