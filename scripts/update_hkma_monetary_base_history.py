from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "data_snapshots" / "hkma_monetary_statistics.json"
OFFICIAL_BASE = (
    "https://api.hkma.gov.hk/public/market-data-and-statistics/monthly-statistical-bulletin/"
    "monetary-operation/monetary-base-endperiod"
)
PARAMS = {
    "pagesize": 100,
    "offset": 0,
    "sortby": "end_of_month",
    "sortorder": "desc",
}


def _extract_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    header = payload.get("header") or {}
    if header.get("success") is False:
        raise RuntimeError(header.get("err_msg") or "HKMA API reported failure")
    records = ((payload.get("result") or {}).get("records") or [])
    if not isinstance(records, list):
        raise RuntimeError("HKMA result.records is not a list")
    rows = [row for row in records if isinstance(row, dict)]
    if len(rows) < 60:
        raise RuntimeError(f"HKMA monetary-base history too short: {len(rows)}")
    return rows


def _parse_transport_text(text: str) -> list[dict[str, Any]]:
    start = text.find('{"header"')
    if start < 0:
        raise RuntimeError("HKMA JSON body not found in transport response")
    return _extract_records(json.loads(text[start:]))


def fetch_official_records() -> list[dict[str, Any]]:
    """Fetch the same HKMA official endpoint through several transports.

    GitHub-hosted US runners intermittently time out against api.hkma.gov.hk and
    r.jina.ai can occasionally answer 422. Try the official host first, then both
    Jina transport variants with retries. The transport never changes the data
    source or field definitions.
    """
    prepared = requests.Request("GET", OFFICIAL_BASE, params=PARAMS).prepare().url
    candidates = [
        ("direct", prepared, True, 18),
        ("jina-https", "https://r.jina.ai/https://" + prepared.split("://", 1)[1], False, 50),
        ("jina-http", "https://r.jina.ai/http://" + prepared.split("://", 1)[1], False, 50),
    ]
    errors: list[str] = []
    headers = {"User-Agent": "MacroDashboard/1.0", "Accept": "application/json"}
    for round_no in range(3):
        for name, url, is_direct, timeout in candidates:
            try:
                response = requests.get(url, headers=headers, timeout=timeout)
                response.raise_for_status()
                rows = _extract_records(response.json()) if is_direct else _parse_transport_text(response.text)
                print(f"HKMA monetary-base transport={name} rows={len(rows)}")
                return rows
            except Exception as exc:
                msg = f"round={round_no + 1} transport={name}: {type(exc).__name__}: {exc}"
                errors.append(msg)
                print("WARN", msg)
        if round_no < 2:
            time.sleep(4 * (round_no + 1))
    raise RuntimeError("all HKMA monetary-base transports failed: " + " | ".join(errors[-6:]))


def main() -> None:
    payload = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    rows = payload.get("records") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise RuntimeError("HKMA monetary snapshot records missing")

    merged = {
        str(row.get("end_of_month")): dict(row)
        for row in rows
        if isinstance(row, dict) and row.get("end_of_month")
    }
    history = fetch_official_records()
    for source in history:
        month = str(source.get("end_of_month") or "")
        if not month:
            continue
        target = merged.setdefault(month, {"end_of_month": month})
        mapping = {
            "cert_of_indebt": "cert_of_indebt",
            "gov_notes_coins_circulation": "gov_notes_coins_circulation",
            "aggr_balance_bf_disc_win": "aggr_balance",
            "outstanding_efbn": "outstanding_efbn",
            "ow_lb_bf_disc_win": "ow_lb_bf_disc_win",
            "mb_bf_disc_win_total": "monetary_base_total",
        }
        for source_key, target_key in mapping.items():
            value = source.get(source_key)
            if value is not None:
                target[target_key] = value

    # Keep valid calendar months only. Annual summary rows such as YYYY-00 are
    # useful upstream but must never enter monthly chart calculations.
    records = [
        row for month, row in merged.items()
        if len(month) == 7 and month[4] == "-" and month[5:7] in {f"{m:02d}" for m in range(1, 13)}
    ]
    records.sort(key=lambda row: str(row.get("end_of_month", "")), reverse=True)

    required = {
        "monetary_base_total": 60,
        "aggr_balance": 60,
        "outstanding_efbn": 60,
        "ow_lb_bf_disc_win": 60,
    }
    coverage = {field: sum(r.get(field) is not None for r in records[:78]) for field in required}
    for field, minimum in required.items():
        if coverage[field] < minimum:
            raise RuntimeError(f"Merged {field} history too short: {coverage[field]} < {minimum}")

    payload["records"] = records
    payload["record_count"] = len(records)
    payload["coverage_start"] = records[-1]["end_of_month"]
    payload["coverage_end"] = records[0]["end_of_month"]
    payload["monetary_base_history"] = {
        "source": "Hong Kong Monetary Authority Monetary Base end-of-period API",
        "official_source_url": OFFICIAL_BASE,
        "transport": "direct HKMA first; r.jina.ai fallback used only by repository snapshot job",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(history),
        "coverage_start": history[-1].get("end_of_month"),
        "coverage_end": history[0].get("end_of_month"),
        "coverage_counts_latest_78_months": coverage,
        "fields": [
            "cert_of_indebt",
            "gov_notes_coins_circulation",
            "aggr_balance",
            "outstanding_efbn",
            "ow_lb_bf_disc_win",
            "monetary_base_total",
        ],
    }
    SNAPSHOT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        "merged HKMA monetary-base history:", len(history), "official rows;",
        "snapshot", records[-1]["end_of_month"], "to", records[0]["end_of_month"],
        "coverage", coverage,
    )


if __name__ == "__main__":
    main()
