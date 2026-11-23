"""Refresh SpaceX's daily median of directly reported five-year CDS spreads."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
from tempfile import NamedTemporaryFile

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from macro_platform import spacex_cds


def download(day):
    url = spacex_cds.REPORT_URL + spacex_cds.report_name(day) + ".zip"
    response = requests.get(url, timeout=(8, 20))
    if response.status_code == 404:
        return day, None
    response.raise_for_status()
    return day, spacex_cds.read_report(response.content, day)


def refresh(reports, path=spacex_cds.SNAPSHOT):
    records = spacex_cds.daily_medians(
        (row for _, report in reports for row in report), max(day for day, _ in reports))
    old = spacex_cds.load_snapshot(path)
    if not records and not old:
        raise ValueError("No directly reported SpaceX 5Y spreads")
    history = {row["observation_date"]: row for row in old.get("records", [])}
    history.update({row["observation_date"]: row for row in records})
    payload = {
        "series": spacex_cds.KEY,
        "source_url": spacex_cds.SOURCE_URL,
        "source_asof": max(max(day for day, _ in reports).isoformat(), old.get("source_asof", "")),
        "records": [history[day] for day in sorted(history)],
    }
    if payload != old:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, indent=2, allow_nan=False)
            handle.write("\n")
        try:
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
    return payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, help="Directory of unmodified DTCC SEC cumulative report ZIPs")
    args = parser.parse_args()
    if args.input_dir:
        files = sorted(args.input_dir.glob("SEC_CUMULATIVE_CREDITS_????_??_??.zip"))
        reports = []
        for path in files:
            day = date.fromisoformat(path.stem[-10:].replace("_", "-"))
            reports.append((day, spacex_cds.read_report(path.read_bytes(), day)))
    else:
        today = datetime.now(timezone.utc).date()
        dates = [today - timedelta(days=lag) for lag in range(1, 11)]
        with ThreadPoolExecutor(max_workers=4) as executor:
            reports = [(day, report) for day, report in executor.map(download, dates) if report is not None]
    if not reports:
        raise ValueError("No DTCC SEC reports available")
    payload = refresh(reports)
    print(payload["source_asof"], payload["records"][-1])


if __name__ == "__main__":
    main()
