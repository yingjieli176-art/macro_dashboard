"""Refresh dated public GEX history; failures leave the last valid file intact."""
import json
from pathlib import Path
import sys
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from macro_platform.dealer_gamma import SNAPSHOT, SOURCE_URL, prepare_snapshot


def main():
    previous = json.loads(SNAPSHOT.read_text()) if SNAPSHOT.exists() else None
    response = requests.get(SOURCE_URL, headers={"User-Agent": "MacroDashboard/1.0"}, timeout=30)
    response.raise_for_status()
    payload = prepare_snapshot(response.text, previous)
    if payload is None:
        print("GEX observations unchanged; preserving original dates and fetch timestamp")
        return
    temporary = SNAPSHOT.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":"))+"\n", encoding="utf-8")
    temporary.replace(SNAPSHOT)
    print(payload["symbol"], payload["record_count"], payload["coverage_start"], payload["coverage_end"])


if __name__ == "__main__":
    main()
