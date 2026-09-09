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


def fetch_page(offset: int, page_size: int = 100) -> list[dict]:
    query = urllib.parse.urlencode({"offset": offset, "pagesize": page_size})
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
            with urllib.request.urlopen(request, timeout=30) as response:
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
    raise RuntimeError(f"HKMA fetch failed at offset={offset}: {last_error}")


def main() -> None:
    page_size = 100
    rows: list[dict] = []
    for page in range(4):
        batch = fetch_page(page * page_size, page_size)
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < page_size:
            break

    monthly = []
    seen = set()
    for row in rows:
        period = str(row.get("end_of_month") or "")
        if len(period) != 7 or period[4] != "-" or period[5:] == "00":
            continue
        if period in seen:
            continue
        seen.add(period)
        monthly.append(row)

    monthly.sort(key=lambda item: item.get("end_of_month", ""), reverse=True)
    if len(monthly) < 24:
        raise RuntimeError(f"HKMA snapshot too short: {len(monthly)} monthly records")

    payload = {
        "source": "HKMA Monetary Statistics",
        "source_url": URL,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(monthly),
        "records": monthly,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(monthly)} HKMA monthly records to {OUT}")


if __name__ == "__main__":
    main()
