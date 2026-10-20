from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
import sys

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from macro_platform.market_history import completed_daily_closes

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data_snapshots" / "usdhkd_daily.json"
SYMBOL = "HKD=X"
HOSTS = (
    "https://query1.finance.yahoo.com/v8/finance/chart/",
    "https://query2.finance.yahoo.com/v8/finance/chart/",
)


def _fetch_yahoo() -> tuple[pd.DataFrame, str]:
    last_error = None
    for host in HOSTS:
        for attempt in range(3):
            try:
                url = host + quote(SYMBOL, safe="")
                response = requests.get(
                    url,
                    params={
                        "range": "5y",
                        "interval": "1d",
                        "includeAdjustedClose": "true",
                        "events": "div,splits",
                    },
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=12,
                )
                response.raise_for_status()
                result = (((response.json() or {}).get("chart") or {}).get("result") or [])
                if not result:
                    raise RuntimeError("Yahoo chart result missing")
                node = result[0] or {}
                timestamps = node.get("timestamp") or []
                frame = completed_daily_closes(node).rename(columns={"close": "value"})
                frame = frame.sort_values("observation_date").drop_duplicates(
                    "observation_date", keep="last"
                )
                if len(frame) < 1000:
                    raise RuntimeError(f"Yahoo USDHKD history too short: {len(frame)}")
                return frame, url
            except Exception as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(1 + attempt)
    raise RuntimeError(f"Yahoo HKD=X fetch failed: {last_error}")


def main() -> None:
    frame, source_url = _fetch_yahoo()
    if OUT.exists():
        previous = json.loads(OUT.read_text(encoding="utf-8"))
        old = pd.DataFrame(previous.get("records") or [])
        if not old.empty:
            old["observation_date"] = pd.to_datetime(old["observation_date"], errors="coerce")
            if frame.observation_date.max() < old.observation_date.max():
                raise RuntimeError("USDHKD source would roll back the saved latest close")
            frame = pd.concat([old, frame], ignore_index=True).dropna()
            frame = frame.drop_duplicates("observation_date", keep="last").sort_values("observation_date")
    records = [
        {
            "observation_date": row.observation_date.strftime("%Y-%m-%d"),
            "value": float(row.value),
        }
        for row in frame.itertuples(index=False)
    ]
    payload = {
        "symbol": SYMBOL,
        "name": "USD/HKD spot exchange rate",
        "source": "Yahoo Finance market history",
        "source_url": source_url,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(records),
        "coverage_start": records[0]["observation_date"],
        "coverage_end": records[-1]["observation_date"],
        "records": records,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("wrote", len(records), "HKD=X rows", records[0], records[-1])


if __name__ == "__main__":
    main()
