"""Persist actual U.S. Treasury TGA daily closing balances for Cloud cold starts.

Only source: official Treasury FiscalData Daily Treasury Statement (DTS).
The since-2022 Closing Balance row stores its named balance under
open_today_bal. Parse by account_type, not by naive column name.
Never forward-fill, interpolate, or invent a date or value.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import os
import sys
import time

import pandas as pd
import requests

from macro_platform.treasury_cash import parse_dts_tga_rows

ENDPOINT = ("https://api.fiscaldata.treasury.gov/services/api/fiscal_service/"
            "v1/accounting/dts/operating_cash_balance")
SNAPSHOT = Path("data_snapshots/treasury_tga_daily.json")
TGA_LABEL = "Treasury General Account (TGA) Closing Balance"
FIELDS = "record_date,account_type,close_today_bal,open_today_bal"


def fetch_latest_official(session):
    now = pd.Timestamp.now().normalize()
    # First request 5+ years of *named* TGA closing-balance rows, so
    # a single page contains actual daily observations across the period.
    # If Treasury rejects the label filter, use a short unfiltered sample.
    windows = [
        f"account_type:eq:{TGA_LABEL},record_date:gte:{(now - pd.DateOffset(years=5, months=1)):%Y-%m-%d}",
        f"record_date:gte:{(now - pd.DateOffset(months=4)):%Y-%m-%d}",
    ]
    problems = []
    for filter_value in windows:
        try:
            response = session.get(
                ENDPOINT,
                params={
                    "filter": filter_value,
                    "fields": FIELDS,
                    "sort": "-record_date",
                    "page[size]": 5000,
                    "format": "json",
                },
                headers={"User-Agent": "MacroDashboard/1.0"},
                timeout=(5, 24),
            )
            response.raise_for_status()
            raw = (response.json() or {}).get("data") or []
            parsed = parse_dts_tga_rows(raw)
            if len(parsed) < 20:
                raise ValueError(f"insufficient observed TGA closings: {len(parsed)}")
            latest = parsed["observation_date"].max()
            if latest < now - pd.Timedelta(days=12):
                raise ValueError(f"last official DTS TGA reading is stale: {latest.date()}")
            # Retain only the identified raw records. The parsed time series
            # is recomputed from these records on each app cache refresh.
            source_rows = [
                row for row in raw if (
                    "treasury general account" in
                    str(row.get("account_type") or "").lower() or
                    "total operating balance" in
                    str(row.get("account_type") or "").lower()
                )
            ]
            if not source_rows:
                raise ValueError("No original labeled Treasury rows to persist")
            source_rows.sort(key=lambda r: str(r.get("record_date") or ""))
            return source_rows, parsed
        except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
            problems.append(f"{type(exc).__name__}: {exc}")
    raise RuntimeError("Official FiscalData DTS unavailable: " + " | ".join(problems))


def main() -> int:
    session = requests.Session()
    rows, parsed = fetch_latest_official(session)
    new_end = parsed["observation_date"].max().strftime("%Y-%m-%d")
    old_records = []
    if SNAPSHOT.exists():
        try:
            old = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
            old_records = old.get("records") or []
            if new_end < str(old.get("coverage_end") or ""):
                raise RuntimeError("New official DTS download is older than saved observations")
            if old_records == rows:
                print("Official DTS TGA observations unchanged:", new_end)
                return 0
        except (ValueError, OSError, TypeError, json.JSONDecodeError):
            pass
    payload = {
        "source": "U.S. Treasury Daily Treasury Statement",
        "source_url": ENDPOINT,
        "series_id": "TGA_DAILY",
        "unit": "USD millions in source; dashboard USD trillions",
        "fetched_at": int(time.time()),
        "coverage_start": parsed["observation_date"].min().strftime("%Y-%m-%d"),
        "coverage_end": new_end,
        "observation_count": len(parsed),
        "records": rows,
    }
    if "--verify-only" not in sys.argv:
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
    print(f"Official Treasury DTS TGA verified: {len(parsed)} published daily "
          f"closings from {payload['coverage_start']} to {new_end}; "
          f"latest {parsed['TGA_DAILY'].iloc[-1]:.6f} USD trillion")
    return 0


if __name__ == "__main__":
    sys.exit(main())
