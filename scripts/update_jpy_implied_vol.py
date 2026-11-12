"""Collect one dated Saxo 3M ATM quote and atomically extend last-good history."""
from pathlib import Path
import json
import sys
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from macro_platform.jpy_implied_vol import SNAPSHOT, SOURCE_URL, prepare_snapshot


def main():
    previous = json.loads(SNAPSHOT.read_text()) if SNAPSHOT.exists() else None
    response = requests.get(SOURCE_URL, headers={'User-Agent': 'MacroDashboard/1.0'}, timeout=25)
    response.raise_for_status()
    payload = prepare_snapshot(response.text, previous)
    if payload is None:
        print('Saxo report unchanged; keeping original observation timestamp')
        return
    temporary = SNAPSHOT.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    temporary.replace(SNAPSHOT)
    print(payload['symbol'], payload['record_count'], payload['coverage_start'], payload['coverage_end'])


if __name__ == '__main__':
    main()
