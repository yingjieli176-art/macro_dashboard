from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "data_snapshots" / "vixeq_daily.json"
SOURCE_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIXEQ_History.csv"


def main() -> None:
    response = requests.get(
        SOURCE_URL,
        headers={"User-Agent": "MacroDashboard/1.0"},
        timeout=30,
    )
    response.raise_for_status()
    frame = pd.read_csv(io.StringIO(response.text))
    columns = {str(col).strip().upper(): col for col in frame.columns}
    value_key = "VIXEQ" if "VIXEQ" in columns else ("CLOSE" if "CLOSE" in columns else None)
    if "DATE" not in columns or value_key is None:
        raise RuntimeError(f"Unexpected VIXEQ CSV columns: {list(frame.columns)}")

    out = frame[[columns["DATE"], columns[value_key]]].copy()
    out.columns = ["observation_date", "close"]
    out["observation_date"] = pd.to_datetime(out["observation_date"], errors="coerce")
    out["close"] = pd.to_numeric(out["close"], errors="coerce")
    out = (
        out.dropna(subset=["observation_date", "close"])
        .sort_values("observation_date")
        .drop_duplicates("observation_date", keep="last")
    )
    if len(out) < 200:
        raise RuntimeError(f"VIXEQ history unexpectedly short: {len(out)} rows")

    records = [
        {"observation_date": row.observation_date.strftime("%Y-%m-%d"), "close": float(row.close)}
        for row in out.itertuples(index=False)
    ]
    payload = {
        "symbol": "VIXEQ",
        "name": "Cboe S&P 500 Constituent Volatility Index",
        "source": "Cboe Global Indices",
        "source_url": SOURCE_URL,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(records),
        "coverage_start": records[0]["observation_date"],
        "coverage_end": records[-1]["observation_date"],
        "records": records,
    }
    SNAPSHOT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        "VIXEQ snapshot",
        payload["record_count"],
        payload["coverage_start"],
        "->",
        payload["coverage_end"],
    )


if __name__ == "__main__":
    main()
