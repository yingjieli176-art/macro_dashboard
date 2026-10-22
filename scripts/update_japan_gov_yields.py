"""Persist original Ministry of Finance JGB observations for cold starts."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from macro_platform.asia_rates import (JAPAN_SNAPSHOT, JAPAN_CURRENT_URL, JAPAN_HISTORY_URL,
                                      _read_japan_csv, _read_japan_snapshot)


def main():
    previous = _read_japan_snapshot()
    current = _read_japan_csv(JAPAN_CURRENT_URL, offline=True)
    current = current.dropna(subset=["japan_2y", "japan_10y"], how="all")
    if current.empty:
        raise ValueError("Current MOF release has no observations")
    frames = [previous] if not previous.empty else []
    if previous.empty:
        frames.append(_read_japan_csv(JAPAN_HISTORY_URL, offline=True))
    frames.append(current)
    frame = (pd.concat(frames).sort_values("observation_date", kind="stable")
             .drop_duplicates("observation_date", keep="last"))
    frame = frame.loc[frame.observation_date.ge(pd.Timestamp.now().normalize() - pd.DateOffset(years=5, days=14))]
    if len(frame) < 1100:
        raise ValueError("MOF history unexpectedly short")
    for field in ("japan_2y", "japan_10y"):
        values = pd.to_numeric(frame[field], errors="coerce").dropna()
        if values.empty or not values.between(-10,30).all():
            raise ValueError("Invalid MOF yield values")
    if frame.observation_date.max() > pd.Timestamp.now(tz="Asia/Tokyo").tz_localize(None).normalize():
        raise ValueError("MOF observation date is in the future")
    if not previous.empty and current.observation_date.max() < previous.observation_date.max():
        raise ValueError("MOF current export is older than the saved observation")
    records = [{"observation_date": row.observation_date.strftime("%Y-%m-%d"),
                "japan_2y": None if pd.isna(row.japan_2y) else float(row.japan_2y),
                "japan_10y": None if pd.isna(row.japan_10y) else float(row.japan_10y)}
               for row in frame.itertuples(index=False)]
    payload = {"source": "Japan Ministry of Finance original JGB constant-maturity yields", "unit": "%",
               "source_urls": [JAPAN_HISTORY_URL, JAPAN_CURRENT_URL],
               "updated_at": datetime.now(timezone.utc).isoformat(),
               "coverage_end": records[-1]["observation_date"], "records": records}
    JAPAN_SNAPSHOT.write_text(json.dumps(payload,ensure_ascii=False,separators=(",",":"))+"\n")
    print("MOF JGB",len(records),records[-1])


if __name__ == "__main__":
    main()
