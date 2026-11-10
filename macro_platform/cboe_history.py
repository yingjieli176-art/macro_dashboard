"""Supplement a lagging Cboe CSV with Cboe's dated daily chart closes."""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
import math

import requests

from macro_platform.tail_risk import completed_date
from macro_platform.vix_market import confirmed_close, parse_cboe_quote

QUOTE = "https://cdn-api.cboe.com/api/global/delayed_quotes/quotes/_{}.json"
CHART_HISTORY = "https://cdn-api.cboe.com/api/global/delayed_quotes/charts/historical/_{}.json"


def supplement_closes(records, symbol, now, get, *, bounds=(0, math.inf)):
    """Only add newer, completed, original observations to a validated CSV."""
    last = date.fromisoformat(records[-1]["observation_date"])
    cutoff = completed_date(now)
    while cutoff.weekday() >= 5:
        cutoff -= timedelta(days=1)
    if last >= cutoff:
        return records, None

    url = CHART_HISTORY.format(symbol)
    additions = {}
    try:
        response = get(url, headers={"User-Agent": "MacroDashboard/1.0"}, timeout=(5, 15))
        response.raise_for_status()
        payload = response.json()
        if payload["symbol"] != f"_{symbol}" or not isinstance(payload["data"], list):
            raise ValueError("Unexpected Cboe chart history identity")
        published = datetime.fromisoformat(payload["timestamp"]).replace(tzinfo=timezone.utc)
        # This endpoint also serves a running daily bar. Its own publication
        # timestamp must be after the US session close for the date admitted.
        cutoff = min(cutoff, completed_date(min(now, published)))
        for row in payload["data"]:
            day = date.fromisoformat(row["date"])
            if last < day <= cutoff and day.weekday() < 5:
                close = float(row["close"])
                if not math.isfinite(close) or not bounds[0] <= close <= bounds[1]:
                    raise ValueError(f"Invalid {symbol} chart close for {day}")
                if day in additions and additions[day] != close:
                    raise ValueError(f"Conflicting {symbol} chart closes for {day}")
                additions[day] = close
    except (requests.RequestException, ValueError, KeyError, TypeError, OverflowError) as exc:
        print(f"Cboe {symbol} chart history unavailable: {type(exc).__name__}")
        additions.clear()
    if not additions and symbol in ("VIX", "SKEW"):
        url = QUOTE.format(symbol)
        try:
            response = get(url, headers={"User-Agent": "MacroDashboard/1.0"}, timeout=(5, 15))
            response.raise_for_status()
            payload = response.json()
            data = payload["data"]
            if payload["symbol"] != f"_{symbol}" or data["security_type"] != "index" or data["symbol"] != f"^{symbol}":
                raise ValueError("Unexpected Cboe closing quote identity")
            close = float(data["close"])
            if not math.isfinite(close) or close <= 0:
                raise ValueError("Invalid Cboe closing quote")
            if symbol == "VIX":
                row = confirmed_close(parse_cboe_quote(payload, now=now), now=now)
                if row and row["value"] == close:
                    day = date.fromisoformat(row["date"])
                    if last < day <= completed_date(now):
                        additions[day] = close
            else:
                et = ZoneInfo("America/New_York")
                observed = datetime.fromisoformat(data["last_trade_time"]).replace(tzinfo=et)
                # The end-of-day SKEW publication is after the regular session.
                day = observed.date()
                if (last < day and day.weekday() < 5 and time(17) <= observed.time()
                        and observed <= now and close == float(data["current_price"])):
                    additions[day] = close
        except (requests.RequestException, ValueError, KeyError, TypeError, OverflowError) as exc:
            print(f"Cboe {symbol} closing quote unavailable: {type(exc).__name__}")
    if not additions:
        return records, None
    return records + [{"observation_date": day.isoformat(), "close": additions[day]}
                      for day in sorted(additions)], url
