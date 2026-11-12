"""Fetch completed daily MOVE observations; preserve last good data on failure."""
import json
from pathlib import Path
import sys
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from macro_platform.move_index import SNAPSHOT, prepare_snapshot


def main():
    previous = json.loads(SNAPSHOT.read_text()) if SNAPSHOT.exists() else None
    last_error = None
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        try:
            response = requests.get(f"https://{host}/v8/finance/chart/%5EMOVE",
                params={"range": "5y", "interval": "1d", "includePrePost": "false"},
                headers={"User-Agent": "Mozilla/5.0 (compatible; MacroDashboard/1.0)"}, timeout=(5, 25))
            response.raise_for_status()
            payload = prepare_snapshot(response.json(), previous)
            if payload is None:
                print("MOVE closes unchanged; preserving observation dates and fetch timestamp")
                return
            if payload["record_count"] < 1000:
                raise ValueError("Incomplete five-year MOVE response")
            temporary = SNAPSHOT.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":"))+"\n")
            temporary.replace(SNAPSHOT)
            print(payload["symbol"], payload["record_count"], payload["coverage_start"], payload["coverage_end"])
            return
        except (requests.RequestException, ValueError, KeyError, TypeError) as error:
            last_error = error
    raise RuntimeError("No valid MOVE response; retaining last good snapshot") from last_error


if __name__ == "__main__":
    main()
