from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "data_snapshots" / "hkma_monetary_statistics.json"
OFFICIAL_URL = (
    "https://api.hkma.gov.hk/public/market-data-and-statistics/monthly-statistical-bulletin/"
    "monetary-operation/monetary-base-endperiod?pagesize=100&offset=0&sortby=end_of_month&sortorder=desc"
)
TRANSPORT_URL = "https://r.jina.ai/https://" + OFFICIAL_URL.split("://", 1)[1]


def fetch_official_records() -> list[dict]:
    response = requests.get(
        TRANSPORT_URL,
        headers={"User-Agent": "MacroDashboard/1.0"},
        timeout=45,
    )
    response.raise_for_status()
    text = response.text
    start = text.find('{"header"')
    if start < 0:
        raise RuntimeError("HKMA JSON body not found in transport response")
    payload = json.loads(text[start:])
    header = payload.get("header") or {}
    if header.get("success") is False:
        raise RuntimeError(header.get("err_msg") or "HKMA API reported failure")
    records = ((payload.get("result") or {}).get("records") or [])
    if not isinstance(records, list) or len(records) < 60:
        raise RuntimeError(f"HKMA monetary-base history too short: {len(records) if isinstance(records, list) else 'invalid'}")
    return records


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

    records = sorted(merged.values(), key=lambda row: str(row.get("end_of_month", "")), reverse=True)
    monetary_complete = [
        r for r in records
        if r.get("monetary_base_total") is not None and r.get("aggr_balance") is not None
    ]
    if len(monetary_complete) < 60:
        raise RuntimeError(f"Merged monetary-base history too short: {len(monetary_complete)}")

    payload["records"] = records
    payload["record_count"] = len(records)
    payload["coverage_start"] = records[-1]["end_of_month"]
    payload["coverage_end"] = records[0]["end_of_month"]
    payload["monetary_base_history"] = {
        "source": "Hong Kong Monetary Authority Monetary Base end-of-period API",
        "official_source_url": OFFICIAL_URL,
        "transport": "r.jina.ai text transport used only by repository snapshot job",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(history),
        "coverage_start": history[-1].get("end_of_month"),
        "coverage_end": history[0].get("end_of_month"),
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
    )


if __name__ == "__main__":
    main()
