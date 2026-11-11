"""Cboe SPX + SPXW put/call *volume* ratio, never broad-index or OI data."""
from datetime import datetime, time, timedelta
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SOURCE_TEMPLATE = "https://cdn.cboe.com/data/us/options/market_statistics/daily/{}_daily_options"
PRODUCT = "SPX + SPXW"
PRODUCTS = (PRODUCT, "SPX + SPXW + SPXO")
PRODUCT_FAMILY = "SPX family (publisher-defined aggregate)"


def completed_report_date(now=None):
    local = (now or datetime.now(ZoneInfo("America/New_York"))).astimezone(ZoneInfo("America/New_York"))
    return local.date() if local.time() >= time(18) else local.date() - timedelta(days=1)


def parse_daily(payload, day, now=None):
    stamp = pd.Timestamp(day)
    cutoff = completed_report_date(now)
    if pd.isna(stamp) or stamp.date() > cutoff or stamp.weekday() >= 5:
        raise ValueError("Uncompleted or invalid SPX operation date")
    # Cboe added SPXO to the named aggregate in November 2026. Preserve
    # the exact published basket on every record; never use TOTAL/INDEX P/C.
    products = [p for p in PRODUCTS if p in payload and any(
        r.get("name") == p + " PUT/CALL RATIO" for r in payload.get("ratios", []))]
    if len(products) != 1:
        raise ValueError("Explicit, unambiguous SPX family aggregate required")
    product = products[0]
    ratios = [r for r in payload.get("ratios", []) if r.get("name") == product + " PUT/CALL RATIO"]
    volumes = [r for r in payload.get(product, []) if r.get("name") == "VOLUME"]
    if len(ratios) != 1 or len(volumes) != 1:
        raise ValueError("Explicit SPX + SPXW ratio and volume rows required")
    volume = volumes[0]
    calls, puts, total = (float(volume[k]) for k in ("call", "put", "total"))
    ratio = float(ratios[0]["value"])
    if (not all(math.isfinite(v) and v >= 0 and v.is_integer() for v in (calls, puts, total))
            or calls <= 0 or total != calls + puts or not math.isfinite(ratio) or ratio < 0
            or abs(ratio - puts / calls) > 0.0051):
        raise ValueError("SPX put/call volume totals or published ratio do not reconcile")
    return dict(observation_date=stamp.strftime("%Y-%m-%d"), product=product, ratio=ratio,
                call_volume=int(calls), put_volume=int(puts), total_volume=int(total),
                source_url=SOURCE_TEMPLATE.format(stamp.strftime("%Y-%m-%d")))


def load_spx_put_call_snapshot():
    empty = pd.DataFrame(columns=["observation_date", "SPX_PCR"])
    try:
        payload = json.loads((ROOT / "data_snapshots/spx_put_call_daily.json").read_text())
        if payload.get("product") not in (*PRODUCTS, PRODUCT_FAMILY) or payload.get("ratio_basis") != "put_volume/call_volume":
            return empty
        rows = []
        for row in payload.get("records", []):
            try:
                product = row.get("product", PRODUCT)
                node = {"ratios": [{"name": product + " PUT/CALL RATIO", "value": row["ratio"]}],
                        product: [{"name": "VOLUME", "call": row["call_volume"], "put": row["put_volume"],
                                   "total": row["total_volume"]}]}
                valid = parse_daily(node, row["observation_date"])
                rows.append({"observation_date": pd.Timestamp(valid["observation_date"]), "SPX_PCR": valid["ratio"]})
            except (ValueError, KeyError, TypeError):
                continue
        return pd.DataFrame(rows, columns=empty.columns).sort_values("observation_date").drop_duplicates("observation_date", keep="last")
    except (OSError, ValueError, TypeError, KeyError):
        return empty

