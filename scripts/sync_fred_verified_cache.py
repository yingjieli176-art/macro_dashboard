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
from pathlib import Path
import os
import sys
import time

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from macro_platform.fred_observations import validate_observations

OUT = Path("data_snapshots/fred_cache")
FRED_GRAPH = "https://fred.stlouisfed.org/graph/fredgraph.csv"
FRED_API = "https://api.stlouisfed.org/fred/series/observations"
# This is an offline snapshot job, not the interactive UI request budget.
# Official CSV transport can take more than four seconds to establish a
# connection (including a proxy tunnel). Keep both phases bounded while
# allowing verified downloads to finish; never substitute estimated values.
FETCH_TIMEOUT = (12, 30)

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
    return validate_observations(frame, series_id, date_column="date",
                                 value_column="value", min_rows=12)


def _fetch_csv(session, series_id: str) -> pd.DataFrame:
    response = session.get(FRED_GRAPH, params={"id": series_id},
                           headers={"User-Agent": "Mozilla/5.0 MacroDashboard/1.0"},
                           timeout=FETCH_TIMEOUT)
    response.raise_for_status()
    return _parse_source(response.text, series_id)


def _fetch_api(session, series_id: str) -> pd.DataFrame:
    api_key = os.environ.get("FRED_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("FRED_API_KEY not configured")
    response = session.get(FRED_API, params={
        "series_id": series_id, "api_key": api_key, "file_type": "json",
        "observation_start": START,
    }, timeout=FETCH_TIMEOUT)
    response.raise_for_status()
    data = response.json()
    observations = data.get("observations", [])
    text = "DATE," + series_id + "\n" + "\n".join(
        str(item.get("date", "")) + "," + str(item.get("value", "."))
        for item in observations
    )
    return _parse_source(text, series_id)


TREASURY_FIELDS = {"DGS3MO": "BC_3MONTH", "DGS2": "BC_2YEAR", "DGS10": "BC_10YEAR",
                   "DFII5": "TC_5YEAR", "DFII10": "TC_10YEAR"}
CBOE_FILES = {"VIXCLS": "VIX_History.csv", "VXVCLS": "VIX3M_History.csv", "GVZCLS": "GVZ_History.csv"}


def _fetch_treasury(session, series_id):
    """Use the original same-definition Treasury close before the FRED mirror."""
    import xml.etree.ElementTree as ET
    field = TREASURY_FIELDS[series_id]
    kind = "daily_treasury_real_yield_curve" if series_id.startswith("DFII") else "daily_treasury_yield_curve"
    response = session.get(
        "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml",
        params={"data": kind, "field_tdr_date_value": datetime.now(timezone.utc).year},
        timeout=FETCH_TIMEOUT,
    )
    response.raise_for_status()
    root = ET.fromstring(response.text)
    observed = []
    for props in root.iter():
        if props.tag.rsplit("}", 1)[-1] != "properties":
            continue
        row = {child.tag.rsplit("}", 1)[-1]: child.text for child in props}
        if row.get("NEW_DATE") and row.get(field) not in (None, ""):
            observed.append({"date": row["NEW_DATE"].split("T")[0], "value": row[field]})
    if not observed:
        raise ValueError("Treasury XML has no dated " + field + " values")
    # Download only this year's original observations; preserve the same-series
    # verified history instead of downloading seven years every few hours.
    previous = []
    target = OUT / (series_id + ".json")
    if target.exists():
        previous = json.loads(target.read_text()).get("records") or []
    frame = pd.DataFrame(previous + observed).drop_duplicates("date", keep="last")
    text = "DATE," + series_id + "\n" + "\n".join(
        f"{row.date},{row.value}" for row in frame.itertuples(index=False)
    )
    return _parse_source(text, series_id)


def _h41_current_frame(text, series_id):
    import re
    for table in pd.read_html(StringIO(text)):
        columns = [" | ".join(map(str, col if isinstance(col, tuple) else (col,))) for col in table.columns]
        labels = table.iloc[:, 0].astype(str).str.strip()
        if series_id == "WALCL":
            if not any("Eliminations from consolidation" in col for col in columns):
                continue
            rows = table.loc[labels.eq("Total assets")]
            indices = [i for i, col in enumerate(columns) if col.startswith("Wednesday ")]
        else:
            rows = table.loc[labels.eq("Reserve balances with Federal Reserve Banks")]
            indices = [i for i, col in enumerate(columns)
                       if col.startswith("Averages of daily figures") and "Week ended" in col]
        if len(rows) != 1 or len(indices) != 1:
            continue
        index = indices[0]
        match = re.search(r"(?:Wednesday|Week ended)\s+([A-Z][a-z]{2} \d{1,2}, \d{4})", columns[index])
        if match is None:
            raise ValueError("H.4.1 observation date unavailable")
        frame = pd.DataFrame({"date": [pd.Timestamp(match.group(1))],
                              "value": [float(str(rows.iloc[0, index]).replace(",", ""))]})
        return validate_observations(frame, series_id, date_column="date", value_column="value")
    raise ValueError("H.4.1 same-definition observation unavailable for " + series_id)


def _fetch_h41_current(session, series_id):
    response = session.get("https://www.federalreserve.gov/releases/h41/current/h41.htm", timeout=FETCH_TIMEOUT)
    response.raise_for_status()
    return _h41_current_frame(response.text, series_id)


def _reverse_repo_frame(payload, series_id):
    records = []
    for row in payload.get("repo", {}).get("operations", []):
        if (row.get("operationType") != "Reverse Repo" or row.get("term") != "Overnight"
                or row.get("auctionStatus") != "Results"):
            continue
        details = row.get("details") or []
        if series_id == "RRPONTSYD":
            # FRED reports billions of dollars; NY Fed reports dollars.
            value = float(row["totalAmtAccepted"]) / 1_000_000_000
        else:
            rates = {float(d["percentAwardRate"]) for d in details if d.get("percentAwardRate") is not None}
            if not rates:
                continue
            if len(rates) != 1:
                raise ValueError("Ambiguous overnight reverse repo award rate")
            value = rates.pop()
        records.append({"date": row["operationDate"], "value": value})
    if not records:
        raise ValueError("No completed overnight reverse repo results")
    frame = pd.DataFrame(records)
    if series_id == "RRPONTSYD":
        frame = frame.groupby("date", as_index=False)["value"].sum()
    elif frame.groupby("date")["value"].nunique().gt(1).any():
        raise ValueError("Conflicting award rates for one operation date")
    return _parse_source("DATE," + series_id + "\n" + "\n".join(
        f"{row.date},{row.value}" for row in frame.itertuples(index=False)), series_id)


def _fetch_reverse_repo(session, series_id):
    response = session.get("https://markets.newyorkfed.org/api/rp/results/search.json",
                           params={"startDate": START, "endDate": datetime.now(timezone.utc).strftime("%Y-%m-%d")},
                           timeout=FETCH_TIMEOUT)
    response.raise_for_status()
    return _reverse_repo_frame(response.json(), series_id)


def _merge_verified_history(series_id, frame):
    target = OUT / (series_id + ".json")
    if target.exists():
        previous = pd.DataFrame(json.loads(target.read_text()).get("records") or [])
        if not previous.empty:
            previous["date"] = pd.to_datetime(previous["date"])
            frame = pd.concat([previous, frame]).drop_duplicates("date", keep="last").sort_values("date")
    return validate_observations(frame, series_id, date_column="date", value_column="value", min_rows=12)


def _fetch_primary(session, series_id: str) -> pd.DataFrame:
    """Get the *same* directly published official rates if FRED is unreachable."""
    if series_id in ("WALCL", "WRESBAL"):
        return _merge_verified_history(series_id, _fetch_h41_current(session, series_id))
    if series_id in ("RRPONTSYAWARD", "RRPONTSYD"):
        return _merge_verified_history(series_id, _fetch_reverse_repo(session, series_id))
    if series_id == "SP500":
        from macro_platform.market_history import completed_daily_closes
        response = session.get("https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC",
                               params={"range": "1y", "interval": "1d"},
                               headers={"User-Agent": "Mozilla/5.0 MacroDashboard/1.0"}, timeout=FETCH_TIMEOUT)
        response.raise_for_status()
        node = response.json()["chart"]["result"][0]
        frame = completed_daily_closes(node).rename(columns={"observation_date": "date", "close": "value"})
        if frame.empty:
            raise ValueError("No completed S&P 500 daily closes")
        return _merge_verified_history(series_id, frame)
    if series_id in TREASURY_FIELDS:
        return _fetch_treasury(session, series_id)
    if series_id in CBOE_FILES:
        response = session.get(
            "https://cdn.cboe.com/api/global/us_indices/daily_prices/" + CBOE_FILES[series_id],
            timeout=FETCH_TIMEOUT,
        )
        response.raise_for_status()
        rows = pd.read_csv(StringIO(response.text))
        value_column = "CLOSE" if "CLOSE" in rows.columns else {
            "GVZCLS": "GVZ", "VXVCLS": "VIX3M", "VIXCLS": "VIX"
        }.get(series_id)
        if "DATE" not in rows.columns or value_column not in rows.columns:
            raise ValueError("Cboe daily close schema changed")
        text = "DATE," + series_id + "\n" + "\n".join(
            f"{day},{value}" for day, value in zip(rows["DATE"], rows[value_column])
        )
        return _parse_source(text, series_id)

    if series_id == "IORB":
        response = session.get(
            "https://www.federalreserve.gov/datadownload/Output.aspx",
            params={
                "rel": "PRATES", "series": "c27939ee810cb2e929a920a6bd77d9f6",
                "filetype": "csv", "label": "include", "layout": "seriescolumn",
                "type": "package",
            }, timeout=FETCH_TIMEOUT,
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
            timeout=FETCH_TIMEOUT,
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
                    "WALCL": ("Federal Reserve H.4.1 total assets, Wednesday level (USD millions)",
                              "https://www.federalreserve.gov/releases/h41/current/h41.htm"),
                    "WRESBAL": ("Federal Reserve H.4.1 reserve balances, weekly average (USD millions)",
                                "https://www.federalreserve.gov/releases/h41/current/h41.htm"),
                    "RRPONTSYAWARD": ("Federal Reserve Bank of New York overnight reverse repo results",
                                      "https://markets.newyorkfed.org/api/rp/results/search.json"),
                    "RRPONTSYD": ("Federal Reserve Bank of New York overnight reverse repo results (USD billions)",
                                  "https://markets.newyorkfed.org/api/rp/results/search.json"),
                    "SP500": ("S&P 500 unadjusted completed closes via Yahoo Finance",
                              "https://finance.yahoo.com/quote/%5EGSPC/history/"),
                    "IORB": ("Board of Governors of the Federal Reserve System",
                             "https://www.federalreserve.gov/datadownload/Choose.aspx?rel=PRATES"),
                    "EFFR": ("Federal Reserve Bank of New York",
                             "https://www.newyorkfed.org/markets/reference-rates/effr"),
                    "SOFR": ("Federal Reserve Bank of New York",
                             "https://www.newyorkfed.org/markets/reference-rates/sofr"),
                }
                for symbol in TREASURY_FIELDS:
                    provenance[symbol] = ("U.S. Treasury original constant-maturity yields",
                                          "https://home.treasury.gov/resource-center/data-chart-center/interest-rates")
                for symbol, filename in CBOE_FILES.items():
                    provenance[symbol] = ("Cboe original daily index close",
                                          "https://cdn.cboe.com/api/global/us_indices/daily_prices/" + filename)
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
                failures.append(f"{getattr(fetcher, '__name__', type(fetcher).__name__)}: {type(exc).__name__}: {exc}")
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
            if snapshot_health(series_id)["status"] != "missing_or_invalid":
                old_end = max(row["date"] for row in old["records"])
                new_end = max(row["date"] for row in payload["records"])
                if pd.Timestamp(new_end) < pd.Timestamp(old_end):
                    return False
        except (OSError, ValueError):
            pass
    target.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
                      encoding="utf-8")
    return True


