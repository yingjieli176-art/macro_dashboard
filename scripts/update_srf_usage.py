"""Refresh completed daily SRF usage from official operation-level results."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from macro_platform.srf_usage import API_URL, START, SNAPSHOT, parse_operations


def collect():
    import requests
    import pandas as pd
    response = requests.get(API_URL, params={"startDate": START,
        "endDate": pd.Timestamp.now(tz="America/New_York").strftime("%Y-%m-%d")}, timeout=(12, 45))
    response.raise_for_status()
    return response.json()


def refresh(payload, path=SNAPSHOT, today=None):
    result = parse_operations(payload, today=today)
    path = Path(path)
    if path.exists():
        old = json.loads(path.read_text(encoding="utf-8"))
        prior = {row["observation_date"]: row for row in old.get("records", [])}
        current = {row["observation_date"]: row for row in result["records"]}
        if prior and (max(current) < max(prior) or len(current) < len(prior) * .8):
            raise ValueError("SRF source is older or truncated; retaining last good history")
        merged = {**prior, **current}
        result["records"] = [merged[day] for day in sorted(merged)]
    result["retrieved_at"] = datetime.now(timezone.utc).isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".srf-usage-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-json", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.source_json.read_text()) if args.source_json else collect()
    result = refresh(payload)
    print(json.dumps({"days": len(result["records"]), "latest": result["records"][-1],
                      "incomplete_dates": result["incomplete_dates"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
