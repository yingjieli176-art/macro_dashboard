"""Persist original Ministry of Finance JGB observations for cold starts.

The current-release fetch is also the recovery path when the source audit sees
an observation newer than the committed snapshot.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from macro_platform.asia_rates import (JAPAN_SNAPSHOT, JAPAN_CURRENT_URL, JAPAN_HISTORY_URL,
                                      _read_japan_csv, _read_japan_snapshot, _merge_japan_yields)


def main():
    previous = _read_japan_snapshot()
    current = _read_japan_csv(JAPAN_CURRENT_URL, offline=True)
    fields = ("japan_2y", "japan_10y", "japan_30y")
    current = current.dropna(subset=list(fields), how="all")
    if current.empty:
        raise ValueError("Current MOF release has no observations")
    frames = [previous] if not previous.empty else []
    cutoff = pd.Timestamp.now(tz="Asia/Tokyo").tz_localize(None).normalize() - pd.DateOffset(years=5, days=14)
    thirty_dates = previous.loc[previous.japan_30y.notna(), "observation_date"]
    if previous.empty or thirty_dates.empty or thirty_dates.min() > cutoff + pd.Timedelta(days=7):
        frames.append(_read_japan_csv(JAPAN_HISTORY_URL, offline=True))
    frames.append(current)
    frame = _merge_japan_yields(frames)
    frame = frame.loc[frame.observation_date.ge(cutoff)]
    if len(frame) < 1100:
        raise ValueError("MOF history unexpectedly short")
    for field in fields:
        values = pd.to_numeric(frame[field], errors="coerce").dropna()
        if len(values) < 1100 or not values.between(-10,30).all():
            raise ValueError("Invalid MOF yield values")
        if frame.loc[frame[field].notna(), "observation_date"].max() < previous.loc[previous[field].notna(), "observation_date"].max():
            raise ValueError(f"MOF {field} observation regressed")
    if frame.observation_date.max() > pd.Timestamp.now(tz="Asia/Tokyo").tz_localize(None).normalize():
        raise ValueError("MOF observation date is in the future")
    if not previous.empty and current.observation_date.max() < previous.observation_date.max():
        raise ValueError("MOF current export is older than the saved observation")
    records = [{"observation_date": row.observation_date.strftime("%Y-%m-%d"),
                "japan_2y": None if pd.isna(row.japan_2y) else float(row.japan_2y),
                "japan_10y": None if pd.isna(row.japan_10y) else float(row.japan_10y),
                "japan_30y": None if pd.isna(row.japan_30y) else float(row.japan_30y)}
               for row in frame.itertuples(index=False)]
    payload = {"source": "Japan Ministry of Finance original JGB constant-maturity yields", "unit": "%",
               "source_urls": [JAPAN_HISTORY_URL, JAPAN_CURRENT_URL],
               "updated_at": datetime.now(timezone.utc).isoformat(),
               "coverage_end": records[-1]["observation_date"], "records": records}
    JAPAN_SNAPSHOT.write_text(json.dumps(payload,ensure_ascii=False,separators=(",",":"))+"\n")
    print("MOF JGB",len(records),records[-1])


if __name__ == "__main__":
    main()
