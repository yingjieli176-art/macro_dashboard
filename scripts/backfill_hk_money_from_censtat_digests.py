from __future__ import annotations

import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pdfplumber
import requests

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "data_snapshots" / "hkma_monetary_statistics.json"

# Overlapping official C&SD monthly digests. The adjusted-money table is sourced
# from HKMA and uses the same adjusted-for-FX-swap-deposits HKD M2/M3 concept as
# the current HKMA monetary-statistics endpoint. Overlap is intentional because
# HKMA revises historical banking statistics.
ISSUES = [
    "2022MM10",
    "2022MM12",
    "2023MM12",
    "2024MM12",
    "2025MM12",
    "2026MM06",
]
URL_TEMPLATE = (
    "https://www.censtatd.gov.hk/en/data/stat_report/product/B1010002/att/"
    "B1010002{issue}B0100.pdf"
)


def _number(value: str) -> float:
    return float(value.replace(",", ""))


def _parse_adjusted_money_page(text: str) -> tuple[dict[str, dict], int]:
    """Parse one digest page and return adjusted monthly HKD M2/M3 rows.

    C&SD changed typography/table-title extraction across digest vintages, so
    the parser intentionally identifies the table from its row structure rather
    than a brittle literal title. In the adjusted-money table:
      * M2 monthly rows contain 6 tokens: year, month, swap, HKD M2, FC M2, total.
      * M3 monthly rows contain 8 tokens: year, month, HKD M3, FC M3, total,
        adjusted customer-deposit HKD, FC, total.
    A nearby unadjusted Table 9.3 has 8-token rows only, so requiring matched
    6- and 8-token rows for the same month cleanly distinguishes Table 9.5.
    """
    m2: dict[str, float] = {}
    m3: dict[str, float] = {}

    for raw in text.splitlines():
        line = re.sub(r"\s+", " ", raw.strip())
        parts = line.split(" ")
        if len(parts) not in (6, 8):
            continue
        if not re.fullmatch(r"20\d{2}", parts[0]):
            continue
        if not parts[1].isdigit() or not 1 <= int(parts[1]) <= 12:
            continue
        if not all(re.fullmatch(r"[\d,]+", token) for token in parts[2:]):
            continue

        month = f"{int(parts[0]):04d}-{int(parts[1]):02d}"
        if len(parts) == 6:
            # year, month, FX-swap deposits, adjusted HKD M2, adjusted FC M2, total M2
            m2[month] = _number(parts[3])
        else:
            # year, month, adjusted HKD M3, adjusted FC M3, total M3,
            # adjusted HKD customer deposits, adjusted FC deposits, total deposits
            m3[month] = _number(parts[2])

    months = sorted(set(m2) & set(m3))
    rows = {
        month: {
            "end_of_month": month,
            "m2_hkd": m2[month],
            "m3_hkd": m3[month],
        }
        for month in months
    }
    return rows, len(months)


def _extract_issue(issue: str) -> tuple[dict[str, dict], str]:
    url = URL_TEMPLATE.format(issue=issue)
    response = requests.get(url, headers={"User-Agent": "MacroDashboard/1.0"}, timeout=45)
    response.raise_for_status()
    print(issue, "downloaded", len(response.content), "bytes")

    best_rows: dict[str, dict] = {}
    best_page = None
    with pdfplumber.open(io.BytesIO(response.content)) as pdf:
        # Finance tables usually sit in the latter half, but scan every page so
        # older editions with shifted numbering remain supported.
        for page_number, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            rows, complete = _parse_adjusted_money_page(text)
            if complete > len(best_rows):
                best_rows = rows
                best_page = page_number

    print(issue, "best adjusted-money page", best_page, "complete months", len(best_rows))
    if len(best_rows) < 4:
        raise RuntimeError(f"{issue}: adjusted M2/M3 table not found or too short ({len(best_rows)})")
    return best_rows, url


def _month_range(start: str, end: str) -> list[str]:
    sy, sm = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    out = []
    value = sy * 12 + sm - 1
    last = ey * 12 + em - 1
    while value <= last:
        out.append(f"{value // 12:04d}-{value % 12 + 1:02d}")
        value += 1
    return out


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
    source_urls: list[str] = []
    extracted: dict[str, dict] = {}
    failures: list[str] = []

    for issue in ISSUES:
        try:
            rows, url = _extract_issue(issue)
            source_urls.append(url)
            # Later digests win because HKMA may revise prior months.
            extracted.update(rows)
        except Exception as exc:
            failures.append(f"{issue}: {exc}")
            print("WARN", failures[-1])

    for month, source_row in extracted.items():
        target = merged.setdefault(month, {"end_of_month": month})
        # Preserve precise current API values where already published. Digest
        # history (rounded to HK$ million) fills only absent historical months.
        for key in ("m2_hkd", "m3_hkd"):
            if target.get(key) is None and source_row.get(key) is not None:
                target[key] = source_row[key]

    # 5Y chart is anchored to the latest complete M2/M3 month. Keep one extra
    # month before the visible window so the first visible MoM can be computed.
    complete_months = sorted(
        month
        for month, row in merged.items()
        if row.get("m2_hkd") is not None and row.get("m3_hkd") is not None
    )
    if not complete_months:
        raise RuntimeError("No complete M2/M3 history after backfill")
    latest = complete_months[-1]
    ly, lm = map(int, latest.split("-"))
    start_value = ly * 12 + lm - 1 - 61
    required_start = f"{start_value // 12:04d}-{start_value % 12 + 1:02d}"
    required = _month_range(required_start, latest)
    missing = [m for m in required if m not in complete_months]
    if missing:
        raise RuntimeError(
            f"Official digest backfill still misses {len(missing)} months "
            f"inside {required_start}..{latest}: {missing[:18]}; failures={failures}"
        )

    records = list(merged.values())
    records.sort(key=lambda row: str(row.get("end_of_month", "")), reverse=True)
    payload["records"] = records
    payload["record_count"] = len(records)
    payload["coverage_start"] = records[-1]["end_of_month"]
    payload["coverage_end"] = records[0]["end_of_month"]
    payload["historical_backfill"] = {
        "source": "C&SD Hong Kong Monthly Digest of Statistics, adjusted money-supply table",
        "underlying_source": "Hong Kong Monetary Authority",
        "concept": "HKD M2/M3 adjusted for foreign currency swap deposits",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source_urls": source_urls,
        "failed_issues": failures,
        "complete_5y_start": required_start,
        "complete_5y_end": latest,
    }
    SNAPSHOT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        "backfill complete:", required_start, "through", latest,
        "months", len(required), "snapshot rows", len(records),
    )


if __name__ == "__main__":
    main()
