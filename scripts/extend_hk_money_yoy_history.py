from __future__ import annotations

import json
from datetime import datetime, timezone

from backfill_hk_money_from_censtat_digests import SNAPSHOT, _extract_issue, _month_range

# Older overlapping C&SD digests provide the 12-month lag needed to display a
# full five years of YoY M2/M3 growth. Later issues remain authoritative where
# the core snapshot already has values; these vintages only fill missing history.
ISSUES = [
    "2020MM12",
    "2021MM06",
    "2021MM10",
    "2021MM12",
    "2022MM06",
]


def main() -> None:
    payload = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    existing = payload.get("records") if isinstance(payload, dict) else None
    if not isinstance(existing, list):
        raise RuntimeError("HKMA snapshot records missing")

    merged = {
        str(row.get("end_of_month")): dict(row)
        for row in existing
        if isinstance(row, dict) and row.get("end_of_month")
    }
    extracted: dict[str, dict] = {}
    source_urls: list[str] = []
    failures: list[str] = []

    for issue in ISSUES:
        try:
            rows, url = _extract_issue(issue)
            source_urls.append(url)
            extracted.update(rows)
        except Exception as exc:
            failures.append(f"{issue}: {exc}")
            print("WARN", failures[-1])

    if not extracted:
        raise RuntimeError(f"No older adjusted M2/M3 rows extracted; failures={failures}")

    for month, source_row in extracted.items():
        target = merged.setdefault(month, {"end_of_month": month})
        for key in ("m2_hkd", "m3_hkd"):
            if target.get(key) is None and source_row.get(key) is not None:
                target[key] = source_row[key]

    complete_months = sorted(
        month for month, row in merged.items()
        if row.get("m2_hkd") is not None and row.get("m3_hkd") is not None
    )
    if not complete_months:
        raise RuntimeError("No complete M2/M3 history after YoY extension")

    latest = complete_months[-1]
    ly, lm = map(int, latest.split("-"))
    latest_value = ly * 12 + lm - 1
    # Five-year visible window plus a full 12-month comparison base.
    required_start_value = latest_value - 72
    required_start = f"{required_start_value // 12:04d}-{required_start_value % 12 + 1:02d}"
    required = _month_range(required_start, latest)
    missing = [month for month in required if month not in complete_months]
    if missing:
        raise RuntimeError(
            f"YoY base history still misses {len(missing)} months inside "
            f"{required_start}..{latest}: {missing[:24]}; failures={failures}"
        )

    records = list(merged.values())
    records.sort(key=lambda row: str(row.get("end_of_month", "")), reverse=True)
    payload["records"] = records
    payload["record_count"] = len(records)
    payload["coverage_start"] = records[-1]["end_of_month"]
    payload["coverage_end"] = records[0]["end_of_month"]
    payload["yoy_history_backfill"] = {
        "source": "C&SD Hong Kong Monthly Digest of Statistics, adjusted money-supply table",
        "underlying_source": "Hong Kong Monetary Authority",
        "concept": "HKD M2/M3 adjusted for foreign currency swap deposits",
        "purpose": "Provide 12-month comparison base for a full five-year YoY display",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source_urls": source_urls,
        "failed_issues": failures,
        "complete_start": required_start,
        "complete_end": latest,
        "complete_months": len(required),
    }
    SNAPSHOT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        "YoY history complete:", required_start, "through", latest,
        "months", len(required), "extracted", len(extracted), "failures", failures,
    )


if __name__ == "__main__":
    main()