def snapshot_health(series_id, now=None):
    """Validate each stored series independently of the sync job exit code."""
    now = pd.Timestamp.now(tz="UTC").tz_localize(None) if now is None else pd.Timestamp(now)
    try:
        payload = json.loads((OUT / (series_id + ".json")).read_text())
        if payload.get("series_id") != series_id:
            raise ValueError("series ID mismatch")
        records = payload["records"]
        if len(records) < 12:
            raise ValueError("too few observations")
        dates = pd.to_datetime([row["date"] for row in records], errors="raise")
        values = [float(row["value"]) for row in records]
        validate_observations(pd.DataFrame({"date": dates, "value": values}), series_id,
                              date_column="date", value_column="value", now=now, min_rows=12)
        end = dates.max().strftime("%Y-%m-%d")
        if end != payload.get("coverage_end"):
            raise ValueError("coverage end mismatch")
        # Debt series are monthly/quarterly; market/rate series are daily/weekly.
        tolerance = (550 if series_id == "FYGFDPUN" else
                     150 if series_id in ("GFDEBTN", "FDHBFRBN", "FDHBFIN", "FDHBPIN") else None)
        deadline = (dates.max().normalize() + pd.Timedelta(days=tolerance)
                    if tolerance is not None else
                    dates.max().normalize() + pd.Timedelta(days=10)
                    if series_id in ("WALCL", "WRESBAL", "WTREGEN") else
                    dates.max().normalize() + pd.offsets.BDay(2))
        status = "stale" if now.normalize() > deadline else "available"
        return {"series_id": series_id, "status": status, "coverage_end": end, "rows": len(records)}
    except (OSError, ValueError, TypeError, KeyError):
        return {"series_id": series_id, "status": "missing_or_invalid", "coverage_end": "", "rows": 0}


