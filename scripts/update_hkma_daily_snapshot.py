from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data_snapshots" / "hkma_banking_liquidity_daily.json"
LIQ_URL = "https://api.hkma.gov.hk/public/market-data-and-statistics/daily-monetary-statistics/daily-figures-interbank-liquidity"
BASE_URL = "https://api.hkma.gov.hk/public/market-data-and-statistics/daily-monetary-statistics/daily-figures-monetary-base"
HIBOR_URL = "https://api.hkma.gov.hk/public/market-data-and-statistics/monthly-statistical-bulletin/er-ir/hk-interbank-ir-daily"


def _request(url: str, params: dict[str, str]) -> list[dict]:
    req = urllib.request.Request(
        f"{url}?{urllib.parse.urlencode(params)}",
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; MacroDashboard/1.0; +https://github.com/yingjieli176-art/macro_dashboard)",
            "Accept": "application/json",
        },
    )
    last_error = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                payload = json.load(response)
            header = payload.get("header") or {}
            if header.get("success") is False:
                raise RuntimeError(header.get("err_msg") or "HKMA API failure")
            rows = (payload.get("result") or {}).get("records") or []
            if not isinstance(rows, list):
                raise RuntimeError("HKMA records is not a list")
            return rows
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(2.0 * (attempt + 1))
    raise RuntimeError(str(last_error))


def _fetch_recent(
    url: str,
    date_field: str,
    fields: str,
    start: str,
    end: str,
    extra: dict[str, str] | None = None,
) -> list[dict]:
    """Page backwards from the latest HKMA records and stop after five years.

    HKMA documents offset/pagesize as the canonical pagination path. Pulling
    newest-first avoids expensive broad date-range queries that can time out on
    daily datasets while still retaining the full rolling five-year window.
    """
    rows: list[dict] = []
    offset = 0
    page_size = 500
    seen: set[tuple[str, str]] = set()
    for _ in range(12):
        params = {
            "offset": str(offset),
            "pagesize": str(page_size),
            "fields": fields,
            "sortby": date_field,
            "sortorder": "desc",
        }
        if extra:
            params.update(extra)
        batch = _request(url, params)
        print(url.rsplit('/', 1)[-1], "offset", offset, len(batch))
        if not batch:
            break

        for row in batch:
            date_text = str(row.get(date_field) or "")
            key = (date_text, json.dumps(row, sort_keys=True, ensure_ascii=False))
            if key in seen:
                continue
            seen.add(key)
            if start <= date_text <= end:
                rows.append(row)

        valid_dates = sorted(
            str(row.get(date_field) or "")
            for row in batch
            if len(str(row.get(date_field) or "")) == 10
        )
        if valid_dates and valid_dates[0] <= start:
            break
        if len(batch) < page_size:
            break
        offset += len(batch)
    else:
        raise RuntimeError(f"HKMA pagination exceeded safety limit for {url}")

    rows.sort(key=lambda row: str(row.get(date_field) or ""))
    return rows


def main() -> None:
    now = datetime.now(timezone.utc)
    end = now.strftime("%Y-%m-%d")
    start = f"{now.year - 5:04d}-{now.month:02d}-01"

    liquidity = _fetch_recent(
        LIQ_URL,
        "end_of_date",
        "end_of_date,cu_weakside,cu_strongside,disc_win_base_rate,hibor_overnight,opening_balance,closing_balance,forecast_aggregate_bal_t1",
        start,
        end,
    )
    monetary_base = _fetch_recent(
        BASE_URL,
        "end_of_date",
        "end_of_date,outstanding_efbn,ow_lb_bf_disc_win,aggr_balance_bf_disc_win,aggr_balance_af_disc_win",
        start,
        end,
    )
    hibor = _fetch_recent(
        HIBOR_URL,
        "end_of_day",
        "end_of_day,ir_overnight,ir_3m",
        start,
        end,
        {"segment": "hibor.fixing"},
    )

    merged: dict[str, dict] = {}
    for row in liquidity:
        key = str(row.get("end_of_date") or "")
        if len(key) == 10:
            merged.setdefault(key, {"end_of_date": key}).update(row)
    for row in monetary_base:
        key = str(row.get("end_of_date") or "")
        if len(key) == 10:
            merged.setdefault(key, {"end_of_date": key}).update(row)
    for row in hibor:
        key = str(row.get("end_of_day") or "")
        if len(key) == 10:
            target = merged.setdefault(key, {"end_of_date": key})
            if row.get("ir_overnight") is not None:
                target["hibor_overnight"] = row.get("ir_overnight")
            target["hibor_3m"] = row.get("ir_3m")

    records = [merged[key] for key in sorted(merged)]
    funding_rows = [r for r in records if r.get("hibor_overnight") is not None and r.get("hibor_3m") is not None]
    balance_rows = [r for r in records if r.get("closing_balance") is not None]
    if len(funding_rows) < 200 or len(balance_rows) < 200:
        raise RuntimeError(
            f"daily snapshot incomplete: records={len(records)}, funding={len(funding_rows)}, balance={len(balance_rows)}"
        )

    payload = {
        "source": "HKMA Daily Interbank Liquidity + Daily Monetary Base + HKD HIBOR Fixing",
        "source_urls": [LIQ_URL, BASE_URL, HIBOR_URL],
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "coverage_start": records[0]["end_of_date"],
        "coverage_end": records[-1]["end_of_date"],
        "record_count": len(records),
        "fetch_strategy": "newest-first offset pagination, 500 rows per page",
        "records": records,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("wrote", len(records), "daily rows", payload["coverage_start"], payload["coverage_end"])


if __name__ == "__main__":
    main()
