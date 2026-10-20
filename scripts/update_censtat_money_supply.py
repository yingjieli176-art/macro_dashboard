from __future__ import annotations

import json
import urllib.request
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data_snapshots" / "censtat_hkd_money_supply.json"
URL = "https://www.censtatd.gov.hk/api/get.php?id=340-45012&lang=en&full_series=1"
MONTHLY_URL = "https://api.hkma.gov.hk/public/market-data-and-statistics/monthly-statistical-bulletin/financial/monetary-statistics"


def main() -> None:
    req = urllib.request.Request(
        URL,
        headers={"User-Agent": "MacroDashboard/1.0", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            payload = json.load(response)
    except Exception as exc:
        print("C&SD source unavailable:", str(exc))
        payload = {}

    rows = payload.get("dataSet") or []
    # Table 340-45012 currently serves Q/Y observations, not a monthly series.
    # Never relabel quarter dates as months. Retain verified monthly history
    # and enrich it from the underlying HKMA original monthly source.
    monthly: dict[str, dict] = {}
    for path in (ROOT / "data_snapshots" / "hkma_monetary_statistics.json", OUT):
        if path.exists():
            saved = json.loads(path.read_text(encoding="utf-8"))
            for row in saved.get("records") or []:
                month = str(row.get("end_of_month") or "")
                if len(month) == 7 and month[5:] in {f"{m:02d}" for m in range(1, 13)}:
                    target = monthly.setdefault(month, {"end_of_month": month})
                    for key in ("m2_hkd", "m3_hkd"):
                        if row.get(key) is not None:
                            target[key] = row[key]
    for row in rows:
        # CURRENCY=1 is HK dollar. We only need true monthly M2/M3 values.
        if str(row.get("freq")) != "M" or str(row.get("CURRENCY")) != "1":
            continue
        series = str(row.get("sv") or "").upper()
        if series not in {"M2", "M3"}:
            continue
        period = str(row.get("period") or "")
        if len(period) != 6 or not period.isdigit():
            continue
        month = f"{period[:4]}-{period[4:]}"
        value = row.get("figure")
        if value is None:
            continue
        target = monthly.setdefault(month, {"end_of_month": month})
        target[f"{series.lower()}_hkd"] = value

    sys.path.insert(0, str(ROOT))
    from scripts.update_hkma_snapshot import _fetch_proxy_records
    original = _fetch_proxy_records(MONTHLY_URL, {"pagesize": 100, "sortby": "end_of_month", "sortorder": "desc"})
    for row in original:
        month = str(row.get("end_of_month") or "")
        if len(month) != 7 or month[5:] not in {f"{m:02d}" for m in range(1, 13)}:
            continue
        target = monthly.setdefault(month, {"end_of_month": month})
        for key in ("m2_hkd", "m3_hkd"):
            if row.get(key) is not None:
                target[key] = row[key]
                target["source_url"] = MONTHLY_URL

    records = [monthly[key] for key in sorted(monthly, reverse=True)]
    complete = [r for r in records if r.get("m2_hkd") is not None and r.get("m3_hkd") is not None]
    if len(complete) < 60:
        raise RuntimeError(f"C&SD M2/M3 history too short: {len(complete)} complete months")

    out = {
        "source": "HKMA original monthly money supply; retained verified monthly history (C&SD table currently quarterly/yearly)",
        "source_url": MONTHLY_URL,
        "cross_check_url": URL,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(records),
        "coverage_start": records[-1]["end_of_month"],
        "coverage_end": complete[0]["end_of_month"],
        "records": records,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("wrote", len(records), "HKD M2/M3 monthly backup (HKMA source)", out["coverage_start"], out["coverage_end"])
    print("latest", complete[0])


if __name__ == "__main__":
    main()
