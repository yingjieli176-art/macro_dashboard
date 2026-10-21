"""Separate, explicitly measured yen series; never splice BIS and FX observations."""
from __future__ import annotations

import io
import json
from pathlib import Path

import pandas as pd

from macro_platform.request_runtime import observed_cache
from macro_platform.market_history import completed_daily_closes

SERIES = "D.N.B.JP"
SOURCE_URL = "https://data.bis.org/topics/EER/BIS,WS_EER,1.0/D.N.B.JP"
API_URL = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_EER/1.0/D.N.B.JP"
SNAPSHOT = Path(__file__).resolve().parents[1] / "data_snapshots/jpy_neer_daily.json"
MARKET_SNAPSHOT = SNAPSHOT.with_name("jpy_market_daily.json")
MARKET_SOURCE_URL = "https://finance.yahoo.com/quote/JPY%3DX/history/"
MARKET_FORMULA = "10000 / USDJPY"


def yen_index_from_fx(frame):
    """Dollar-denominated yen strength: 10,000 divided by observed USD/JPY."""
    out = frame[["observation_date", "usd_jpy_close"]].copy()
    out["usd_jpy_close"] = pd.to_numeric(out["usd_jpy_close"], errors="coerce")
    out["observation_date"] = pd.to_datetime(out["observation_date"], errors="coerce")
    valid = out.usd_jpy_close.gt(0) & out.usd_jpy_close.lt(float("inf"))
    out = out.loc[valid].dropna().sort_values("observation_date").drop_duplicates("observation_date", keep="last")
    out["jpy_usd_index"] = 10000.0 / out["usd_jpy_close"]
    return out.reset_index(drop=True)


def parse_yahoo_yen(payload, now=None):
    nodes = (payload.get("chart") or {}).get("result") or []
    if len(nodes) != 1:
        raise ValueError("Yahoo USD/JPY response missing")
    node = nodes[0]
    meta = node.get("meta") or {}
    if meta.get("symbol") != "JPY=X" or meta.get("currency") != "JPY" or meta.get("instrumentType") != "CURRENCY":
        raise ValueError("Wrong currency series; expected JPY=X (JPY per USD)")
    # Include completed sessions only. A running intraday quote is not a close.
    frame = completed_daily_closes(node, now=now).rename(columns={"close": "usd_jpy_close"})
    return yen_index_from_fx(frame)


@observed_cache(paths=lambda: (MARKET_SNAPSHOT,))
def load_yen_market_index():
    try:
        payload = json.loads(MARKET_SNAPSHOT.read_text())
        if payload.get("symbol") != "JPY=X" or payload.get("formula") != MARKET_FORMULA:
            raise ValueError("Wrong market yen index snapshot")
        rows = pd.DataFrame(payload["records"]).rename(columns={"date": "observation_date"})
        # The updater only persists completed daily observations. Retain the
        # source close so every displayed index value can be recomputed.
        frame = yen_index_from_fx(rows)
        today = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
        frame = frame.loc[frame.observation_date < today]
        frame.attrs.update({"source": MARKET_SOURCE_URL, "fetched_at": payload.get("fetched_at"),
                            "formula": MARKET_FORMULA})
        return frame
    except (OSError, ValueError, KeyError, TypeError):
        return pd.DataFrame(columns=["observation_date", "usd_jpy_close", "jpy_usd_index"])


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
