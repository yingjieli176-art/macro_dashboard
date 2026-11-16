"""Read official monthly PDFs and retain dated USDJPY implied-volatility facts."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from macro_platform.jpy_option_history import (SNAPSHOT, IDENTITY, discover_reports,
                                             parse_pdf, validated_records)


def get(url, **kwargs):
    return requests.get(url, timeout=35, **kwargs)


def collect(previous=None, *, backfill=False):
    previous = previous if previous is not None else dict(IDENTITY, records=[])
    old = validated_records(previous)
    reports = discover_reports(get, backfill=backfill)
    saved = {r['issue_month']: r for r in old}
    newest = set(sorted(reports)[-2:])
    pending = [(month, url) for month,url in reports.items() if month not in saved or month in newest]
    def read(item):
        month, url = item
        response = get(url); response.raise_for_status()
        row = parse_pdf(response.content, url)
        print(month, row['observation_date'], row['value'], flush=True)
        return row
    # Parse all requested original reports before any snapshot replacement.
    with ThreadPoolExecutor(max_workers=3) as pool:
        for row in pool.map(read, pending):
            saved[row['issue_month']] = row
    rows = sorted(saved.values(), key=lambda r:r['observation_date'])
    result = dict(IDENTITY, source_url='https://q-cam.com/news-publications/', records=rows,
                  coverage_start=rows[0]['observation_date'], coverage_end=rows[-1]['observation_date'],
                  record_count=len(rows))
    validated_records(result)
    if old and (len(rows) < len(old) or rows[-1]['observation_date'] < old[-1]['observation_date']):
        raise ValueError('QCAM history would shrink or roll back')
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--backfill', action='store_true')
    args = parser.parse_args()
    previous = json.loads(SNAPSHOT.read_text(encoding='utf-8')) if SNAPSHOT.exists() else dict(IDENTITY, records=[])
    validated_records(previous)
    result = collect(previous, backfill=args.backfill or not previous['records'])
    if result.get('records') == previous.get('records'):
        print('QCAM observations unchanged'); return
    result['updated_at'] = pd.Timestamp.now(tz='UTC').isoformat()
    temporary = SNAPSHOT.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    temporary.replace(SNAPSHOT)
    print('QCAM history:',result['record_count'],result['coverage_start'],result['coverage_end'])


if __name__ == '__main__':
    main()
