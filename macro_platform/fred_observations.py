"""Admission checks shared by live FRED refreshes and offline source jobs."""
import math

import pandas as pd


RATE_LIMITS = {sid: (-10, 30) for sid in ("IORB", "RRPONTSYAWARD", "EFFR", "SOFR")}


def validate_observations(frame, series_id, *, date_column="observation_date",
                          value_column=None, now=None, min_rows=1,
                          latest_known_date=None):
    """Reject invalid observations before publishing or replacing last-good data.

    Missing FRED observations (".") are removed by the source parser. This
    function only checks remaining observations and never fills their gaps.
    """
    value_column = series_id if value_column is None else value_column
    if frame is None or len(frame) < min_rows:
        raise ValueError(f"{series_id}: too few observed rows")
    dates = pd.to_datetime(frame[date_column], errors="raise", utc=True)
    if dates.isna().any() or not dates.is_unique or not dates.is_monotonic_increasing:
        raise ValueError(f"{series_id}: invalid observation dates")
    today = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    today = today.tz_localize("UTC") if today.tzinfo is None else today.tz_convert("UTC")
    if dates.max() > today.normalize():
        raise ValueError(f"{series_id}: observed date in the future")
    if latest_known_date is not None and dates.max() < pd.to_datetime(latest_known_date, utc=True):
        raise ValueError(f"{series_id}: older than latest stored observation")
    values = [float(value) for value in frame[value_column]]
    if not all(math.isfinite(value) for value in values):
        raise ValueError(f"{series_id}: invalid/nonfinite source value")
    limits = RATE_LIMITS.get(series_id)
    if limits is not None and not all(limits[0] <= value <= limits[1] for value in values):
        raise ValueError(f"{series_id}: outside plausible rate bounds")
    return frame
