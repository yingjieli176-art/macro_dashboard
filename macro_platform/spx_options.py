"""Cboe SPX + SPXW put/call *volume* ratio, never broad-index or OI data."""
from datetime import datetime, time, timedelta
import csv
import io
from urllib.parse import urlencode
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SOURCE_TEMPLATE = "https://cdn.cboe.com/data/us/options/market_statistics/daily/{}_daily_options"
PRODUCT = "SPX + SPXW"
EXPANDED_PRODUCT = "SPX + SPXW + SPXO"
OCC_VOLUME_URL = "https://marketdata.theocc.com/volume-query"


def occ_volume_params(day):
    return dict(reportDate=pd.Timestamp(day).strftime('%Y%m%d'), format='csv',
                volumeQueryType='O', symbolType='U', symbol='SPX', reportType='D',
                accountType='ALL', productKind='OIND', porc='BOTH')


def completed_report_date(now=None):
    local = (now or datetime.now(ZoneInfo("America/New_York"))).astimezone(ZoneInfo("America/New_York"))
    return local.date() if local.time() >= time(18) else local.date() - timedelta(days=1)


def parse_daily(payload, day, now=None):
    stamp = pd.Timestamp(day)
    cutoff = completed_report_date(now)
    if pd.isna(stamp) or stamp.date() > cutoff or stamp.weekday() >= 5:
        raise ValueError("Uncompleted or invalid SPX operation date")
    ratios = [r for r in payload.get("ratios", []) if r.get("name") == PRODUCT + " PUT/CALL RATIO"]
    volumes = [r for r in payload.get(PRODUCT, []) if r.get("name") == "VOLUME"]
    if len(ratios) != 1 or len(volumes) != 1:
        raise ValueError("Explicit SPX + SPXW ratio and volume rows required")
    volume = volumes[0]
    calls, puts, total = (float(volume[k]) for k in ("call", "put", "total"))
    ratio = float(ratios[0]["value"])
    if (not all(math.isfinite(v) and v >= 0 and v.is_integer() for v in (calls, puts, total))
            or calls <= 0 or total != calls + puts or not math.isfinite(ratio) or ratio < 0
            or abs(ratio - puts / calls) > 0.0051):
        raise ValueError("SPX put/call volume totals or published ratio do not reconcile")
    return dict(observation_date=stamp.strftime("%Y-%m-%d"), ratio=ratio,
                call_volume=int(calls), put_volume=int(puts), total_volume=int(total),
                source_url=SOURCE_TEMPLATE.format(stamp.strftime("%Y-%m-%d")))


def parse_expanded_daily(payload, day, occ_text, now=None):
    """Reconcile cleared OCC sides with Cboe, then exclude the new SPXO root.

    SPXO joined Cboe's aggregate on 2026-11-09. A renamed aggregate cannot
    silently change the dashboard's original SPX + SPXW product basket.
    """
    expanded = parse_daily({
        'ratios': [dict(row, name=PRODUCT + ' PUT/CALL RATIO')
                   for row in payload.get('ratios', [])
                   if row.get('name') == EXPANDED_PRODUCT + ' PUT/CALL RATIO'],
        PRODUCT: payload.get(EXPANDED_PRODUCT, [])}, day, now)
    reader = csv.DictReader(io.StringIO(occ_text))
    required = {'quantity', 'underlying', 'symbol', 'actype', 'porc', 'exchange', 'actdate'}
    if not required.issubset(reader.fieldnames or []):
        raise ValueError('Missing OCC cleared-volume fields')
    sides, seen, roots = {}, set(), set()
    for record in reader:
        # An underlying query also returns FLEX roots such as 2SPX/4SPX;
        # those are outside both the Cboe aggregate and the original basket.
        if record['underlying'] == 'SPX' and record['symbol'] not in {'SPX', 'SPXW', 'SPXO'}:
            continue
        stamp = pd.Timestamp(record['actdate'])
        identity = tuple(record[field] for field in ('symbol', 'actype', 'porc', 'exchange', 'actdate'))
        quantity = float(record['quantity'])
        if (record['underlying'] != 'SPX' or record['symbol'] not in {'SPX', 'SPXW', 'SPXO'}
                or record['actype'] not in {'C', 'F', 'M'} or record['porc'] not in {'C', 'P'}
                or record['exchange'] != 'CBOE' or stamp != pd.Timestamp(day)
                or identity in seen or not math.isfinite(quantity) or quantity < 0 or not quantity.is_integer()):
            raise ValueError('Invalid, duplicate or mismatched OCC cleared-volume row')
        seen.add(identity)
        roots.add(record['symbol'])
        key = (record['symbol'], record['porc'])
        sides[key] = sides.get(key, 0) + int(quantity)
    if not {'SPX', 'SPXW'}.issubset(roots) or any(value % 2 for value in sides.values()):
        raise ValueError('Incomplete or unpaired OCC cleared-volume sides')
    contracts = {key: value // 2 for key, value in sides.items()}
    for side, field in [('C', 'call_volume'), ('P', 'put_volume')]:
        if sum(value for (root, cp), value in contracts.items() if cp == side) != expanded[field]:
            raise ValueError('OCC cleared-volume sides do not reconcile with Cboe aggregate')
    calls, puts = [sum(contracts.get((root, side), 0) for root in ('SPX', 'SPXW')) for side in ('C', 'P')]
    if calls <= 0:
        raise ValueError('No original-basket call volume')
    return dict(observation_date=expanded['observation_date'], ratio=round(puts / calls, 2),
                call_volume=calls, put_volume=puts, total_volume=calls + puts,
                source_url=expanded['source_url'], occ_source_url=OCC_VOLUME_URL + '?' + urlencode(occ_volume_params(day)),
                reconciliation=dict(expanded_product=EXPANDED_PRODUCT,
                    expanded_call_volume=expanded['call_volume'], expanded_put_volume=expanded['put_volume'],
                    excluded_spxo_call_volume=contracts.get(('SPXO', 'C'), 0),
                    excluded_spxo_put_volume=contracts.get(('SPXO', 'P'), 0),
                    method='OCC cleared sides / 2; matched to Cboe calls and puts; SPXO excluded'))


def load_spx_put_call_snapshot():
    empty = pd.DataFrame(columns=["observation_date", "SPX_PCR"])
    try:
        payload = json.loads((ROOT / "data_snapshots/spx_put_call_daily.json").read_text())
        if payload.get("product") != PRODUCT or payload.get("ratio_basis") != "put_volume/call_volume":
            return empty
        rows = []
        for row in payload.get("records", []):
            try:
                node = {"ratios": [{"name": PRODUCT + " PUT/CALL RATIO", "value": row["ratio"]}],
                        PRODUCT: [{"name": "VOLUME", "call": row["call_volume"], "put": row["put_volume"],
                                   "total": row["total_volume"]}]}
                valid = parse_daily(node, row["observation_date"])
                rows.append({"observation_date": pd.Timestamp(valid["observation_date"]), "SPX_PCR": valid["ratio"]})
            except (ValueError, KeyError, TypeError):
                continue
        return pd.DataFrame(rows, columns=empty.columns).sort_values("observation_date").drop_duplicates("observation_date", keep="last")
    except (OSError, ValueError, TypeError, KeyError):
        return empty

