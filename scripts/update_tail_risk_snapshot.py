"""Publish five years of verified Cboe SKEW/VVIX closes atomically per file."""
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import sys

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from macro_platform.cboe_history import supplement_closes
from macro_platform.tail_risk import SYMBOLS, SOURCE_TEMPLATE, completed_date


def prepare_snapshot(text, symbol, previous, now, *, get=None):
    if symbol not in SYMBOLS:
        raise ValueError(f"Unsupported index: {symbol}")
    frame = pd.read_csv(io.StringIO(text))
    frame.columns = [str(c).strip().upper() for c in frame.columns]
    value_column = "CLOSE" if symbol == "VIX9D" else symbol
    if not {"DATE", value_column}.issubset(frame.columns):
        raise ValueError(f"Unexpected {symbol} CSV schema")
    dates = pd.to_datetime(frame.DATE, format="%m/%d/%Y", errors="coerce")
    values = pd.to_numeric(frame[value_column], errors="coerce")
    if dates.isna().any():
        raise ValueError(f"Invalid {symbol} observation date")
    cutoff = pd.Timestamp(completed_date(now))
    start = pd.Timestamp(now.date()) - pd.DateOffset(years=5)
    current = dates.between(start, cutoff)
    if not (values.loc[current].gt(0) & values.loc[current].lt(float("inf"))).all():
        raise ValueError(f"Invalid {symbol} daily close")
    fresh = pd.DataFrame({"observation_date": dates.loc[current], "close": values.loc[current]})
    fresh = fresh.sort_values("observation_date").drop_duplicates("observation_date", keep="last")
    if len(fresh) < 700:
        raise ValueError(f"{symbol} source history unexpectedly short: {len(fresh)}")
    latest_source = None
    if get is not None:
        records = [{"observation_date": r.observation_date.strftime("%Y-%m-%d"), "close": float(r.close)}
                   for r in fresh.itertuples(index=False)]
        records, latest_source = supplement_closes(records, symbol, now, get)
        if latest_source:
            fresh = pd.DataFrame(records)
            fresh["observation_date"] = pd.to_datetime(fresh.observation_date)
    old = pd.DataFrame(previous.get("records") or [], columns=["observation_date", "close"])
    old["observation_date"] = pd.to_datetime(old.observation_date, errors="coerce")
    old = old.loc[old.observation_date.between(start, cutoff)]
    if not old.empty and fresh.observation_date.max() < old.observation_date.max():
        raise ValueError(f"{symbol} source is older than saved observations")
    # A partial export cannot delete genuine saved observations inside the horizon.
    merged = pd.concat([old, fresh]).drop_duplicates("observation_date", keep="last").sort_values("observation_date")
    records = [{"observation_date": r.observation_date.strftime("%Y-%m-%d"), "close": float(r.close)}
               for r in merged.itertuples(index=False)]
    if records == previous.get("records"):
        return None
    payload = dict(symbol=symbol, source="Cboe Global Indices", source_url=SOURCE_TEMPLATE.format(symbol),
                unit="index points", updated_at=now.astimezone(timezone.utc).isoformat(),
                coverage_start=records[0]["observation_date"], coverage_end=records[-1]["observation_date"],
                record_count=len(records), records=records)
    if latest_source:
        payload["latest_source_url"] = latest_source
    return payload


def main():
    pending = []
    now = datetime.now(timezone.utc)
    for symbol in SYMBOLS:
        path = ROOT / "data_snapshots" / f"{symbol.lower()}_daily.json"
        previous = json.loads(path.read_text()) if path.exists() else {}
        response = requests.get(SOURCE_TEMPLATE.format(symbol), headers={"User-Agent": "MacroDashboard/1.0"}, timeout=30)
        response.raise_for_status()
        payload = prepare_snapshot(response.text, symbol, previous, now, get=requests.get)
        if payload is not None:
            pending.append((path, payload))
    # Validate both sources before replacing either last-good file.
    for path, payload in pending:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
        temporary.replace(path)
        print(payload["symbol"], payload["record_count"], payload["coverage_end"])


if __name__ == "__main__":
    main()
