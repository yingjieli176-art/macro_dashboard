from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data_snapshots" / "hkma_banking_liquidity_daily.json"
INTERBANK_URL = "https://api.hkma.gov.hk/public/market-data-and-statistics/daily-monetary-statistics/daily-figures-interbank-liquidity"
MONETARY_BASE_URL = "https://api.hkma.gov.hk/public/market-data-and-statistics/daily-monetary-statistics/daily-figures-monetary-base"

INTERBANK_FIELDS = [
    "end_of_date",
    "opening_balance",
    "closing_balance",
    "forecast_aggregate_bal_t1",
]
BASE_FIELDS = [
    "end_of_date",
    "outstanding_efbn",
    "ow_lb_bf_disc_win",
]


def _request(url: str, params: dict[str, object]) -> list[dict]:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(
        f"{url}?{query}",
        headers={
            "User-Agent": "MacroDashboard/1.0 (+https://github.com/yingjieli176-art/macro_dashboard)",
            "Accept": "application/json",
        },
    )
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                payload = json.load(response)
            header = payload.get("header") or {}
            if header.get("success") is False:
                raise RuntimeError(header.get("err_msg") or "HKMA API returned failure")
            result = payload.get("result") or {}
            records = result.get("records") or []
            if not isinstance(records, list):
                raise RuntimeError("HKMA result.records is not a list")
            return records
        except Exception as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"HKMA request failed: {last_error}")


def _year_windows(years: int = 5) -> list[tuple[str, str]]:
    today = date.today()
    start_year = today.year - years
    windows: list[tuple[str, str]] = []
    for year in range(start_year, today.year + 1):
        start = date(year, 1, 1)
        end = date(year, 12, 31)
        if year == start_year:
            start = date(start_year, today.month, min(today.day, 28))
        if year == today.year:
            end = today
        if start <= end:
            windows.append((start.isoformat(), end.isoformat()))
    return windows


def _fetch_range(url: str, fields: list[str]) -> list[dict]:
    rows: list[dict] = []
    for start, end in _year_windows(5):
        params = {
            "choose": "end_of_date",
            "from": start,
            "to": end,
            "sortby": "end_of_date",
            "sortorder": "asc",
            "pagesize": 1000,
            "fields": ",".join(fields),
            "offset": 0,
        }
        rows.extend(_request(url, params))
    dedup: dict[str, dict] = {}
    for row in rows:
        day = str(row.get("end_of_date") or "")
        if len(day) == 10:
            dedup[day] = row
    return [dedup[key] for key in sorted(dedup)]


def main() -> None:
    interbank = _fetch_range(INTERBANK_URL, INTERBANK_FIELDS)
    monetary_base = _fetch_range(MONETARY_BASE_URL, BASE_FIELDS)

    by_date: dict[str, dict] = {}
    for row in interbank:
        day = str(row.get("end_of_date") or "")
        if day:
            by_date.setdefault(day, {"end_of_date": day}).update(row)
    for row in monetary_base:
        day = str(row.get("end_of_date") or "")
        if day:
            by_date.setdefault(day, {"end_of_date": day}).update(row)

    records = [by_date[key] for key in sorted(by_date)]
    if len(records) < 250:
        raise RuntimeError(f"HKMA daily banking snapshot too short: {len(records)} records")

    payload = {
        "source": "HKMA Daily Interbank Liquidity + Daily Monetary Base",
        "source_urls": [INTERBANK_URL, MONETARY_BASE_URL],
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(records),
        "records": records,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(records)} HKMA daily banking-liquidity records to {OUT}")


if __name__ == "__main__":
    main()
