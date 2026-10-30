"""Refresh original weekly CFTC yen noncommercial positions from the regulator."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from macro_platform.cftc_yen import API_URL, CONTRACT_CODE, REPORT_TYPE, SNAPSHOT, parse_cftc_yen


def fetch_cftc_yen(now=None, get=requests.get):
    clock = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    params = {
        "$where": f"cftc_contract_market_code='{CONTRACT_CODE}' AND report_date_as_yyyy_mm_dd >= '{clock.year-6}-01-01T00:00:00'",
        "$order": "report_date_as_yyyy_mm_dd ASC", "$limit": 10000,
        "$select": "market_and_exchange_names,cftc_contract_market_code,futonly_or_combined,report_date_as_yyyy_mm_dd,noncomm_positions_long_all,noncomm_positions_short_all,open_interest_all",
    }
    response = get(API_URL, params=params, headers={"User-Agent": "MacroDashboard/1.0"}, timeout=(12, 30))
    response.raise_for_status()
    return parse_cftc_yen(response.json(), now=clock)


def save_cftc_yen(frame, path=SNAPSHOT, now=None):
    clock = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    clock = clock.tz_localize(None).normalize()
    if len(frame) < 240 or frame.observation_date.min() > clock - pd.DateOffset(years=4, months=10):
        raise ValueError("Incomplete five-year CFTC yen history; retaining previous data")
    latest = frame.observation_date.max()
    if latest > clock or latest < clock-pd.Timedelta(days=17):
        raise ValueError("Future/overdue CFTC source; retaining previous data")
    records = [{key: day.strftime("%Y-%m-%d") if key == "observation_date" else int(day)
                for key, day in row.items()} for row in frame.to_dict("records")]
    if path.exists():
        previous = json.loads(path.read_text())["records"]
        if previous and max(row["observation_date"] for row in previous) > latest.strftime("%Y-%m-%d"):
            raise ValueError("CFTC source date regressed")
        retained = {row["observation_date"] for row in previous if row["observation_date"] >= records[0]["observation_date"]}
        if not retained.issubset({row["observation_date"] for row in records}):
            raise ValueError("CFTC source lost existing report dates")
        if previous == records:
            return False
    payload = {"source": API_URL, "contract_code": CONTRACT_CODE, "report_type": REPORT_TYPE,
               "unit": "contracts", "date_basis": "as-of position date, not release date",
               "formula": "noncommercial_long - noncommercial_short", "frequency": "weekly",
               "fetched_at": datetime.now(timezone.utc).isoformat(), "records": records}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2)+"\n")
    temporary.replace(path)
    return True


def main():
    frame = fetch_cftc_yen()
    changed = save_cftc_yen(frame)
    print(f"CFTC JPY: {len(frame)} reports; latest={frame.observation_date.max().date()}, changed={changed}")


if __name__ == "__main__":
    main()
