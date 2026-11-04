"""Refresh dated Cboe SPX/SPXW daily volume reports, retaining last-good rows."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from macro_platform.spx_options import PRODUCT, SOURCE_TEMPLATE, parse_daily

OUT = ROOT / "data_snapshots/spx_put_call_daily.json"


def fetch_daily(day, now=None):
    response = requests.get(SOURCE_TEMPLATE.format(day), headers={"User-Agent": "MacroDashboard/1.0"}, timeout=20)
    if response.status_code in (403, 404):
        return None  # No report on holidays or before publication; never write a zero.
    response.raise_for_status()
    return parse_daily(response.json(), day, now=now)


def refresh(previous, now, fetch=fetch_daily, backfill=False):
    start = (pd.Timestamp(now.date()) - pd.DateOffset(years=5)).strftime("%Y-%m-%d")
    existing = {r["observation_date"]: r for r in previous.get("records", []) if r["observation_date"] >= start}
    end = pd.Timestamp(now.astimezone(ZoneInfo("America/New_York")).date()) - pd.Timedelta(days=1)
    begin = pd.Timestamp(start) if backfill or len(existing) < 700 else end - pd.Timedelta(days=14)
    days = [d.strftime("%Y-%m-%d") for d in pd.bdate_range(begin, end)]
    downloaded, errors = [], []
    with ThreadPoolExecutor(max_workers=8) as pool:
        jobs = {pool.submit(fetch, day, now): day for day in days}
        for count, future in enumerate(as_completed(jobs), 1):
            try:
                row = future.result()
                if row is not None:
                    existing[row["observation_date"]] = row
                    downloaded.append(row)
            except Exception as exc:
                errors.append({"date": jobs[future], "error": type(exc).__name__ + ": " + str(exc)[:180]})
            if count % 100 == 0:
                print("SPX reports", count, "/", len(days), "valid", len(downloaded), "errors", len(errors), flush=True)
    if not downloaded:
        raise RuntimeError("No verified SPX reports downloaded; saved snapshot retained")
    records = [existing[k] for k in sorted(existing)]
    if len(records) < 700:
        raise RuntimeError(f"SPX history too short: {len(records)}; saved snapshot retained")
    if records == previous.get("records"):
        return None
    return dict(product=PRODUCT, ratio_basis="put_volume/call_volume", unit="ratio", source="Cboe Daily Market Statistics",
                source_url="https://www.cboe.com/markets/us/options/market-statistics/daily",
                source_template=SOURCE_TEMPLATE, updated_at=now.isoformat(), records=records,
                record_count=len(records), coverage_start=records[0]["observation_date"],
                coverage_end=records[-1]["observation_date"], fetch_errors=errors)


def main():
    previous = json.loads(OUT.read_text()) if OUT.exists() else {}
    payload = refresh(previous, datetime.now(timezone.utc), backfill="--backfill" in sys.argv)
    if payload is not None:
        tmp = OUT.with_suffix(".json.tmp")
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
        tmp.replace(OUT)
        print("SPX P/C", payload["record_count"], payload["coverage_end"], "errors", len(payload["fetch_errors"]))


if __name__ == "__main__":
    main()
