"""Persist completed US market bars so a live API outage cannot blank charts."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from urllib.parse import quote
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from macro_platform.market_history import completed_daily_closes

SYMBOLS = {"^NDX": "nasdaq100_daily.json", "GC=F": "gold_daily.json", "SI=F": "silver_daily.json"}


def refresh(symbol, filename):
    path = ROOT / "data_snapshots" / filename
    old = json.loads(path.read_text()) if path.exists() else {}
    best = None
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        try:
            response = requests.get(f"https://{host}/v8/finance/chart/{quote(symbol, safe='')}",
                params={"range": "5y", "interval": "1d", "includePrePost": "false"},
                headers={"User-Agent": "Mozilla/5.0 MacroDashboard/1.0"}, timeout=(5, 25))
            response.raise_for_status()
            node = response.json()["chart"]["result"][0]
            if node["meta"]["symbol"] != symbol or node["meta"]["dataGranularity"] != "1d":
                raise ValueError("Unexpected daily market identity")
            frame = completed_daily_closes(node)
            if len(frame) < 900:
                raise ValueError("Insufficient five-year daily bars")
            if best is None or frame.observation_date.max() > best.observation_date.max():
                best = frame
        except (requests.RequestException, ValueError, KeyError, TypeError):
            continue
    if best is None:
        raise RuntimeError(symbol + ": both market transports unavailable")
    rows = {row["observation_date"]: row for row in old.get("records", [])}
    rows.update({r.observation_date.strftime("%Y-%m-%d"): {"observation_date": r.observation_date.strftime("%Y-%m-%d"),
                  "close": float(r.close)} for r in best.itertuples()})
    records = [rows[d] for d in sorted(rows)]
    if records != old.get("records"):
        payload = dict(symbol=symbol, records=records, coverage_end=records[-1]["observation_date"],
                       source_url=f"https://finance.yahoo.com/quote/{quote(symbol, safe='')}/history/",
                       updated_at=datetime.now(timezone.utc).isoformat())
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, separators=(",", ":")) + "\n")
        temporary.replace(path)
    print(symbol, records[-1]["observation_date"], flush=True)


def main():
    errors = []
    for symbol, filename in SYMBOLS.items():
        try:
            refresh(symbol, filename)
        except Exception as exc:
            errors.append(symbol + ": " + type(exc).__name__)
    if errors:
        raise RuntimeError("; ".join(errors))


if __name__ == "__main__":
    main()
