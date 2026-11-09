"""Refresh the published daily close history for Yahoo! Japan's TOPIX index."""
from datetime import time
from io import StringIO
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from macro_platform.topix import SNAPSHOT_PATH, SOURCE_URL, SYMBOL, load_topix_snapshot


def read_history_page(response, cutoff):
    response.raise_for_status()
    if urlsplit(response.url).path != f"/quote/{SYMBOL}/history" or "TOPIX" not in response.text:
        raise ValueError("Unexpected TOPIX history page")
    tables = pd.read_html(StringIO(response.text), match="終値")
    frame = next((table for table in tables if list(table.columns) == ["日付", "始値", "高値", "安値", "終値"]), None)
    if frame is None or frame.empty:
        raise ValueError("No TOPIX daily close rows")
    dates = pd.to_datetime(frame["日付"], format="%Y/%m/%d", errors="raise")
    closes = pd.to_numeric(frame["終値"], errors="raise")
    if dates.dt.dayofweek.ge(5).any() or not (closes.gt(0) & closes.lt(float("inf"))).all():
        raise ValueError("Invalid TOPIX dates or values")
    return pd.DataFrame({"observation_date": dates, "topix_close": closes}).loc[dates.le(cutoff)]


def refresh(path=SNAPSHOT_PATH):
    now = pd.Timestamp.now(tz="Asia/Tokyo")
    today = now.tz_localize(None).normalize()
    cutoff = today if now.time() >= time(16) else today - pd.Timedelta(days=1)
    start = today - pd.DateOffset(years=5, days=7)
    old = load_topix_snapshot(path)
    boundary = start if old.empty else old.observation_date.max()
    pages = []
    # Initial backfill covers five years. Normal refresh stops as soon as
    # the new daily page overlaps the saved observations.
    with requests.Session() as session:
        for page in range(1, 75):
            response = session.get(SOURCE_URL, params={
                "styl": "stock", "from": start.strftime("%Y%m%d"), "to": today.strftime("%Y%m%d"),
                "timeFrame": "d", "page": page,
            }, timeout=(5, 15), headers={"User-Agent": "Mozilla/5.0 (compatible; MacroDashboard/1.0)"})
            rows = read_history_page(response, cutoff)
            if rows.empty or (pages and rows.observation_date.max() >= pages[-1].observation_date.min()):
                raise ValueError("TOPIX history pages did not advance")
            pages.append(rows)
            earliest = rows.observation_date.min()
            if earliest <= boundary + (pd.Timedelta(days=7) if old.empty else pd.Timedelta(0)):
                break
        else:
            raise ValueError("TOPIX history did not reach the requested window")
    new = pd.concat(pages)
    latest = new.observation_date.max()
    if latest + pd.offsets.BDay(3) < cutoff or (not old.empty and latest < boundary):
        raise ValueError("TOPIX source returned older observations")
    combined = (pd.concat([old, new]) if not old.empty else new).sort_values("observation_date", kind="stable")
    combined = combined.loc[combined.observation_date.ge(start)].drop_duplicates("observation_date", keep="last")
    if len(combined) < 1100 or combined.observation_date.min() > today - pd.DateOffset(years=5) + pd.Timedelta(days=7):
        raise ValueError("TOPIX history is shorter than five years")
    records = [{"observation_date": day.strftime("%Y-%m-%d"), "close": float(close)}
               for day, close in combined.itertuples(index=False, name=None)]
    payload = {"symbol": SYMBOL, "source_url": SOURCE_URL, "records": records}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    print(f"TOPIX: {len(records)} closing levels through {latest:%Y-%m-%d}")


if __name__ == "__main__":
    refresh()
