"""Refresh public CDS aggregates atomically; outages never replace good history."""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from macro_platform.ai_credit import SOURCE_URL, SNAPSHOT, SERIES, load_cds_snapshot, parse_source


def refresh(payload, path=SNAPSHOT):
    candidate = parse_source(payload)
    old = load_cds_snapshot(path)
    if old:
        if candidate["source_asof"] < old["source_asof"]:
            raise ValueError("CDS source calendar moved backwards")
        for key in SERIES:
            previous = {r["observation_date"]: r for r in old["series"].get(key, {}).get("records", [])}
            current = {r["observation_date"]: r for r in candidate["series"][key]["records"]}
            valid_old = {d: r for d, r in previous.items() if r["spread_bps"] is not None}
            valid_new = {d: r for d, r in current.items() if r["spread_bps"] is not None}
            if valid_old and (len(valid_new) < len(valid_old) * .8 or max(valid_new) < max(valid_old)):
                raise ValueError("CDS history regressed/truncated: " + key)
            # Retain prior actual observations when a rolling file omits them.
            for day, row in valid_old.items():
                if day not in current or current[day]["spread_bps"] is None:
                    current[day] = row
            candidate["series"][key]["records"] = [current[d] for d in sorted(current)]
    candidate["retrieved_at"] = datetime.now(timezone.utc).isoformat()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".ai-cds-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(candidate, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return candidate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-json", type=Path, help="Saved, unmodified public chart_data.json")
    args = parser.parse_args()
    if args.source_json:
        payload = json.loads(args.source_json.read_text(encoding="utf-8"))
    else:
        import requests
        response = requests.get(SOURCE_URL, timeout=(10, 45))
        response.raise_for_status()
        payload = response.json()
    result = refresh(payload)
    print(json.dumps({"source_asof": result["source_asof"], "series": {
        key: {"observations": sum(r["spread_bps"] is not None for r in node["records"]),
              "latest": max(r["observation_date"] for r in node["records"] if r["spread_bps"] is not None)}
        for key, node in result["series"].items()}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
