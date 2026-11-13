"""Persist completed DXY index closes with the same admission rules as the audit."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from macro_platform.market_history import completed_daily_closes

SYMBOL = "DX-Y.NYB"
OUTPUT = ROOT / "data_snapshots/dxy_daily.json"


def parse_history(payload, now=None):
    nodes = (payload.get("chart") or {}).get("result") or []
    if len(nodes) != 1:
        raise ValueError("Missing unique DXY history")
    node = nodes[0]
    meta = node.get("meta") or {}
    if (meta.get("symbol") != SYMBOL or meta.get("instrumentType") != "INDEX"
            or meta.get("dataGranularity") != "1d"):
        raise ValueError("Unexpected DXY identity or frequency")
    frame = completed_daily_closes(node, now=now)
    if len(frame) < 1000:
        raise ValueError("Incomplete five-year DXY history")
    return frame


def save_snapshot(frame, path=OUTPUT):
    previous = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if previous and previous.get("symbol") != SYMBOL:
        raise ValueError("Unexpected saved DXY identity")
    records = [{"observation_date": row.observation_date.strftime("%Y-%m-%d"), "close": float(row.close)}
               for row in frame.itertuples()]
    if not records or any(not (0 < r["close"] < float("inf")) for r in records):
        raise ValueError("Missing or invalid DXY closes")
    days = [r["observation_date"] for r in records]
    if days != sorted(set(days)):
        raise ValueError("DXY dates must be unique and ordered")
    if pd.Timestamp(days[-1]) > pd.Timestamp.now(tz="UTC").tz_localize(None).normalize():
        raise ValueError("Future DXY observation")
    old = previous.get("records", [])
    required = {r["observation_date"] for r in old if r["observation_date"] >= days[0]}
    if not required.issubset(set(days)):
        raise ValueError("DXY response regressed or lost previously verified dates")
    records = [r for r in old if r["observation_date"] < days[0]] + records
    if records == old:
        return False
    payload = {"symbol": SYMBOL, "source_url": frame.attrs.get("source_url"),
               "frequency": "completed daily close", "unit": "index points",
               "fetched_at": datetime.now(timezone.utc).isoformat(), "records": records}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8")
    temporary.replace(path)
    return True


def main():
    best, errors = None, []
    now = pd.Timestamp.now(tz="UTC")
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        try:
            url = f"https://{host}/v8/finance/chart/{SYMBOL}"
            response = requests.get(url, params={"range": "5y", "interval": "1d", "includePrePost": "false"},
                                    headers={"User-Agent": "Mozilla/5.0 MacroDashboard/1.0"}, timeout=(5, 25))
            response.raise_for_status()
            frame = parse_history(response.json(), now)
            frame.attrs["source_url"] = response.url
            if best is None or frame.observation_date.max() > best.observation_date.max():
                best = frame
        except (requests.RequestException, ValueError, KeyError, TypeError) as error:
            errors.append(f"{host}: {type(error).__name__}: {error}")
    if best is None:
        raise RuntimeError("No verified DXY history; preserving last good snapshot: " + "; ".join(errors))
    changed = save_snapshot(best)
    print("DXY", len(best), "last", best.observation_date.max().date(), "changed", changed, flush=True)


if __name__ == "__main__":
    main()
