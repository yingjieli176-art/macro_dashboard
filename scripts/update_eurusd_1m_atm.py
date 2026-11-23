"""Append separately validated EUR/USD and USD/JPY 1M ATM Saxo quotes."""
import argparse
from pathlib import Path

import requests

from macro_platform.cross_asset_volatility import (
    SAXO_URL, SNAPSHOT, USDJPY_SNAPSHOT, accept_saxo_report, accept_usdjpy_report,
)


def update(path=SNAPSHOT, usdjpy_path=USDJPY_SNAPSHOT, get=requests.get):
    response = get(SAXO_URL, timeout=(5, 20), headers={
        "User-Agent": "Mozilla/5.0 (compatible; macro-dashboard-data-collector/1.0)"})
    response.raise_for_status()
    # Validate every pair independently: a missing row must not overwrite
    # previously verified observations for the other pair.
    results = {}
    for pair, writer, target in (
        ("EURUSD", accept_saxo_report, path),
        ("USDJPY", accept_usdjpy_report, usdjpy_path),
    ):
        try:
            results[pair] = writer(response.text, path=Path(target))
        except (ValueError, TypeError, KeyError) as exc:
            print(f"{pair} 1M ATM: quote unavailable ({exc})")
            results[pair] = None
    if all(value is None for value in results.values()):
        raise ValueError("Saxo 1M ATM report contains no validated FX quotes")
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, default=SNAPSHOT)
    parser.add_argument("--usdjpy-snapshot", type=Path, default=USDJPY_SNAPSHOT)
    args = parser.parse_args()
    results = update(args.snapshot, args.usdjpy_snapshot)
    for pair, rows in results.items():
        print(f"{pair} 1M ATM: {len(rows)} verified observations; latest="
              f"{rows[-1]['observation_date'] if rows else 'unavailable'}"
              if rows is not None else f"{pair} 1M ATM: existing history unchanged")


if __name__ == "__main__":
    main()