def write_health_report(series_ids, errors):
    reports = [snapshot_health(sid) for sid in series_ids]
    Path("fred_sync_health.json").write_text(json.dumps({"series": reports, "fetch_failures": errors}, indent=2) + "\n")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        available = sum(row["status"] == "available" for row in reports)
        lines = [f"## Source availability: {available}/{len(reports)} series", "",
                 "A successful job does not imply that every source is current.", "",
                 "| Series | Stored status | Last observed | Rows |", "| --- | --- | --- | --- |"]
        lines += [f"| {row['series_id']} | {row['status']} | {row['coverage_end']} | {row['rows']} |" for row in reports]
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write("\n".join(lines) + "\n")
    return reports


def main():
    updated, retained, errors = [], [], []
    target_series = CRITICAL if "--core-only" in sys.argv else SERIES
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        results = pool.map(refresh_one, target_series)
        for sid, payload, error in results:
            if payload:
                changed = save_snapshot(sid, payload)
                (updated if changed else retained).append(sid)
                stored = snapshot_health(sid)
                print(f"OK {sid}: {stored['rows']} real points, "
                      f"last {stored['coverage_end']} ({'updated' if changed else 'retained'}), source={payload['source']}",
                      flush=True)
            else:
                errors.append(sid)
                print(f"WARN {sid}: {error}; preserved last-good snapshot", flush=True)

    write_health_report(target_series, errors)
    missing_core = [s for s in CRITICAL if snapshot_health(s)["status"] != "available"]
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

