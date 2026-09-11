from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data_snapshots" / "hkma_banking_liquidity_daily.json"

# Use the lighter monthly-statistical-bulletin daily endpoints as the durable
# backbone. They publish the same official daily Aggregate Balance / monetary
# base / HIBOR concepts but have proved materially more reliable from GitHub
# Actions than the large daily-interbank-liquidity endpoint.
MARKET_OP_URL = "https://api.hkma.gov.hk/public/market-data-and-statistics/monthly-statistical-bulletin/monetary-operation/market-operation-daily"
BASE_URL = "https://api.hkma.gov.hk/public/market-data-and-statistics/monthly-statistical-bulletin/monetary-operation/monetary-base-daily"
HIBOR_URL = "https://api.hkma.gov.hk/public/market-data-and-statistics/monthly-statistical-bulletin/er-ir/hk-interbank-ir-daily"

# This richer endpoint supplies opening balance / T+1 forecast / base rate. It
# is optional because it is the endpoint that repeatedly timed out in Actions.
INTERBANK_URL = "https://api.hkma.gov.hk/public/market-data-and-statistics/daily-monetary-statistics/daily-figures-interbank-liquidity"


def _request(url: str, params: dict[str, str], timeout: int = 15, attempts: int = 3) -> list[dict]:
    last_error: Exception | None = None
    for attempt in range(attempts):
        query = dict(params)
        query["_"] = str(int(time.time() * 1000))
        req = urllib.request.Request(
            f"{url}?{urllib.parse.urlencode(query)}",
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; MacroDashboard/1.0; +https://github.com/yingjieli176-art/macro_dashboard)",
                "Accept": "application/json",
                "Cache-Control": "no-cache, no-store, max-age=0",
                "Pragma": "no-cache",
                "Connection": "close",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
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
            if attempt < attempts - 1:
                time.sleep(1.25 * (attempt + 1))
    raise RuntimeError(str(last_error))


def _fetch_window(
    url: str,
    date_field: str,
    fields: str,
    start_day: date,
    end_day: date,
    extra: dict[str, str] | None = None,
    *,
    timeout: int = 15,
    attempts: int = 3,
) -> list[dict]:
    params = {
        "pagesize": "1000",
        "fields": fields,
        "choose": date_field,
        "from": start_day.isoformat(),
        "to": end_day.isoformat(),
        "sortby": date_field,
        "sortorder": "asc",
    }
    if extra:
        params.update(extra)
    rows = _request(url, params, timeout=timeout, attempts=attempts)
    print(url.rsplit("/", 1)[-1], start_day, end_day, len(rows), flush=True)
    return rows


def _fetch_window_adaptive(
    url: str,
    date_field: str,
    fields: str,
    start_day: date,
    end_day: date,
    extra: dict[str, str] | None = None,
) -> list[dict]:
    try:
        return _fetch_window(url, date_field, fields, start_day, end_day, extra)
    except Exception as exc:
        span = (end_day - start_day).days
        if span <= 14:
            raise
        mid = start_day + timedelta(days=span // 2)
        print("split", url.rsplit("/", 1)[-1], start_day, end_day, repr(exc), flush=True)
        return _fetch_window_adaptive(url, date_field, fields, start_day, mid, extra) + _fetch_window_adaptive(
            url, date_field, fields, mid + timedelta(days=1), end_day, extra
        )


def _fetch_recent(
    url: str,
    date_field: str,
    fields: str,
    start_day: date,
    end_day: date,
    extra: dict[str, str] | None = None,
) -> list[dict]:
    rows: list[dict] = []
    cursor = start_day
    while cursor <= end_day:
        window_end = min(cursor + timedelta(days=179), end_day)
        rows.extend(_fetch_window_adaptive(url, date_field, fields, cursor, window_end, extra))
        cursor = window_end + timedelta(days=1)

    deduped: dict[str, dict] = {}
    for row in rows:
        key = str(row.get(date_field) or "")
        if len(key) == 10:
            deduped[key] = row
    return [deduped[key] for key in sorted(deduped)]


def _fetch_optional_interbank(start_day: date, end_day: date) -> list[dict]:
    """Try to enrich the latest window; never block the daily backbone."""
    try:
        return _fetch_window(
            INTERBANK_URL,
            "end_of_date",
            "end_of_date,cu_weakside,cu_strongside,disc_win_base_rate,hibor_overnight,opening_balance,closing_balance,forecast_aggregate_bal_t1",
            start_day,
            end_day,
            timeout=8,
            attempts=1,
        )
    except Exception as exc:
        print("optional interbank enrichment unavailable:", repr(exc), flush=True)
        return []


def main() -> None:
    now = datetime.now(timezone.utc)
    end_day = now.date()
    start_day = end_day - timedelta(days=550)  # 18-month buffer for <=1Y views

    market_ops = _fetch_recent(
        MARKET_OP_URL,
        "end_of_day",
        "end_of_day,closing_balance",
        start_day,
        end_day,
    )
    monetary_base = _fetch_recent(
        BASE_URL,
        "end_of_day",
        "end_of_day,outstanding_efbn,ow_lb_bf_disc_win,aggr_balance_bf_disc_win",
        start_day,
        end_day,
    )
    hibor = _fetch_recent(
        HIBOR_URL,
        "end_of_day",
        "end_of_day,ir_overnight,ir_3m",
        start_day,
        end_day,
        {"segment": "hibor.fixing"},
    )

    # Only ask the fragile rich endpoint for the latest 45 days. If it times
    # out, the snapshot remains fully daily for Closing Balance / EFBN / HIBOR.
    interbank = _fetch_optional_interbank(max(start_day, end_day - timedelta(days=45)), end_day)

    merged: dict[str, dict] = {}
    for row in market_ops:
        key = str(row.get("end_of_day") or "")
        if len(key) == 10:
            target = merged.setdefault(key, {"end_of_date": key})
            if row.get("closing_balance") is not None:
                target["closing_balance"] = row.get("closing_balance")

    for row in monetary_base:
        key = str(row.get("end_of_day") or "")
        if len(key) == 10:
            target = merged.setdefault(key, {"end_of_date": key})
            for field in ("outstanding_efbn", "ow_lb_bf_disc_win", "aggr_balance_bf_disc_win"):
                if row.get(field) is not None:
                    target[field] = row.get(field)
            if target.get("closing_balance") is None and row.get("aggr_balance_bf_disc_win") is not None:
                target["closing_balance"] = row.get("aggr_balance_bf_disc_win")

    for row in hibor:
        key = str(row.get("end_of_day") or "")
        if len(key) == 10:
            target = merged.setdefault(key, {"end_of_date": key})
            if row.get("ir_overnight") is not None:
                target["hibor_overnight"] = row.get("ir_overnight")
            if row.get("ir_3m") is not None:
                target["hibor_3m"] = row.get("ir_3m")

    for row in interbank:
        key = str(row.get("end_of_date") or "")
        if len(key) == 10:
            target = merged.setdefault(key, {"end_of_date": key})
            for field in (
                "cu_weakside",
                "cu_strongside",
                "disc_win_base_rate",
                "hibor_overnight",
                "opening_balance",
                "closing_balance",
                "forecast_aggregate_bal_t1",
            ):
                if row.get(field) is not None:
                    target[field] = row.get(field)

    records = [merged[key] for key in sorted(merged)]
    funding_rows = [r for r in records if r.get("hibor_overnight") is not None and r.get("hibor_3m") is not None]
    balance_rows = [r for r in records if r.get("closing_balance") is not None]
    if len(records) < 200 or len(funding_rows) < 200 or len(balance_rows) < 200:
        raise RuntimeError(
            f"daily snapshot incomplete: records={len(records)}, funding={len(funding_rows)}, balance={len(balance_rows)}"
        )

    payload = {
        "source": "HKMA Market Operation Daily + Monetary Base Daily + HKD HIBOR Fixing; recent Interbank Liquidity enrichment when available",
        "source_urls": [MARKET_OP_URL, BASE_URL, HIBOR_URL, INTERBANK_URL],
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "coverage_start": records[0]["end_of_date"],
        "coverage_end": records[-1]["end_of_date"],
        "record_count": len(records),
        "fetch_strategy": "official HKMA daily bulletin backbone in bounded windows; optional 45-day rich interbank enrichment",
        "records": records,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("wrote", len(records), "daily rows", payload["coverage_start"], payload["coverage_end"], flush=True)


if __name__ == "__main__":
    main()
