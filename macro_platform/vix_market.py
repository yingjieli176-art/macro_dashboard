"""Dated VIX index quotes; only confirmed closing observations enter daily history."""
from datetime import datetime, time, timedelta, timezone
import json
import math
from pathlib import Path
import threading
from zoneinfo import ZoneInfo

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
QUOTE_URL = "https://cdn-api.cboe.com/api/global/delayed_quotes/quotes/_VIX.json"
QUOTE_PAGE = "https://www.cboe.com/delayed_quotes/_vix/quote_table"
SAVED_QUOTE = ROOT / "data_snapshots/vix_quote.json"
LIVE_QUOTE = ROOT / "static/vix_quote.json"
VIX_HISTORY = ROOT / "data_snapshots/fred_cache/VIXCLS.json"
ET = ZoneInfo("America/New_York")
_WRITE_LOCK = threading.RLock()


def clock_utc(now=None):
    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=timezone.utc)
    return clock.astimezone(timezone.utc)


def parse_cboe_quote(payload, now=None):
    clock = clock_utc(now)
    data = payload.get("data") or {}
    if data.get("symbol") not in {"^VIX", "VIX"} or data.get("security_type") != "index":
        raise ValueError("A VIX index quote is required; futures and other indices are excluded")
    raw = data.get("current_price")
    if isinstance(raw, bool):
        raise ValueError("Invalid VIX price")
    value = float(raw)
    if not math.isfinite(value) or value <= 0:
        raise ValueError("Invalid VIX price")
    # Cboe's quote dashboard labels last_trade_time as ET. The top-level
    # timestamp describes the response and must never replace quote time.
    observed = datetime.fromisoformat(str(data["last_trade_time"]).replace("Z", "+00:00"))
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=ET)
    observed = observed.astimezone(timezone.utc)
    if observed > clock + timedelta(seconds=60):
        raise ValueError("VIX quote time is in the future")
    return {"symbol":"^VIX", "value":value, "observed_at":observed.isoformat(),
            "retrieved_at":clock.isoformat(), "source":"Cboe delayed index quote",
            "source_url":QUOTE_URL, "delayed":True}


def fetch_quote(get=requests.get, now=None):
    response = get(QUOTE_URL, headers={"User-Agent":"Mozilla/5.0 MacroDashboard/1.0",
                                        "Accept":"application/json"}, timeout=(3, 7))
    response.raise_for_status()
    return parse_cboe_quote(response.json(), now=now)


def confirmed_close(quote, now=None):
    if not quote or quote.get("symbol") != "^VIX" or quote.get("source") != "Cboe delayed index quote":
        return None
    observed = datetime.fromisoformat(quote["observed_at"]).astimezone(ET)
    clock = clock_utc(now).astimezone(ET)
    # Cboe disseminates the regular-session VIX through 15:15 CT (16:15 ET).
    # Require that closing-minute quote and wait until 16:30 ET to avoid
    # turning an intraday value into a historical close.
    ready = observed.replace(hour=16, minute=30, second=0, microsecond=0)
    if observed.weekday() >= 5 or not time(16,15) <= observed.time() < time(16,16) or clock < ready:
        return None
    value = float(quote["value"])
    if not math.isfinite(value) or value <= 0:
        return None
    return {"date":observed.date().isoformat(), "value":value}


def read_quote(paths=None, now=None):
    quotes = []
    for path in paths or (LIVE_QUOTE, SAVED_QUOTE):
        try:
            item = json.loads(Path(path).read_text())
            if item.get("source") != "Cboe delayed index quote" or item.get("source_url") != QUOTE_URL:
                continue
            # Reuse the source parser so corrupt snapshots cannot become UI quotes.
            quote = parse_cboe_quote({"data":{"symbol":item["symbol"], "security_type":"index",
                "current_price":item["value"], "last_trade_time":item["observed_at"]}}, now=now)
            quote["retrieved_at"] = item["retrieved_at"]
            quotes.append(quote)
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return max(quotes, key=lambda q:(q["observed_at"],q["retrieved_at"])) if quotes else None


def write_quote(quote, path=LIVE_QUOTE):
    path = Path(path)
    with _WRITE_LOCK:
        previous = read_quote((path,))
        if previous and (previous["observed_at"] > quote["observed_at"] or
                         (previous["observed_at"] == quote["observed_at"] and previous["value"] == quote["value"])):
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".vix.tmp")
        tmp.write_text(json.dumps(quote, ensure_ascii=False, indent=2) + "\n")
        tmp.replace(path)
        return True


def append_confirmed_close(quote, path=VIX_HISTORY, now=None):
    close = confirmed_close(quote, now=now)
    path = Path(path)
    if close is None or not path.exists():
        return False
    from macro_platform.fred_observations import validate_observations
    with _WRITE_LOCK:
        payload = json.loads(path.read_text())
        if payload.get("series_id") != "VIXCLS":
            raise ValueError("VIX daily history identity mismatch")
        records = payload.get("records") or []
        last = max(row["date"] for row in records)
        # Existing official daily observations are never overwritten by quotes.
        if close["date"] <= last:
            return False
        records = [*records, close]
        validate_observations(pd.DataFrame(records), "VIXCLS", date_column="date",
                              value_column="value", min_rows=12, latest_known_date=last, now=now)
        payload.update(records=records, coverage_end=close["date"],
                       fetched_at=int(clock_utc(now).timestamp()))
        payload.setdefault("closing_quote_sources", {})[close["date"]] = quote["source_url"]
        tmp = path.with_suffix(".vix.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",",":")) + "\n")
        tmp.replace(path)
        return True
