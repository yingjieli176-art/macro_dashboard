"""Publish the three official CSI daily histories together, or keep last-good."""
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from macro_platform.china_equity import (
    SERIES, SNAPSHOT, SOURCE, PRICE_BASIS, completed_china_date, parse_csindex_history,
)
from macro_platform.equity_drawdown import calculate_drawdown


def save_snapshot(histories, path=SNAPSHOT, now=None):
    cutoff = completed_china_date(now)
    old = json.loads(path.read_text()) if path.exists() else {}
    output = {}
    for code, config in SERIES.items():
        frame = calculate_drawdown(histories[code]).dropna(subset=["close"])
        if len(frame) < 2000 or frame.observation_date.min() > pd.Timestamp(config["base_date"]) + pd.Timedelta(days=10):
            raise ValueError(f"{code}: incomplete history; historical highs may be missing")
        latest = frame.observation_date.max()
        if latest > cutoff or latest + pd.offsets.BDay(3) < cutoff:
            raise ValueError(f"{code}: future, incomplete or stale daily history")
        if frame.observation_date.dt.dayofweek.ge(5).any():
            raise ValueError(f"{code}: unexpected weekend observation")
        records = [{"date": row.observation_date.strftime("%Y-%m-%d"), "close": float(row.close)}
                   for row in frame.itertuples()]
        old_dates = {row["date"] for row in ((old.get("series") or {}).get(code) or {}).get("records", [])}
        if not old_dates.issubset({row["date"] for row in records}):
            raise ValueError(f"{code}: lost verified observations; retaining snapshot")
        output[code] = {"code": code, "name": config["name"], "frequency": "1d", "source": SOURCE,
                        "base_date": config["base_date"], "records": records}
    if output == old.get("series") and old.get("price_basis") == PRICE_BASIS:
        return False
    payload = {"price_basis": PRICE_BASIS, "source": SOURCE,
               "fetched_at": datetime.now(timezone.utc).isoformat(), "series": output}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    temporary.replace(path)
    return True


def collect_history(code):
    response = requests.get(SOURCE, params={
        "indexCode": code, "startDate": "19900101",
        "endDate": completed_china_date().strftime("%Y%m%d")}, timeout=(10, 30))
    response.raise_for_status()
    return parse_csindex_history(response.json(), code)


def main():
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=3) as pool:
        histories = dict(zip(SERIES, pool.map(collect_history, SERIES)))
    print(f"Snapshot changed={save_snapshot(histories)}")
    for code, frame in histories.items():
        print(code, len(frame), str(frame.observation_date.min().date()), str(frame.observation_date.max().date()))


if __name__ == "__main__":
    main()
