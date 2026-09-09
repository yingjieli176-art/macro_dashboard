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

# Overlapping official C&SD monthly digests. Table 9.5 is sourced from HKMA and
# uses the same adjusted-for-FX-swap-deposits HKD M2/M3 concept as the current
# HKMA monetary-statistics endpoint. Overlap is intentional for revision safety.
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


def _extract_issue(issue: str) -> tuple[dict[str, dict], str]:
    url = URL_TEMPLATE.format(issue=issue)
    response = requests.get(url, headers={"User-Agent": "MacroDashboard/1.0"}, timeout=40)
    response.raise_for_status()
    print(issue, "downloaded", len(response.content), "bytes")

    found: dict[str, dict] = {}
    with pdfplumber.open(io.BytesIO(response.content)) as pdf:
        page_text = None
        # Finance tables sit around this region in the digest. Restricting the
        # scan keeps the CI backfill much faster than parsing all ~300 pages.
        start = min(145, max(0, len(pdf.pages) - 1))
        stop = min(len(pdf.pages), 225)
        for page in pdf.pages[start:stop]:
            text = page.extract_text() or ""
            normalized = re.sub(r"\s+", " ", text)
            if (
                "Table 9.5" in normalized
                and "Money supply" in normalized
                and "currency swap deposits" in normalized
            ):
                page_text = text
                break
        if page_text is None:
            # Page numbering shifted in some older issues: use a full scan only
            # as a fallback.
            for page in pdf.pages:
                text = page.extract_text() or ""
                normalized = re.sub(r"\s+", " ", text)
                if (
                    "Table 9.5" in normalized
                    and "Money supply" in normalized
                    and "currency swap deposits" in normalized
                ):
                    page_text = text
                    break
    if page_text is None:
        raise RuntimeError(f"{issue}: Table 9.5 not found")

    for raw in page_text.splitlines():
        line = re.sub(r"\s+", " ", raw.strip())
        parts = line.split(" ")
        if len(parts) not in (6, 7):
            continue
        if not re.fullmatch(r"20\d{2}", parts[0]):
            continue
        if not parts[1].isdigit() or not 1 <= int(parts[1]) <= 12:
            continue
        if not all(re.fullmatch(r"[\d,]+", token) for token in parts[2:]):
            continue
        month = f"{int(parts[0]):04d}-{int(parts[1]):02d}"
        target = found.setdefault(month, {"end_of_month": month})
        if len(parts) == 6:
            # year, month, FX-swap deposits, adjusted HKD M2, adjusted FC M2, total M2
            target["m2_hkd"] = _number(parts[3])
        elif len(parts) == 7:
            # year, month, adjusted HKD M3, adjusted FC M3, total M3,
            # adjusted HKD customer deposits, total customer deposits
            target["m3_hkd"] = _number(parts[2])

    complete = sum(
        row.get("m2_hkd") is not None and row.get("m3_hkd") is not None
        for row in found.values()
    )
    print(issue, "Table 9.5 months", len(found), "complete", complete)
    if complete < 4:
        raise RuntimeError(f"{issue}: too few complete Table 9.5 months ({complete})")
    return found, url


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
        # Preserve the current API snapshot where it already has a published
        # value; use digest history only to fill absent older months.
        for key in ("m2_hkd", "m3_hkd"):
            if target.get(key) is None and source_row.get(key) is not None:
                target[key] = source_row[key]

    # 5Y chart is anchored to the latest published complete M2/M3 month. We
    # require one extra month before the visible 5Y window so the first MoM
    # point can be calculated instead of appearing blank.
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
            f"inside {required_start}..{latest}: {missing[:12]}; failures={failures}"
        )

    records = list(merged.values())
    records.sort(key=lambda row: str(row.get("end_of_month", "")), reverse=True)
    payload["records"] = records
    payload["record_count"] = len(records)
    payload["coverage_start"] = records[-1]["end_of_month"]
    payload["coverage_end"] = records[0]["end_of_month"]
    payload["historical_backfill"] = {
        "source": "C&SD Hong Kong Monthly Digest of Statistics, Table 9.5",
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
        "backfill complete:",
        required_start,
        "through",
        latest,
        "months",
        len(required),
        "snapshot rows",
        len(records),
    )


if __name__ == "__main__":
    main()
