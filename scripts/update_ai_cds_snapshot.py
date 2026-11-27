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
    CDX_SNAPSHOT, NVIDIA_ISSUER_URL, SERIES, SNAPSHOT, SOURCE_URL, load_cds_snapshot,
    load_cdx_snapshot, merge_cdx_history, nvidia_issuer_reference, parse_cdx_source,
    parse_nvidia_issuer_reference, parse_source,
)


def refresh(payload, path=SNAPSHOT):
    candidate = parse_source(payload)
    old = load_cds_snapshot(path)
    if old:
        if candidate["source_asof"] < old["source_asof"]:
            raise ValueError("CDS source calendar moved backwards")
        for key in SERIES:
            if key not in candidate["series"]:
                if key in old["series"]:
                    candidate["series"][key] = old["series"][key]
                continue
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
    reference = nvidia_issuer_reference(old)
    if reference:
        candidate["nvidia_issuer_observation"] = reference
        if not nvidia_issuer_reference(candidate):
            del candidate["nvidia_issuer_observation"]
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


def refresh_nvidia_issuer(html, path=SNAPSHOT):
    reference = parse_nvidia_issuer_reference(html)
    snapshot = load_cds_snapshot(path)
    if not snapshot:
        raise ValueError("Missing valid aggregate snapshot for NVIDIA issuer reference")
    saved = nvidia_issuer_reference(snapshot)
    if saved and saved["observation_date"] > reference["observation_date"]:
        return saved
    if saved != reference:
        snapshot["nvidia_issuer_observation"] = reference
        if not nvidia_issuer_reference(snapshot):
            return None
        write_snapshot(path, snapshot, indent=2)
    return reference


def refresh_live_nvidia_issuer():
    import requests
    try:
        response = requests.get(NVIDIA_ISSUER_URL, timeout=(10, 25))
        response.raise_for_status()
        reference = refresh_nvidia_issuer(response.text)
        if reference:
            print("NVIDIA issuer trade reference:", reference)
    except (requests.RequestException, ValueError) as exc:
        print(f"NVIDIA issuer refresh failed; retained last-good observation ({exc})", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-json", type=Path, help="Saved, unmodified public chart_data.json")
    parser.add_argument("--cdx-only", action="store_true")
    args = parser.parse_args()
    if args.source_json:
        payload = json.loads(args.source_json.read_text(encoding="utf-8"))
    else:
        import requests
        try:
            response = requests.get(SOURCE_URL, timeout=(10, 45))
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException:
            if not args.cdx_only:
                refresh_live_nvidia_issuer()
            raise
    try:
        print("CDX:", {key: rows[-1] for key, rows in refresh_cdx(payload).items()})
    except (ValueError, TypeError, KeyError) as exc:
        if args.cdx_only:
            raise
        print(f"CDX refresh failed; retained last-good snapshot ({exc})", file=sys.stderr)
    if not args.cdx_only:
        try:
            result = refresh(payload)
        finally:
            if not args.source_json:
                refresh_live_nvidia_issuer()
        print(json.dumps({"source_asof": result["source_asof"], "series": {
            key: {"observations": sum(r["spread_bps"] is not None for r in node["records"]),
                  "latest": max((r["observation_date"] for r in node["records"] if r["spread_bps"] is not None), default=None)}
            for key, node in result["series"].items()}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
