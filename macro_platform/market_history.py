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
    instrument = str(meta.get("instrumentType", "")).upper()
    tz_name = "UTC" if instrument == "CRYPTOCURRENCY" else meta.get("exchangeTimezoneName") or "UTC"
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
    if instrument != "CRYPTOCURRENCY":
        try:
            start = pd.Timestamp(float(regular["start"]), unit="s", tz="UTC")
            end = pd.Timestamp(float(regular["end"]), unit="s", tz="UTC")
            if start < end <= clock and start.tz_convert(tz_name).tz_localize(None).normalize() == today:
                completed = completed | (local_dates == today)
        except (KeyError, TypeError, ValueError, OverflowError):
            pass
        # The provider can advance currentTradingPeriod to tomorrow during
        # today's post-market session. That must not discard today's close.
        # Prefer explicit historical windows, including shortened sessions.
        def sessions(value):
            if isinstance(value, dict):
                if "start" in value and "end" in value:
                    yield value
                elif "regular" in value:
                    yield from sessions(value["regular"])
            elif isinstance(value, list):
                for item in value:
                    yield from sessions(item)
        for period in sessions(node.get("tradingPeriods") or meta.get("tradingPeriods") or []):
            try:
                start = pd.Timestamp(float(period["start"]), unit="s", tz="UTC")
                end = pd.Timestamp(float(period["end"]), unit="s", tz="UTC")
                day = start.tz_convert(tz_name).tz_localize(None).normalize()
                if start < end <= clock:
                    completed = completed | (local_dates == day)
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
        # Conservative fallback only for a rolled-forward regular session on
        # known cash exchanges, after their full-day close plus 15 minutes.
        # Unknown venues and futures still require explicit session evidence.
        close_times = {"America/New_York": (16, 15), "Asia/Hong_Kong": (16, 15),
                       "Asia/Tokyo": (15, 45)}
        # DXY continues publishing after the US cash-equity close.
        if (instrument in {"EQUITY", "ETF", "INDEX"} and tz_name in close_times
                and meta.get("symbol") != "DX-Y.NYB"):
            try:
                next_start = pd.Timestamp(float(regular["start"]), unit="s", tz="UTC")
                local_clock = clock.tz_convert(tz_name)
                next_day = next_start.tz_convert(tz_name).tz_localize(None).normalize()
                if (next_day > today and local_clock.weekday() < 5
                        and (local_clock.hour, local_clock.minute) >= close_times[tz_name]):
                    completed = completed | (local_dates == today)
            except (KeyError, TypeError, ValueError, OverflowError):
                pass
        # COMEX gold/silver/copper and NYMEX WTI finish their full daily
        # session at 16:00 Chicago time (CME product specifications).
        # Once the next overnight session starts, currentTradingPeriod no
        # longer describes the just-completed observation date.
        if instrument == "FUTURE" and meta.get("symbol") in {"GC=F", "SI=F", "HG=F", "CL=F"}:
            local_clock = clock.tz_convert("America/Chicago")
            if local_clock.weekday() < 5 and (local_clock.hour, local_clock.minute) >= (16, 15):
                completed = completed | (local_dates == today)
    frame = pd.DataFrame({"observation_date": local_dates, "close": pd.to_numeric(values, errors="coerce")})
    valid = frame["close"].map(lambda value: pd.notna(value) and math.isfinite(float(value)) and value > 0)
    frame = frame.loc[completed & valid].dropna(subset=["observation_date"])
    return frame.sort_values("observation_date").drop_duplicates("observation_date", keep="last").reset_index(drop=True)

