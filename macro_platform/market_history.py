"""Parse observed, completed daily bars without mixing adjusted prices."""
import math
import pandas as pd


def completed_daily_closes(node, now=None):
    timestamps = node.get("timestamp") or []
    values = (((node.get("indicators") or {}).get("quote") or [{}])[0]).get("close") or []
    if len(timestamps) != len(values):
        raise ValueError("Daily history timestamps/close length mismatch")
    if not timestamps:
        return pd.DataFrame(columns=["observation_date", "close"])
    meta = node.get("meta") or {}
    tz_name = meta.get("exchangeTimezoneName") or "UTC"
    clock = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    clock = clock.tz_localize("UTC") if clock.tzinfo is None else clock.tz_convert("UTC")
    dates = pd.to_datetime(timestamps, unit="s", utc=True, errors="coerce")
    try:
        local_dates = dates.tz_convert(tz_name).tz_localize(None).normalize()
        today = clock.tz_convert(tz_name).tz_localize(None).normalize()
    except (KeyError, ValueError):
        local_dates = dates.tz_localize(None).normalize()
        today = clock.tz_localize(None).normalize()
    completed = local_dates < today
    # A same-day equity/futures bar is usable only after the source's
    # explicit session end. Crypto daily bars complete at UTC midnight.
    regular = (meta.get("currentTradingPeriod") or {}).get("regular") or {}
    if str(meta.get("instrumentType", "")).upper() != "CRYPTOCURRENCY":
        try:
            start = pd.Timestamp(float(regular["start"]), unit="s", tz="UTC")
            end = pd.Timestamp(float(regular["end"]), unit="s", tz="UTC")
            if start < end <= clock and start.tz_convert(tz_name).tz_localize(None).normalize() == today:
                completed = completed | (local_dates == today)
        except (KeyError, TypeError, ValueError, OverflowError):
            pass
    frame = pd.DataFrame({"observation_date": local_dates, "close": pd.to_numeric(values, errors="coerce")})
    valid = frame["close"].map(lambda value: pd.notna(value) and math.isfinite(float(value)) and value > 0)
    frame = frame.loc[completed & valid].dropna(subset=["observation_date"])
    return frame.sort_values("observation_date").drop_duplicates("observation_date", keep="last").reset_index(drop=True)
