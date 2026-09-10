from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data_snapshots" / "hkma_monetary_statistics.json"
MONETARY_URL = (
    "https://api.hkma.gov.hk/public/market-data-and-statistics/monthly-statistical-bulletin/"
    "financial/monetary-statistics"
)
MONETARY_BASE_URL = (
    "https://api.hkma.gov.hk/public/market-data-and-statistics/monthly-statistical-bulletin/"
    "monetary-operation/monetary-base-endperiod"
)
PROXY_PREFIX = "https://r.jina.ai/https://"
MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
KEEP_MONTHS = 78

MONETARY_FIELDS = [
    "notes_coins_circulation",
    "aggr_balance",
    "ef_bills_notes",
    "monetary_base_total",
    "m1_hkd",
    "m2_hkd",
    "m3_hkd",
    "exrate_hkd_usd",
    "nominal_eff_exrate_index",
    "hibor_fixing_overnight",
    "hibor_fixing_3m",
    "discount_window_base_rate",
]
BASE_FIELD_MAP = {
    "cert_of_indebt": "cert_of_indebt",
    "gov_notes_coins_circulation": "gov_notes_coins_circulation",
    "aggr_balance_bf_disc_win": "aggr_balance",
    "outstanding_efbn": "outstanding_efbn",
    "ow_lb_bf_disc_win": "ow_lb_bf_disc_win",
    "mb_bf_disc_win_total": "monetary_base_total",
}


def _month_add(period: str, months: int) -> str:
    year, month = map(int, period.split("-"))
    value = year * 12 + (month - 1) + months
    return f"{value // 12:04d}-{value % 12 + 1:02d}"


def _month_min(a: str, b: str) -> str:
    return a if a <= b else b


def _proxy_url(official_url: str, params: dict[str, Any]) -> str:
    request = requests.Request("GET", official_url, params=params).prepare()
    return PROXY_PREFIX + request.url.split("://", 1)[1]


def _parse_proxy_json(text: str) -> dict[str, Any]:
    start = text.find('{"header"')
    if start < 0:
        raise RuntimeError("HKMA JSON body not found in transport response")
    payload = json.loads(text[start:])
    header = payload.get("header") or {}
    if header.get("success") is False:
        raise RuntimeError(header.get("err_msg") or "HKMA API reported failure")
    return payload


def _fetch_proxy_records(official_url: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    url = _proxy_url(official_url, params)
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = requests.get(
                url,
                headers={"User-Agent": "MacroDashboard/1.0"},
                timeout=50,
            )
            response.raise_for_status()
            payload = _parse_proxy_json(response.text)
            records = ((payload.get("result") or {}).get("records") or [])
            if not isinstance(records, list):
                raise RuntimeError("HKMA result.records is not a list")
            return [row for row in records if isinstance(row, dict)]
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"HKMA proxy fetch failed: {last_error}")


def fetch_monetary_history() -> list[dict[str, Any]]:
    """Fetch real monthly observations in bounded date windows.

    The monetary-statistics endpoint mixes recent monthly rows with annual
    summary rows when queried without a date range, and offset pagination is
    not reliable for older monthly observations. Explicit month ranges avoid
    both behaviours and preserve the original HKMA field definitions.
    """
    now = datetime.now(timezone.utc)
    latest_month = f"{now.year:04d}-{now.month:02d}"
    start_month = _month_add(latest_month, -(KEEP_MONTHS + 2))
    merged: dict[str, dict[str, Any]] = {}
    cursor = start_month
    fields = ",".join(["end_of_month", *MONETARY_FIELDS])

    while cursor <= latest_month:
        end = _month_min(_month_add(cursor, 11), latest_month)
        rows = _fetch_proxy_records(
            MONETARY_URL,
            {
                "choose": "end_of_month",
                "from": cursor,
                "to": end,
                "fields": fields,
                "sortby": "end_of_month",
                "sortorder": "asc",
                "pagesize": 100,
            },
        )
        monthly_rows = 0
        for row in rows:
            period = str(row.get("end_of_month") or "")
            if MONTH_RE.match(period):
                merged[period] = row
                monthly_rows += 1
        print(f"HKMA monetary-statistics {cursor}..{end}: {monthly_rows} monthly rows")
        cursor = _month_add(end, 1)
        time.sleep(0.35)

    return [merged[key] for key in sorted(merged, reverse=True)]


