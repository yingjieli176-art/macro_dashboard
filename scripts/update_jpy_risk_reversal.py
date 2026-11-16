"""Append dated original Saxo risk reversals; never invent prior-day quotes."""
import json
from pathlib import Path
import sys
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from macro_platform.jpy_risk_reversal import SNAPSHOT, SOURCE_URL, prepare_snapshot


def main():
    response = requests.get(SOURCE_URL, timeout=25)
    response.raise_for_status()
    previous = json.loads(SNAPSHOT.read_text(encoding='utf-8')) if SNAPSHOT.exists() else None
    payload = prepare_snapshot(response.text, previous)
    if payload is None:
        print('Saxo RR observation unchanged'); return
    temporary = SNAPSHOT.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    temporary.replace(SNAPSHOT)
    print(payload['symbol'],payload['record_count'],payload['coverage_end'])


if __name__ == '__main__':
    main()
