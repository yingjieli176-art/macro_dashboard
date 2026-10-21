"""Refresh completed USD/JPY closes and verify the timely yen index snapshot."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from macro_platform.yen_index import MARKET_FORMULA, MARKET_SNAPSHOT, MARKET_SOURCE_URL, parse_yahoo_yen


def save_market_snapshot(frame, path=MARKET_SNAPSHOT, now=None):
    clock = pd.Timestamp.now(tz="UTC").tz_localize(None) if now is None else pd.Timestamp(now)
    if clock.tzinfo is not None:
        clock = clock.tz_convert("UTC").tz_localize(None)
    if len(frame) < 1000 or frame.observation_date.min() > clock - pd.DateOffset(years=4, months=10):
        raise ValueError("Incomplete five-year USD/JPY history")
    latest = frame.observation_date.max()
    if latest >= clock.normalize() or latest + pd.offsets.BDay(2) < clock.normalize():
        raise ValueError("USD/JPY response is future-dated or overdue")
    records = [{"date": day.strftime("%Y-%m-%d"), "usd_jpy_close": float(value)}
               for day, value in zip(frame.observation_date, frame.usd_jpy_close)]
    if path.exists():
        previous = json.loads(path.read_text())
        old = previous["records"]
        if latest < pd.Timestamp(max(row["date"] for row in old)):
            raise ValueError("USD/JPY response regressed")
        retained = {row["date"] for row in old if row["date"] >= records[0]["date"]}
        if not retained.issubset({row["date"] for row in records}):
            raise ValueError("USD/JPY response lost existing dates")
        if records == old:
            return False
    payload = {"symbol": "JPY=X", "source": MARKET_SOURCE_URL, "formula": MARKET_FORMULA,
               "frequency": "completed daily close", "fetched_at": datetime.now(timezone.utc).isoformat(),
               "records": records}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n")
    temporary.replace(path)
    return True


def main():
    last_error = None
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        try:
            response = requests.get(f"https://{host}/v8/finance/chart/JPY%3DX",
                params={"range": "5y", "interval": "1d", "includePrePost": "false"},
                headers={"User-Agent": "Mozilla/5.0 (compatible; MacroDashboard/1.0)"}, timeout=(5, 20))
            response.raise_for_status()
            frame = parse_yahoo_yen(response.json())
            changed = save_market_snapshot(frame)
            print(f"JPY/USD Index: {len(frame)} completed closes, latest {frame.observation_date.max().date()}, changed={changed}")
            return
        except (requests.RequestException, ValueError, KeyError, TypeError) as error:
            last_error = error
    raise RuntimeError("No valid current USD/JPY source; retaining last good snapshot") from last_error


if __name__ == "__main__":
    main()
