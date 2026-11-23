"""SpaceX USD senior single-name CDS spreads reported to the DTCC SEC tape."""

import csv
from datetime import date, datetime, timezone
from io import BytesIO, TextIOWrapper
import json
import math
from pathlib import Path
from statistics import median
from zipfile import ZipFile

SNAPSHOT = Path(__file__).resolve().parents[1] / "data_snapshots" / "spacex_cds_daily.json"
SOURCE_URL = "https://pddata.dtcc.com/ppd/secdashboard"
REPORT_URL = "https://pddata.dtcc.com/api/report/cumulative/sec/"
KEY = "sn_spacex"
SPACEX_IDENTIFIERS = {"US84615QAC78", "8CA76V", "8CA76VAB1"}
SPREAD_MULTIPLIER = {"3": 10_000, "4": 1}


def report_name(day):
    return f"SEC_CUMULATIVE_CREDITS_{day:%Y_%m_%d}"


def read_report(content, day):
    with ZipFile(BytesIO(content)) as archive:
        with archive.open(report_name(day) + ".csv") as handle:
            reader = csv.DictReader(TextIOWrapper(handle, encoding="utf-8-sig"))
            if not {"Dissemination Identifier", "Underlier ID-Leg 1", "Spread-Leg 1",
                    "Spread notation-Leg 1"}.issubset(reader.fieldnames or ()):
                raise ValueError("Unexpected DTCC SEC credits report schema")
            return [row for row in reader if row["Underlier ID-Leg 1"] in SPACEX_IDENTIFIERS
                    or row["Action type"] in {"EROR", "CORR"}]


def daily_medians(rows, asof):
    prices = {}
    cancelled = set()
    for row in rows:
        action = row["Action type"]
        if action in {"EROR", "CORR"} and row["Original Dissemination Identifier"]:
            cancelled.add(row["Original Dissemination Identifier"])
        if (row["Underlier ID-Leg 1"] not in SPACEX_IDENTIFIERS
                or row["UPI FISN"] != "NA/CDS Corp SN Sr"
                or row["Notional currency-Leg 1"] != "USD"
                or action != "NEWT" or row["Event type"] != "TRAD"
                or row["Package indicator"].upper() != "FALSE"):
            continue
        multiplier = SPREAD_MULTIPLIER.get(row["Spread notation-Leg 1"])
        if not multiplier or not row["Spread-Leg 1"]:
            continue
        executed = datetime.fromisoformat(row["Execution Timestamp"])
        if executed.tzinfo is None:
            raise ValueError("DTCC execution timestamps must specify a timezone")
        day = executed.astimezone(timezone.utc).date()
        years = (date.fromisoformat(row["Expiration Date"]) - day).days / 365.25
        value = float(row["Spread-Leg 1"]) * multiplier
        if day <= asof and 4.4 <= years <= 5.6 and math.isfinite(value) and value > 0:
            prices[row["Dissemination Identifier"]] = (day, value)
    by_day = {}
    for identifier, (day, value) in prices.items():
        if identifier not in cancelled:
            by_day.setdefault(day, []).append(value)
    return [{"observation_date": day.isoformat(), "spread_bps": round(median(values), 4),
             "trade_count": len(values)} for day, values in sorted(by_day.items())]


def load_snapshot(path=SNAPSHOT):
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if payload["source_url"] != SOURCE_URL or payload["series"] != KEY:
            raise ValueError("Unexpected SpaceX CDS source")
        asof = date.fromisoformat(payload["source_asof"])
        if asof > datetime.now(timezone.utc).date():
            raise ValueError("Future SpaceX CDS source date")
        records = payload["records"]
        dates = [date.fromisoformat(row["observation_date"]) for row in records]
        if not dates or dates != sorted(set(dates)) or dates[-1] > asof:
            raise ValueError("Invalid SpaceX CDS calendar")
        if not all(math.isfinite(row["spread_bps"]) and row["spread_bps"] > 0
                   and row["trade_count"] > 0 for row in records):
            raise ValueError("Invalid SpaceX spread")
        return payload
    except (OSError, ValueError, KeyError, TypeError):
        return {}
