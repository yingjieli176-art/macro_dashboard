"""Refresh *observed* FRED series for cold-start-safe Macro Dashboard charts.

Do not interpolate, extrapolate, or invent values. Keep existing last-good
snapshots when upstream endpoints are unreachable; bad fetches cannot erase data.
Compatible with data.py:_read_fred_success and _normalize_fred_frame.
"""
from __future__ import annotations

import concurrent.futures
from datetime import datetime, timezone
from io import StringIO
import json
import math
from pathlib import Path
import os
import re
import sys
import time

import pandas as pd
import requests

OUT = Path("data_snapshots/fred_cache")
FRED_GRAPH = "https://fred.stlouisfed.org/graph/fredgraph.csv"
FRED_API = "https://api.stlouisfed.org/fred/series/observations"

# Every US policy/yield/liquidity series used directly or by the app's data
# module. Snapshot failures are per-series; unknown source values stay absent.
SERIES = (
    "DGS3MO", "DGS2", "DGS10", "DFII5", "DFII10", "T10YIE",
    "SOFR", "IORB", "EFFR", "RRPONTSYAWARD", "WALCL",
    "WRESBAL", "WTREGEN", "RRPONTSYD", "VIXCLS", "VXVCLS",
    "SP500", "GVZCLS", "GFDEBTN", "FYGFDPUN",
    "FDHBFRBN", "FDHBFIN", "FDHBPIN",
)
CRITICAL = ("IORB", "RRPONTSYAWARD", "EFFR", "SOFR")
STOCK_LIMITS = {"IORB": (-10, 30), "RRPONTSYAWARD": (-10, 30),
                "EFFR": (-10, 30), "SOFR": (-10, 30)}
START = "2020-01-01"


def _parse_source(text: str, series_id: str) -> pd.DataFrame:
    raw = pd.read_csv(StringIO(text))
    if series_id not in raw.columns or len(raw.columns) < 2:
        raise ValueError(f"{series_id}: invalid FRED CSV columns: {list(raw.columns)}")
    frame = pd.DataFrame({
        "date": pd.to_datetime(raw.iloc[:, 0], errors="coerce"),
        "value": pd.to_numeric(raw[series_id], errors="coerce"),
    }).dropna()
    frame = frame[frame.date >= pd.Timestamp(START)]
    frame = frame.sort_values("date").drop_duplicates("date", keep="last")
    if len(frame) < 12:
        raise ValueError(f"{series_id}: too few observed rows: {len(frame)}")
    if frame.date.max() > pd.Timestamp.now(tz="UTC").tz_localize(None) + pd.Timedelta(days=1):
        raise ValueError(f"{series_id}: observed date in the future")
    if not all(math.isfinite(float(v)) for v in frame.value):
        raise ValueError(f"{series_id}: invalid/nonfinite source value")
    limits = STOCK_LIMITS.get(series_id)
    if limits is not None and not frame.value.between(*limits).all():
        raise ValueError(f"{series_id}: outside plausible rate bounds")
    return frame


def _fetch_csv(session, series_id: str) -> pd.DataFrame:
    response = session.get(FRED_GRAPH, params={"id": series_id},
                           headers={"User-Agent": "Mozilla/5.0 MacroDashboard/1.0"},
                           timeout=(4, 15))
    response.raise_for_status()
    return _parse_source(response.text, series_id)


