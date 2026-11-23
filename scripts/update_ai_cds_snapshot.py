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
from macro_platform.ai_credit import (
    CDX_SNAPSHOT, SERIES, SNAPSHOT, SOURCE_URL, load_cds_snapshot, load_cdx_snapshot,
    merge_cdx_history, parse_cdx_source, parse_source,
)


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
    write_snapshot(path, candidate, indent=2)
    return candidate


def write_snapshot(path, payload, *, indent=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".ai-cds-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=indent, allow_nan=False)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def refresh_cdx(payload, path=CDX_SNAPSHOT):
    observed = parse_cdx_source(payload)
    saved = load_cdx_snapshot(path)
    combined = merge_cdx_history(saved, observed)
    if combined != saved:
        write_snapshot(path, {"source_url": SOURCE_URL, "series": combined})
    return combined


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-json", type=Path, help="Saved, unmodified public chart_data.json")
    parser.add_argument("--cdx-only", action="store_true")
    args = parser.parse_args()
    if args.source_json:
        payload = json.loads(args.source_json.read_text(encoding="utf-8"))
    else:
        import requests
        response = requests.get(SOURCE_URL, timeout=(10, 45))
        response.raise_for_status()
        payload = response.json()
    try:
        print("CDX:", {key: rows[-1] for key, rows in refresh_cdx(payload).items()})
    except (ValueError, TypeError, KeyError) as exc:
        if args.cdx_only:
            raise
        print(f"CDX refresh failed; retained last-good snapshot ({exc})", file=sys.stderr)
    if not args.cdx_only:
        result = refresh(payload)
        print(json.dumps({"source_asof": result["source_asof"], "series": {
            key: {"observations": sum(r["spread_bps"] is not None for r in node["records"]),
                  "latest": max((r["observation_date"] for r in node["records"] if r["spread_bps"] is not None), default=None)}
            for key, node in result["series"].items()}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
