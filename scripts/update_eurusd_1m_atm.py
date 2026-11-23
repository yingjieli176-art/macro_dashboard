"""Append verified EUR/USD 1M ATM option-implied volatility from Saxo's dated report."""
import argparse
from pathlib import Path

import requests

from macro_platform.cross_asset_volatility import SAXO_URL, SNAPSHOT, accept_saxo_report


def update(path=SNAPSHOT, get=requests.get):
    response = get(SAXO_URL, timeout=(5, 20), headers={
        "User-Agent": "Mozilla/5.0 (compatible; macro-dashboard-data-collector/1.0)"})
    response.raise_for_status()
    return accept_saxo_report(response.text, path=Path(path))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, default=SNAPSHOT)
    args = parser.parse_args()
    records = update(args.snapshot)
    print(f"EUR/USD 1M ATM: {len(records)} validated dated observations; "
          f"latest={records[-1]['observation_date'] if records else 'none'}")


if __name__ == "__main__":
    main()
