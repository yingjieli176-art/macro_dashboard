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


def _decode_payload(raw: bytes) -> dict:
    text = raw.decode("utf-8", errors="replace").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


def _fetch_bytes(url: str, timeout: int) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "MacroDashboard/1.0 (+https://github.com/yingjieli176-art/macro_dashboard)",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _request(url: str, params: dict[str, object]) -> list[dict]:
    query = urllib.parse.urlencode(params)
    official = f"{url}?{query}"
    proxy = "https://r.jina.ai/http://" + official.removeprefix("https://")
    last_error: Exception | None = None

    # GitHub-hosted runners have intermittently timed out against api.hkma.gov.hk.
    # The proxy is transport-only; the underlying dataset and field definitions remain HKMA.
    for candidate, timeout in ((proxy, 35), (official, 10)):
        for attempt in range(2):
            try:
                payload = _decode_payload(_fetch_bytes(candidate, timeout))
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
                if attempt == 0:
                    time.sleep(1)
    raise RuntimeError(f"HKMA request failed: {last_error}")


def _five_year_start() -> str:
    today = date.today()
    try:
        return today.replace(year=today.year - 5).isoformat()
    except ValueError:
        return today.replace(year=today.year - 5, day=28).isoformat()


def _fetch_range(url: str, fields: list[str]) -> list[dict]:
    rows: list[dict] = []
    page_size = 1000
    for offset in (0, 1000):
        params = {
            "choose": "end_of_date",
            "from": _five_year_start(),
            "to": date.today().isoformat(),
            "sortby": "end_of_date",
            "sortorder": "asc",
            "pagesize": page_size,
            "fields": ",".join(fields),
            "offset": offset,
        }
        batch = _request(url, params)
        rows.extend(batch)
        if len(batch) < page_size:
            break

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
        "transport_fallback": "r.jina.ai when direct HKMA access is unavailable from CI",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(records),
        "records": records,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(records)} HKMA daily banking-liquidity records to {OUT}")


if __name__ == "__main__":
    main()
