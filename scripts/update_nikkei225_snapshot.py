"""Persist genuine completed daily closes for the Nikkei 225 index."""
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
from urllib.parse import quote

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from macro_platform.market_history import completed_daily_closes

SYMBOL = "^N225"
SOURCE = "https://query1.finance.yahoo.com/v8/finance/chart/%5EN225"
OUTPUT = ROOT / "data_snapshots/nikkei225_daily.json"


def collect_history():
    now = pd.Timestamp.now(tz="UTC")
    period1 = int((now - pd.DateOffset(years=6)).timestamp())
    period2 = int(now.timestamp())
    errors = []
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        url = f"https://{host}/v8/finance/chart/{quote(SYMBOL, safe='')}"
        try:
            response = requests.get(
                url,
                params={"period1": period1, "period2": period2, "interval": "1d",
                        "events": "history", "includePrePost": "false"},
                headers={"User-Agent": "Mozilla/5.0 (compatible; MacroDashboard/1.0)"},
                timeout=(5, 25),
            )
            response.raise_for_status()
            payload = response.json() or {}
            nodes = ((payload.get("chart") or {}).get("result") or [])
            if len(nodes) != 1:
                raise ValueError("Yahoo Finance returned no unique Nikkei 225 history")
            node = nodes[0]
            meta = node.get("meta") or {}
            if (meta.get("symbol") != SYMBOL or meta.get("currency") != "JPY"
                    or meta.get("instrumentType") != "INDEX"
                    or meta.get("dataGranularity") != "1d"):
                raise ValueError("Unexpected Nikkei 225 identity, currency or frequency")
            frame = completed_daily_closes(node)
            if frame.empty:
                raise ValueError("No completed daily Nikkei 225 closes")
            frame = frame[["observation_date", "close"]].copy()
            frame["close"] = pd.to_numeric(frame["close"], errors="coerce").round().astype("Int64")
            frame = frame.dropna(subset=["observation_date", "close"]).sort_values("observation_date")
            if len(frame) < 1100:
                raise ValueError("Nikkei 225 history shorter than five years of daily sessions")
            if frame.observation_date.min() > pd.Timestamp.now(tz="Asia/Tokyo").tz_localize(None).normalize() - pd.DateOffset(years=5, days=-14):
                raise ValueError("Nikkei 225 history does not cover five full years")
            if frame.observation_date.dt.dayofweek.ge(5).any():
                raise ValueError("Nikkei 225 source contains weekend observations")
            cutoff = pd.Timestamp.now(tz="Asia/Tokyo").tz_localize(None).normalize()
            latest = frame.observation_date.max()
            if latest > cutoff or latest + pd.offsets.BDay(3) < cutoff:
                raise ValueError("Nikkei 225 source is future-dated or stale")
            frame.attrs["source_url"] = response.url
            return frame
        except (requests.RequestException, ValueError, KeyError, TypeError) as error:
            errors.append(f"{host}: {type(error).__name__}: {error}")
    raise RuntimeError("No valid Nikkei 225 daily history: " + "; ".join(errors))


def save_snapshot(frame, path=OUTPUT):
    old = {}
    if path.exists():
        old = json.loads(path.read_text())
    records = [
        {"date": row.observation_date.strftime("%Y-%m-%d"), "close": int(row.close)}
        for row in frame.itertuples(index=False)
    ]
    old_dates = {row["date"] for row in old.get("records", [])}
    new_dates = {row["date"] for row in records}
    if old_dates and not old_dates.issubset(new_dates):
        raise ValueError("Nikkei 225 response lost previously verified observations")
    if old.get("records") == records:
        return False
    payload = {
        "symbol": SYMBOL,
        "source": "Yahoo Finance · Nikkei 225",
        "source_url": frame.attrs.get("source_url", SOURCE),
        "frequency": "1d",
        "unit": "index points",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "coverage_start": records[0]["date"],
        "coverage_end": records[-1]["date"],
        "records": records,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    temporary.replace(path)
    return True


def main():
    frame = collect_history()
    changed = save_snapshot(frame)
    print("Nikkei 225", len(frame), frame.observation_date.min().date(),
          frame.observation_date.max().date(), "snapshot changed=", changed)


if __name__ == "__main__":
    main()
