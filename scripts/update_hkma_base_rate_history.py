from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data_snapshots" / "hkma_base_rate_monthly.json"
OFFICIAL_URL = (
    "https://api.hkma.gov.hk/public/market-data-and-statistics/monthly-statistical-bulletin/"
    "monetary-operation/disc-win-liquid-adj-win-rates-endperiod"
)
TRANSPORT_URL = (
    "https://r.jina.ai/https://"
    + OFFICIAL_URL.split("://", 1)[1]
    + "?pagesize=100&offset=0&sortby=end_of_month&sortorder=desc"
)
MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def main() -> None:
    response = requests.get(
        TRANSPORT_URL,
        headers={"User-Agent": "MacroDashboard/1.0"},
        timeout=50,
    )
    response.raise_for_status()
    start = response.text.find('{"header"')
    if start < 0:
        raise RuntimeError("HKMA JSON body not found")
    payload = json.loads(response.text[start:])
    header = payload.get("header") or {}
    if header.get("success") is False:
        raise RuntimeError(header.get("err_msg") or "HKMA API failure")
    rows = ((payload.get("result") or {}).get("records") or [])
    records = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        period = str(row.get("end_of_month") or "")
        if not MONTH_RE.match(period):
            continue
        value = row.get("disc_win_base_rate")
        if value is None:
            continue
        records.append({
            "end_of_month": period,
            "disc_win_base_rate": value,
        })
    records.sort(key=lambda row: row["end_of_month"])
    if len(records) < 60:
        raise RuntimeError(f"HKMA Base Rate history too short: {len(records)}")
    out = {
        "source": "Hong Kong Monetary Authority Discount Window Base Rate — end of period",
        "source_url": OFFICIAL_URL,
        "transport": "r.jina.ai text transport used only by repository snapshot job",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(records),
        "coverage_start": records[0]["end_of_month"],
        "coverage_end": records[-1]["end_of_month"],
        "records": records,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("HKMA Base Rate history", len(records), records[0]["end_of_month"], records[-1]["end_of_month"])


if __name__ == "__main__":
    main()