def fetch_monetary_base_history() -> list[dict[str, Any]]:
    rows = _fetch_proxy_records(
        MONETARY_BASE_URL,
        {
            "pagesize": 100,
            "offset": 0,
            "sortby": "end_of_month",
            "sortorder": "desc",
        },
    )
    monthly = [row for row in rows if MONTH_RE.match(str(row.get("end_of_month") or ""))]
    print(f"HKMA monetary-base-endperiod: {len(monthly)} monthly rows")
    return monthly


def load_existing() -> dict[str, dict[str, Any]]:
    if not OUT.exists():
        return {}
    try:
        payload = json.loads(OUT.read_text(encoding="utf-8"))
    except Exception:
        return {}
    merged: dict[str, dict[str, Any]] = {}
    for row in payload.get("records") or []:
        if not isinstance(row, dict):
            continue
        period = str(row.get("end_of_month") or "")
        if MONTH_RE.match(period):
            merged[period] = dict(row)
    return merged


def _merge_non_null(target: dict[str, Any], source: dict[str, Any], fields: list[str]) -> None:
    for field in fields:
        value = source.get(field)
        if value is not None:
            target[field] = value


def _valid_count(records: list[dict[str, Any]], field: str) -> int:
    return sum(row.get(field) is not None for row in records)


def main() -> None:
    existing = load_existing()
    monetary = fetch_monetary_history()
    base = fetch_monetary_base_history()

    merged = {period: dict(row) for period, row in existing.items()}

    # Field-level merge is deliberate: historical M2/M3 repaired from official
    # C&SD digests and monetary-base structural fields must survive refreshes.
    for row in monetary:
        period = str(row.get("end_of_month") or "")
        target = merged.setdefault(period, {"end_of_month": period})
        _merge_non_null(target, row, MONETARY_FIELDS)

    for row in base:
        period = str(row.get("end_of_month") or "")
        target = merged.setdefault(period, {"end_of_month": period})
        for source_field, target_field in BASE_FIELD_MAP.items():
            value = row.get(source_field)
            if value is not None:
                target[target_field] = value

    if not merged:
        raise RuntimeError("No HKMA monthly history available after merge")

    latest = max(merged)
    cutoff = _month_add(latest, -(KEEP_MONTHS - 1))
    records = [
        merged[period]
        for period in sorted(merged, reverse=True)
        if period >= cutoff and MONTH_RE.match(period)
    ]

    required_minimums = {
        "m2_hkd": 58,
        "m3_hkd": 58,
        "monetary_base_total": 60,
        "aggr_balance": 60,
        "hibor_fixing_overnight": 58,
        "hibor_fixing_3m": 58,
        "discount_window_base_rate": 58,
        "exrate_hkd_usd": 58,
        "outstanding_efbn": 60,
        "ow_lb_bf_disc_win": 60,
    }
    coverage = {field: _valid_count(records, field) for field in required_minimums}
    for field, minimum in required_minimums.items():
        if coverage[field] < minimum:
            raise RuntimeError(
                f"HKMA 5Y coverage incomplete for {field}: {coverage[field]} < {minimum}"
            )

    payload = {
        "source": "HKMA Monetary Statistics + Monetary Base end-of-period",
        "source_url": MONETARY_URL,
        "monetary_base_source_url": MONETARY_BASE_URL,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(records),
        "coverage_start": records[-1]["end_of_month"],
        "coverage_end": records[0]["end_of_month"],
        "fetch_strategy": "HKMA official APIs via repository-only text transport; 12-month windows + field-level merge",
        "coverage_counts": coverage,
        "records": records,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        "wrote", len(records), "HKMA monthly records;",
        payload["coverage_start"], "to", payload["coverage_end"],
    )
    print("coverage", coverage)


if __name__ == "__main__":
    main()
