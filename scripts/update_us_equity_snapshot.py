"""Publish genuine daily SPX/RSP closes atomically, preserving last-good history."""
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
from urllib.parse import quote

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from macro_platform.equity_drawdown import (
    PRICE_BASIS, SERIES, SNAPSHOT, calculate_drawdown, completed_us_date, parse_yahoo_history,
)


def save_snapshot(histories, path=SNAPSHOT, now=None):
    cutoff = completed_us_date(now)
    old = json.loads(path.read_text()) if path.exists() else {}
    output = {}
    for key, config in SERIES.items():
        frame = calculate_drawdown(histories[key]).dropna(subset=["close"])
        if len(frame) < 1000 or frame.observation_date.min() > cutoff - pd.DateOffset(years=5):
            raise ValueError(f"{key}: incomplete five-year daily history")
        latest = frame.observation_date.max()
        if latest > cutoff or latest + pd.offsets.BDay(3) < cutoff:
            raise ValueError(f"{key}: incomplete session, future date or stale response")
        if frame.observation_date.dt.dayofweek.ge(5).any():
            raise ValueError(f"{key}: invalid weekend equity observation")
        records = [{"date": row.observation_date.strftime("%Y-%m-%d"), "close": float(row.close)}
                   for row in frame.itertuples()]
        previous = ((old.get("series") or {}).get(key) or {}).get("records") or []
        old_dates = {row["date"] for row in previous}
        new_dates = {row["date"] for row in records}
        if not old_dates.issubset(new_dates):
            raise ValueError(f"{key}: response lost existing observations; retaining snapshot")
        output[key] = {"symbol": config["symbol"], "source": config["source"],
                       "frequency": "1d", "records": records}
    if output == old.get("series") and old.get("price_basis") == PRICE_BASIS:
        return False
    payload = {"price_basis": PRICE_BASIS,
               "fetched_at": datetime.now(timezone.utc).isoformat(), "series": output}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    temporary.replace(path)
    return True


def collect_history(key):
    errors = []
    best = None
    cutoff = completed_us_date()
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        try:
            # range=max can silently downgrade interval=1d to MONTHLY.
            # Explicit epoch bounds request the complete daily history.
            response = requests.get(
                f"https://{host}/v8/finance/chart/{quote(SERIES[key]['symbol'], safe='')}",
                params={"period1": 0, "period2": int(datetime.now(timezone.utc).timestamp()),
                        "interval": "1d", "includePrePost": "false"},
                headers={"User-Agent": "Mozilla/5.0 (compatible; MacroDashboard/1.0)"},
                timeout=(5, 25),
            )
            response.raise_for_status()
            frame = parse_yahoo_history(response.json(), key)
            if frame.empty:
                raise ValueError("No completed daily observations")
            frame.attrs["source_url"] = response.url
            if best is None or frame.observation_date.max() > best.observation_date.max():
                best = frame
            if frame.observation_date.max() >= cutoff:
                return frame
        except (requests.RequestException, ValueError, KeyError, TypeError) as error:
            errors.append(f"{host}: {type(error).__name__}: {error}")
    # A valid first host can be cached one session behind. Check the second
    # host before accepting that lag; never replace a newer valid response.
    if best is not None:
        return best
    raise RuntimeError(f"{key}: no valid daily price source; " + "; ".join(errors))


def main():
    histories = {key: collect_history(key) for key in SERIES}
    changed = save_snapshot(histories)
    for key, frame in histories.items():
        print(f"{key}: {len(frame)} daily closes, {frame.observation_date.min().date()} to {frame.observation_date.max().date()}")
    print(f"Snapshot changed={changed}")


if __name__ == "__main__":
    main()
