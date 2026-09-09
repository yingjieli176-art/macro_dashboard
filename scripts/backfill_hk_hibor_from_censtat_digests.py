from __future__ import annotations

import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pdfplumber
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data_snapshots" / "hkd_hibor_monthly.json"
CURRENT = ROOT / "data_snapshots" / "hkma_monetary_statistics.json"
ISSUES = ["2022MM10", "2022MM12", "2023MM12", "2024MM12", "2025MM12", "2026MM06"]
URL_TEMPLATE = (
    "https://www.censtatd.gov.hk/en/data/stat_report/product/B1010002/att/"
    "B1010002{issue}B0100.pdf"
)


def _parse_page(text: str) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    for raw in text.splitlines():
        line = re.sub(r"\s+", " ", raw.strip())
        parts = line.split(" ")
        if len(parts) < 7:
            continue
        if not re.fullmatch(r"20\d{2}", parts[0]):
            continue
        if not parts[1].isdigit() or not 1 <= int(parts[1]) <= 12:
            continue
        try:
            rates = [float(parts[i]) for i in range(2, 7)]
        except (ValueError, IndexError):
            continue
        # HIBOR table columns: O/N, 1W, 1M, 3M, 6M. A narrow sanity band
        # filters unrelated finance-table rows that also begin year/month.
        if not all(-1.0 <= value <= 20.0 for value in rates):
            continue
        month = f"{int(parts[0]):04d}-{int(parts[1]):02d}"
        rows[month] = {
            "end_of_month": month,
            "hibor_overnight": rates[0],
            "hibor_1w": rates[1],
            "hibor_1m": rates[2],
            "hibor_3m": rates[3],
            "hibor_6m": rates[4],
        }
    return rows


def _extract_issue(issue: str) -> tuple[dict[str, dict], str]:
    url = URL_TEMPLATE.format(issue=issue)
    response = requests.get(url, headers={"User-Agent": "MacroDashboard/1.0"}, timeout=45)
    response.raise_for_status()
    print(issue, "downloaded", len(response.content), "bytes")
    best: dict[str, dict] = {}
    best_page = None
    with pdfplumber.open(io.BytesIO(response.content)) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            # The target page explicitly names Hong Kong Dollar Interest
            # Settlement Rates; using this guard prevents accidental parsing of
            # other rate tables with year/month rows.
            norm = re.sub(r"\s+", " ", text).lower()
            if "interest settlement rates" not in norm and "港元利息結算率" not in text:
                continue
            rows = _parse_page(text)
            if len(rows) > len(best):
                best = rows
                best_page = page_number
    print(issue, "best HIBOR page", best_page, "monthly rows", len(best))
    if len(best) < 4:
        raise RuntimeError(f"{issue}: HIBOR table not found ({len(best)} rows)")
    return best, url


def main() -> None:
    merged: dict[str, dict] = {}
    source_urls: list[str] = []
    failures: list[str] = []
    for issue in ISSUES:
        try:
            rows, url = _extract_issue(issue)
            merged.update(rows)  # newer digest revisions win
            source_urls.append(url)
        except Exception as exc:
            failures.append(f"{issue}: {exc}")
            print("WARN", failures[-1])

    # Overlay the current HKMA monthly snapshot when available: it contains more
    # decimal precision than the digest's rounded display.
    try:
        current_payload = json.loads(CURRENT.read_text(encoding="utf-8"))
        current_rows = current_payload.get("records") if isinstance(current_payload, dict) else []
        for row in current_rows or []:
            month = str(row.get("end_of_month") or "")
            if not re.fullmatch(r"20\d{2}-(0[1-9]|1[0-2])", month):
                continue
            target = merged.setdefault(month, {"end_of_month": month})
            if row.get("hibor_fixing_overnight") is not None:
                target["hibor_overnight"] = float(row["hibor_fixing_overnight"])
            if row.get("hibor_fixing_3m") is not None:
                target["hibor_3m"] = float(row["hibor_fixing_3m"])
    except Exception as exc:
        print("WARN current HKMA overlay failed:", exc)

    complete = sorted(
        month for month, row in merged.items()
        if row.get("hibor_overnight") is not None and row.get("hibor_3m") is not None
    )
    if len(complete) < 60:
        raise RuntimeError(f"HIBOR history too short: {len(complete)} complete months; failures={failures}")
    latest = complete[-1]
    ly, lm = map(int, latest.split("-"))
    cutoff_value = ly * 12 + lm - 1 - 60
    cutoff = f"{cutoff_value // 12:04d}-{cutoff_value % 12 + 1:02d}"
    selected = [merged[m] for m in complete if m >= cutoff]
    if len(selected) < 60:
        raise RuntimeError(f"HIBOR 5Y window too short: {len(selected)} from {cutoff} to {latest}")

    payload = {
        "source": "C&SD Hong Kong Monthly Digest of Statistics Table 9.13",
        "underlying_sources": ["Hong Kong Association of Banks", "Hong Kong Monetary Authority"],
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(selected),
        "coverage_start": selected[0]["end_of_month"],
        "coverage_end": selected[-1]["end_of_month"],
        "source_urls": source_urls,
        "failed_issues": failures,
        "records": selected,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("wrote HIBOR history", len(selected), selected[0]["end_of_month"], selected[-1]["end_of_month"])


if __name__ == "__main__":
    main()
