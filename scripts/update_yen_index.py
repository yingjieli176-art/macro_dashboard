"""Fetch published BIS observations; never interpolate or change the index base."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from macro_platform.yen_index import API_URL, SERIES, SNAPSHOT, SOURCE_URL, parse_bis_yen_csv


def save_snapshot(frame, path=SNAPSHOT):
    if len(frame) < 1000:
        raise ValueError("Incomplete BIS five-year history")
    if path.exists():
        previous = json.loads(path.read_text())
        previous_dates = [row["date"] for row in previous["records"]]
        if frame.observation_date.max() < pd.Timestamp(max(previous_dates)):
            raise ValueError("BIS response regressed behind the existing observation date")
        cutoff = frame.observation_date.min().strftime("%Y-%m-%d")
        retained = {day for day in previous_dates if day >= cutoff}
        if not retained.issubset(set(frame.observation_date.dt.strftime("%Y-%m-%d"))):
            raise ValueError("BIS response lost existing observed dates")
        records = [{"date": d.strftime("%Y-%m-%d"), "value": float(v)}
                   for d, v in zip(frame.observation_date, frame.jpy_neer)]
        if records == previous["records"]:
            return False
    else:
        records = [{"date": d.strftime("%Y-%m-%d"), "value": float(v)}
                   for d, v in zip(frame.observation_date, frame.jpy_neer)]
    payload = {"series_id": SERIES, "source": SOURCE_URL, "api_url": API_URL,
               "unit": "Index, 2020=100", "frequency": "daily",
               "fetched_at": datetime.now(timezone.utc).isoformat(), "records": records}
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    temp.replace(path)
    return True


def main():
    start = (pd.Timestamp.now(tz="UTC") - pd.DateOffset(years=5, days=14)).strftime("%Y-%m-%d")
    response = requests.get(API_URL, params={"c[TIME_PERIOD]": "ge:" + start},
                            headers={"Accept": "application/vnd.sdmx.data+csv;version=1.0.0"}, timeout=(10, 45))
    response.raise_for_status()
    frame = parse_bis_yen_csv(response.text)
    changed = save_snapshot(frame)
    print(f"BIS {SERIES}: {len(frame)} observations, latest {frame.observation_date.max().date()}, changed={changed}")


if __name__ == "__main__":
    main()
