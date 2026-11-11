"""Refresh the risk chart independently of delayed/unavailable Cboe CSV exports."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from macro_platform.cboe_history import supplement_closes
from macro_platform.tail_risk import completed_date

SERIES = {
    "VIXEQ": "data_snapshots/vixeq_daily.json",
    "COR3M": "data_snapshots/cor3m_daily.json",
    "VIX": "data_snapshots/fred_cache/VIXCLS.json",
    "SPX": "data_snapshots/fred_cache/SP500.json",
}


def refresh_payload(previous, symbol, now, get=requests.get):
    """Retain validated history; append only dated, completed official closes."""
    fred = symbol in ("VIX", "SPX")
    expected = {"VIX": "VIXCLS", "SPX": "SP500"}.get(symbol)
    if (previous.get("series_id") != expected if fred else previous.get("symbol") != symbol):
        raise ValueError(f"Unexpected saved identity for {symbol}")
    records = ([{"observation_date": row["date"], "close": row["value"]}
                for row in previous["records"]] if fred else previous["records"])
    if not records:
        raise ValueError("A verified history is required")
    updated, source = records, None
    cutoff = completed_date(now)
    # A second attempt handles intermittent CDN errors, independently per series.
    for _ in range(2):
        updated, candidate = supplement_closes(updated, symbol, now, get,
                                               bounds=(-100, 100) if symbol == "COR3M" else (0, float("inf")))
        source = candidate or source
        if updated[-1]["observation_date"] >= cutoff.isoformat():
            break
    if updated == records:
        return None
    result = dict(previous)
    result.update(coverage_end=updated[-1]["observation_date"], latest_source_url=source)
    if fred:
        result.update(records=[{"date": r["observation_date"], "value": r["close"]} for r in updated],
                      source="Cboe completed index closes", source_series=source,
                      fetched_at=now.timestamp())
    else:
        result.update(records=updated, record_count=len(updated), updated_at=now.isoformat())
    return result


def main():
    now = datetime.now(timezone.utc)
    errors = []
    for symbol, relative in SERIES.items():
        path = ROOT / relative
        try:
            previous = json.loads(path.read_text())
            payload = refresh_payload(previous, symbol, now)
            if payload is not None:
                temporary = path.with_suffix(".json.tmp")
                temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=None if symbol in ("VIX", "SPX") else 2, separators=(",", ":") if symbol in ("VIX", "SPX") else None) + "\n")
                temporary.replace(path)
            saved = payload or previous
            print(symbol, "actual observation:", saved.get("coverage_end") or saved["records"][-1].get("date"),
                  "updated" if payload else "unchanged", flush=True)
        except Exception as exc:
            errors.append(f"{symbol}: {type(exc).__name__}: {exc}")
    if errors:
        raise RuntimeError("; ".join(errors))


if __name__ == "__main__":
    main()
