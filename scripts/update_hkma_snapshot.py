from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data_snapshots" / "hkma_monetary_statistics.json"
URL = "https://api.hkma.gov.hk/public/market-data-and-statistics/monthly-statistical-bulletin/financial/monetary-statistics"
FIELDS = ",".join(
    [
        "end_of_month",
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
)


def _month_add(period: str, months: int) -> str:
    year, month = map(int, period.split("-"))
    value = year * 12 + (month - 1) + months
    return f"{value // 12:04d}-{value % 12 + 1:02d}"


def _month_min(a: str, b: str) -> str:
    return a if a <= b else b


def fetch_window(start: str, end: str) -> list[dict]:
    """Fetch a small HKMA month window to avoid long-range upstream timeouts."""
    params = {
        "choose": "end_of_month",
        "from": start,
        "to": end,
        "fields": FIELDS,
        "sortby": "end_of_month",
        "sortorder": "asc",
        "pagesize": 100,
    }
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(
        f"{URL}?{query}",
        headers={
            "User-Agent": "MacroDashboard/1.0 (+https://github.com/yingjieli176-art/macro_dashboard)",
            "Accept": "application/json",
        },
    )
    last_error = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=18) as response:
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
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"HKMA fetch failed for {start}..{end}: {last_error}")


def load_existing() -> dict[str, dict]:
    if not OUT.exists():
        return {}
    try:
        payload = json.loads(OUT.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out: dict[str, dict] = {}
    for row in payload.get("records") or []:
        period = str(row.get("end_of_month") or "")
        if len(period) == 7 and period[4] == "-":
            out[period] = row
    return out


def main() -> None:
    # Keep >6 years. The extra history lets 5Y MoM/YoY charts calculate the
    # first visible points without artificial gaps at the left edge.
    now = datetime.now(timezone.utc)
    latest_month = f"{now.year:04d}-{now.month:02d}"
    start_month = _month_add(latest_month, -76)

    merged = load_existing()
    successes = 0
    failures: list[str] = []

    # Six-month chunks are intentionally small: the HKMA endpoint has been
    # unreliable for large range pulls from US-hosted CI runners.
    cursor = start_month
    while cursor <= latest_month:
        end = _month_min(_month_add(cursor, 5), latest_month)
        try:
            batch = fetch_window(cursor, end)
            successes += 1
            print(f"HKMA {cursor}..{end}: {len(batch)} rows")
            for row in batch:
                period = str(row.get("end_of_month") or "")
                if len(period) == 7 and period[4] == "-" and period >= start_month:
                    merged[period] = row
        except Exception as exc:
            failures.append(f"{cursor}..{end}: {exc}")
            print(f"WARN {failures[-1]}")
        cursor = _month_add(end, 1)

    monthly = [row for period, row in merged.items() if period >= start_month]
    monthly.sort(key=lambda item: item.get("end_of_month", ""), reverse=True)

    # Do not overwrite the repository snapshot with a partial backfill.
    valid_money = [
        row
        for row in monthly
        if row.get("m2_hkd") is not None and row.get("m3_hkd") is not None
    ]
    if len(monthly) < 60 or len(valid_money) < 60:
        raise RuntimeError(
            f"HKMA 5Y backfill incomplete: rows={len(monthly)}, "
            f"M2/M3 rows={len(valid_money)}, windows_ok={successes}, failures={len(failures)}"
        )

    payload = {
        "source": "HKMA Monetary Statistics",
        "source_url": URL,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(monthly),
        "coverage_start": monthly[-1].get("end_of_month"),
        "coverage_end": monthly[0].get("end_of_month"),
        "fetch_strategy": "six-month range chunks merged with last good snapshot",
        "records": monthly,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {len(monthly)} HKMA monthly records to {OUT}; "
        f"coverage {payload['coverage_start']}..{payload['coverage_end']}"
    )
    if failures:
        print(f"completed with {len(failures)} failed windows preserved from last good snapshot")


if __name__ == "__main__":
    main()
