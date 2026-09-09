from __future__ import annotations

import io
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data_snapshots" / "usdhkd_daily.json"
URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
SERIES = "DEXHKUS"


def fetch() -> pd.DataFrame:
    last_error = None
    for attempt in range(4):
        try:
            response = requests.get(
                URL,
                params={"id": SERIES},
                headers={"User-Agent": "MacroDashboard/1.0"},
                timeout=35,
            )
            response.raise_for_status()
            frame = pd.read_csv(io.StringIO(response.text))
            if frame.empty or SERIES not in frame.columns:
                raise RuntimeError("FRED DEXHKUS payload missing series")
            date_col = frame.columns[0]
            frame["observation_date"] = pd.to_datetime(frame[date_col], errors="coerce")
            frame["value"] = pd.to_numeric(frame[SERIES], errors="coerce")
            frame = frame.dropna(subset=["observation_date", "value"]).sort_values("observation_date")
            cutoff = frame["observation_date"].max() - pd.DateOffset(years=5, months=2)
            frame = frame.loc[frame["observation_date"] >= cutoff, ["observation_date", "value"]]
            if len(frame) < 1000:
                raise RuntimeError(f"FRED history too short: {len(frame)}")
            return frame
        except Exception as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"FRED DEXHKUS fetch failed: {last_error}")


def main() -> None:
    frame = fetch()
    records = [
        {"observation_date": row.observation_date.strftime("%Y-%m-%d"), "value": float(row.value)}
        for row in frame.itertuples(index=False)
    ]
    payload = {
        "series": SERIES,
        "name": "Hong Kong Dollars to U.S. Dollar Exchange Rate",
        "source": "Federal Reserve Economic Data (FRED)",
        "source_url": URL,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(records),
        "coverage_start": records[0]["observation_date"],
        "coverage_end": records[-1]["observation_date"],
        "records": records,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("wrote", len(records), "DEXHKUS rows", records[0], records[-1])


if __name__ == "__main__":
    main()
