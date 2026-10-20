"""Refresh verified Cboe COR1M/COR3M closes; never replace newer history."""
from __future__ import annotations

import io
import json
import math
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
SYMBOLS = ("COR1M", "COR3M")
SOURCE_TEMPLATE = "https://cdn.cboe.com/api/global/us_indices/daily_prices/{}_History.csv"


def parse_history(text: str, symbol: str, now: datetime) -> list[dict]:
    if symbol not in SYMBOLS:
        raise ValueError(f"Unsupported correlation index: {symbol}")
    frame = pd.read_csv(io.StringIO(text))
    frame.columns = [str(column).strip().upper() for column in frame.columns]
    if not {"DATE", "CLOSE"}.issubset(frame.columns):
        raise ValueError(f"Unexpected {symbol} CSV columns: {list(frame.columns)}")
    dates = pd.to_datetime(frame["DATE"], format="%m/%d/%Y", errors="coerce")
    values = pd.to_numeric(frame["CLOSE"], errors="coerce")
    valid = dates.notna() & values.map(math.isfinite) & values.between(-100, 100)
    if not valid.all():
        raise ValueError(f"Invalid {symbol} dates or correlation points")
    local_now = now.astimezone(ZoneInfo("America/New_York"))
    cutoff = (local_now.date() if local_now.time() >= time(16, 15)
              else local_now.date() - timedelta(days=1))
    out = pd.DataFrame({"observation_date": dates, "close": values})
    out = (out.loc[dates.le(pd.Timestamp(cutoff))].sort_values("observation_date")
           .drop_duplicates("observation_date", keep="last"))
    if len(out) < 200:
        raise ValueError(f"{symbol} history unexpectedly short: {len(out)} rows")
    return [{"observation_date": row.observation_date.strftime("%Y-%m-%d"),
             "close": float(row.close)} for row in out.itertuples(index=False)]


def prepare_snapshot(text: str, symbol: str, previous: dict, now: datetime) -> dict | None:
    records = parse_history(text, symbol, now)
    old_records = previous.get("records") or []
    if (records[-1]["observation_date"] < str(previous.get("coverage_end") or "")
            or len(records) < len(old_records)):
        raise ValueError(f"{symbol} source would roll back or truncate saved history")
    if records == old_records:
        return None  # Keep the original fetch timestamp when nothing changed.
    return {
        "symbol": symbol,
        "name": f"Cboe {1 if symbol == 'COR1M' else 3}-Month Implied Correlation Index",
        "source": "Cboe Global Indices",
        "source_url": SOURCE_TEMPLATE.format(symbol),
        "unit": "index points",
        "updated_at": now.astimezone(timezone.utc).isoformat(),
        "record_count": len(records),
        "coverage_start": records[0]["observation_date"],
        "coverage_end": records[-1]["observation_date"],
        "records": records,
    }


def main() -> None:
    now = datetime.now(timezone.utc)
    pending = []
    for symbol in SYMBOLS:
        path = ROOT / "data_snapshots" / f"{symbol.lower()}_daily.json"
        previous = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        response = requests.get(SOURCE_TEMPLATE.format(symbol),
                                headers={"User-Agent": "MacroDashboard/1.0"}, timeout=30)
        response.raise_for_status()
        payload = prepare_snapshot(response.text, symbol, previous, now)
        if payload is not None:
            pending.append((path, payload))
        else:
            print(symbol, "source unchanged; retaining original observation timestamp")
    # Validate both exports before touching either last-good snapshot.
    for path, payload in pending:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
        print(payload["symbol"], payload["record_count"], payload["coverage_start"], "->", payload["coverage_end"])


if __name__ == "__main__":
    main()
