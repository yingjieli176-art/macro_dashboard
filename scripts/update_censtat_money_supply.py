from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data_snapshots" / "censtat_hkd_money_supply.json"
URL = "https://www.censtatd.gov.hk/api/get.php?id=340-45012&lang=en&full_series=1"


def main() -> None:
    req = urllib.request.Request(
        URL,
        headers={"User-Agent": "MacroDashboard/1.0", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=25) as response:
        payload = json.load(response)

    rows = payload.get("dataSet") or []
    monthly: dict[str, dict] = {}
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

    records = [monthly[key] for key in sorted(monthly, reverse=True)]
    complete = [r for r in records if r.get("m2_hkd") is not None and r.get("m3_hkd") is not None]
    if len(complete) < 60:
        raise RuntimeError(f"C&SD M2/M3 history too short: {len(complete)} complete months")

    out = {
        "source": "Census and Statistics Department Table 340-45012 (source: HKMA)",
        "source_url": URL,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(records),
        "coverage_start": records[-1]["end_of_month"],
        "coverage_end": records[0]["end_of_month"],
        "records": records,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("wrote", len(records), "C&SD HKD M2/M3 monthly records", out["coverage_start"], out["coverage_end"])
    print("latest", complete[0])


if __name__ == "__main__":
    main()
