"""Refresh current copper/WTI fields independently; retain all historical rows."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import update_copper_snapshot as copper


def merge_frame(records, frame, now=None):
    today = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize() if now is None else pd.Timestamp(now)
    changed = False
    for row in frame.to_dict("records"):
        day = pd.Timestamp(row.pop("date"))
        if pd.isna(day) or day.normalize() > today or day.weekday() >= 5:
            raise ValueError("Invalid completed copper observation date")
        stamp = day.strftime("%Y-%m-%d")
        values = {}
        for key, value in row.items():
            if pd.isna(value):
                continue
            if key == "comex_stock_source":
                values[key] = str(value)
            elif math.isfinite(float(value)) and float(value) > 0:
                values[key] = float(value)
            else:
                raise ValueError("Invalid copper value: " + key)
        old = records.setdefault(stamp, {"date": stamp})
        if any(old.get(k) != v for k, v in values.items()):
            old.update(values); changed = True
    return changed


def main():
    previous = json.loads(copper.OUT.read_text())
    records = {r["date"]: dict(r) for r in previous["records"]}
    fetchers = {"HG": copper._fetch_comex_price, "WTI": copper._fetch_wti,
                "LME": lambda: copper._fetch_westmetall_year(datetime.now(timezone.utc).year),
                "CME": lambda: pd.DataFrame([copper._fetch_cme_stocks()])}
    errors, changed = [], False
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(f): name for name, f in fetchers.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                frame = future.result()
                if frame.empty:
                    raise ValueError("Empty observation feed")
                # A malformed family cannot partially change shared records.
                candidate = {d: dict(r) for d, r in records.items()}
                updated = merge_frame(candidate, frame)
                records = candidate
                changed = updated or changed
                print(name, frame.date.max(), "updated" if updated else "unchanged", flush=True)
            except Exception as exc:
                errors.append(name + ": " + type(exc).__name__)
    if changed:
        output = dict(previous, records=[records[d] for d in sorted(records)],
                      updated_at=datetime.now(timezone.utc).isoformat(), coverage_end=max(records))
        fields = previous.get("latest_by_field", {})
        output["latest_by_field"] = {key: max((d for d, r in records.items() if r.get(key) is not None), default=None)
                                     for key in fields}
        temporary = copper.OUT.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        temporary.replace(copper.OUT)
    if errors:
        raise RuntimeError("; ".join(errors))


if __name__ == "__main__":
    main()
