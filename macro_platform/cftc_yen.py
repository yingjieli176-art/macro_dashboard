"""CFTC Legacy Futures Only yen positions, not TFF or combined options."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from macro_platform.request_runtime import observed_cache

API_URL = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"
SOURCE_URL = "https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm"
CONTRACT_CODE = "097741"
REPORT_TYPE = "Legacy Futures Only"
SNAPSHOT = Path(__file__).resolve().parents[1] / "data_snapshots/cftc_jpy_weekly.json"
COLUMNS = ["observation_date", "noncommercial_long", "noncommercial_short", "net_contracts", "open_interest"]


def parse_cftc_yen(rows, now=None):
    """Validate identity and calculate noncommercial outright long minus short."""
    clock = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    clock = clock.tz_localize(None).normalize()
    records = []
    for row in rows:
        if (row.get("cftc_contract_market_code") != CONTRACT_CODE
                or row.get("futonly_or_combined") != "FutOnly"
                or not str(row.get("market_and_exchange_names", "")).startswith("JAPANESE YEN - CHICAGO MERCANTILE EXCHANGE")):
            raise ValueError("Expected CFTC 097741 Legacy Futures Only Japanese Yen")
        day = pd.Timestamp(row["report_date_as_yyyy_mm_dd"])
        if day.tzinfo:
            day = day.tz_convert("UTC").tz_localize(None)
        if pd.isna(day) or day.normalize() > clock:
            raise ValueError("Invalid/future CFTC position date")
        values = [float(row[key]) for key in ("noncomm_positions_long_all", "noncomm_positions_short_all", "open_interest_all")]
        if any(not value.is_integer() or value < 0 for value in values):
            raise ValueError("Invalid CFTC contract count")
        long, short, interest = map(int, values)
        if max(long, short) > interest or interest == 0:
            raise ValueError("CFTC positions exceed open interest")
        records.append(dict(zip(COLUMNS, (day.normalize(), long, short, long-short, interest))))
    frame = pd.DataFrame(records, columns=COLUMNS)
    if frame.observation_date.duplicated().any():
        raise ValueError("Duplicate CFTC report dates")
    return frame.sort_values("observation_date").reset_index(drop=True)


def read_cftc_yen(path=SNAPSHOT, now=None):
    try:
        payload = json.loads(path.read_text())
        if payload.get("contract_code") != CONTRACT_CODE or payload.get("report_type") != REPORT_TYPE:
            raise ValueError("Wrong CFTC snapshot identity")
        rows = [{"cftc_contract_market_code": CONTRACT_CODE, "futonly_or_combined": "FutOnly",
                 "market_and_exchange_names": "JAPANESE YEN - CHICAGO MERCANTILE EXCHANGE",
                 "report_date_as_yyyy_mm_dd": row["observation_date"],
                 "noncomm_positions_long_all": row["noncommercial_long"],
                 "noncomm_positions_short_all": row["noncommercial_short"],
                 "open_interest_all": row["open_interest"]} for row in payload["records"]]
        frame = parse_cftc_yen(rows, now=now)
        if frame.net_contracts.tolist() != [row["net_contracts"] for row in sorted(payload["records"], key=lambda r: r["observation_date"])]:
            raise ValueError("Inconsistent CFTC net position")
        return frame
    except (OSError, ValueError, KeyError, TypeError, OverflowError):
        return pd.DataFrame(columns=COLUMNS)


@observed_cache(paths=lambda: (SNAPSHOT,))
def load_cftc_yen():
    return read_cftc_yen()