def _fetch_api(session, series_id: str) -> pd.DataFrame:
    api_key = os.environ.get("FRED_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("FRED_API_KEY not configured")
    response = session.get(FRED_API, params={
        "series_id": series_id, "api_key": api_key, "file_type": "json",
        "observation_start": START,
    }, timeout=(4, 15))
    response.raise_for_status()
    data = response.json()
    observations = data.get("observations", [])
    text = "DATE," + series_id + "\n" + "\n".join(
        str(item.get("date", "")) + "," + str(item.get("value", "."))
        for item in observations
    )
    return _parse_source(text, series_id)


def _fetch_primary(session, series_id: str) -> pd.DataFrame:
    """Get the *same* directly published official rates if FRED is unreachable."""
    if series_id == "IORB":
        response = session.get(
            "https://www.federalreserve.gov/datadownload/Output.aspx",
            params={
                "rel": "PRATES", "series": "c27939ee810cb2e929a920a6bd77d9f6",
                "filetype": "csv", "label": "include", "layout": "seriescolumn",
                "type": "package",
            }, timeout=(4, 12),
        )
        response.raise_for_status()
        table = pd.read_csv(StringIO(response.text), header=5)
        if "Time Period" not in table.columns or "RESBM_N.D" not in table.columns:
            raise ValueError("Federal Reserve PRATES response has no IORB series")
        frame = pd.DataFrame({
            "date": pd.to_datetime(table["Time Period"], errors="coerce"),
            "value": pd.to_numeric(table["RESBM_N.D"], errors="coerce"),
        }).dropna()
        frame = frame.loc[frame["date"] >= pd.Timestamp(START)]
        if len(frame) < 12:
            raise ValueError("PRATES/IORB missing observed points")
        return _parse_source("DATE,IORB\n" + "\n".join(
            f"{date:%Y-%m-%d},{value}" for date, value
            in zip(frame["date"], frame["value"])
        ), series_id)

    if series_id in ("EFFR", "SOFR"):
        rate_type = "unsecured/effr" if series_id == "EFFR" else "secured/sofr"
        response = session.get(
            f"https://markets.newyorkfed.org/api/rates/{rate_type}/search.json",
            params={"startDate": START, "endDate": datetime.now(timezone.utc).strftime("%Y-%m-%d")},
            timeout=(4, 12),
        )
        response.raise_for_status()
        payload = response.json()
        records = payload.get("refRates", [])
        if not isinstance(records, list):
            raise ValueError("New York Fed reference rate response malformed")
        data = []
        for row in records:
            date, value = row.get("effectiveDate"), row.get("percentRate")
            if date and value not in (None, "", "N/A"):
                data.append({"date": date, "value": value})
        result = pd.DataFrame(data)
        if result.empty:
            raise ValueError("New York Fed returned no valid observed rates")
        return _parse_source("DATE," + series_id + "\n" + "\n".join(
            f"{row['date']},{row['value']}" for row in data
        ), series_id)
    raise ValueError("No official direct endpoint for " + series_id)


def refresh_one(series_id: str):
    failures = []
    with requests.Session() as session:
        fetchers = (_fetch_primary, _fetch_csv, _fetch_api)
        for fetcher in fetchers:
            try:
                frame = fetcher(session, series_id)
                primary_source = fetcher is _fetch_primary
                provenance = {
                    "IORB": ("Board of Governors of the Federal Reserve System",
                             "https://www.federalreserve.gov/datadownload/Choose.aspx?rel=PRATES"),
                    "EFFR": ("Federal Reserve Bank of New York",
                             "https://www.newyorkfed.org/markets/reference-rates/effr"),
                    "SOFR": ("Federal Reserve Bank of New York",
                             "https://www.newyorkfed.org/markets/reference-rates/sofr"),
                }
                source_name, source_url = (provenance[series_id]
                    if primary_source else
                    ("Federal Reserve Bank of St. Louis FRED",
                     "https://fred.stlouisfed.org/series/" + series_id))
                payload = {
                    "series_id": series_id,
                    "fetched_at": int(time.time()),
                    "source": source_name,
                    "source_series": source_url,
                    "coverage_end": frame.date.max().strftime("%Y-%m-%d"),
                    "records": [
                        {"date": date.strftime("%Y-%m-%d"), "value": float(value)}
                        for date, value in zip(frame.date, frame.value)
                    ],
                }
                return series_id, payload, ""
            except Exception as exc:
                failures.append(f"{fetcher.__name__}: {type(exc).__name__}: {exc}")
    return series_id, None, " | ".join(failures)


def save_snapshot(series_id, payload):
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / (series_id + ".json")
    # Skip pointless commit churn when data did not change; only actual
    # observation updates should alter the tracked copy.
    if target.exists():
        try:
            old = json.loads(target.read_text(encoding="utf-8"))
            if old.get("records") == payload["records"]:
                return False
        except (OSError, ValueError):
            pass
    target.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
                      encoding="utf-8")
    return True


def main():
    updated, retained, errors = [], [], []
    target_series = CRITICAL if "--core-only" in sys.argv else SERIES
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        results = pool.map(refresh_one, target_series)
        for sid, payload, error in results:
            if payload:
                changed = save_snapshot(sid, payload)
                (updated if changed else retained).append(sid)
                print(f"OK {sid}: {len(payload['records'])} real points, "
                      f"last {payload['coverage_end']} ({'updated' if changed else 'unchanged'})",
                      flush=True)
            else:
                errors.append(sid)
                print(f"WARN {sid}: {error}; preserved last-good snapshot", flush=True)

    missing_core = [s for s in CRITICAL if not (OUT / (s + ".json")).exists()]
    core_present = len(CRITICAL) - len(missing_core)
    # The chart is honest with partial observations; do NOT fail because the
    # ON RRP operation rate is unavailable from a primary endpoint.
    if core_present < 2:
        print(f"ERROR: less than two official Fed rate feeds available: {missing_core}")
        return 1
    if missing_core:
        print(f"WARN partial Fed chart: {core_present}/4 observed feeds; "
              f"missing series will remain absent: {missing_core}")
    print(f"Snapshot sync: updated={len(updated)}, unchanged={len(retained)}, failed={len(errors)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
