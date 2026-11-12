"""Saxo USD/JPY three-month ATM implied quotes; never Bloomberg-labelled data."""
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re

from lxml import html
import pandas as pd
import plotly.graph_objects as go
from macro_platform.chart_axes import apply_time_axis

SOURCE_URL = 'https://fxowebtools.saxobank.com/otc.html'
SNAPSHOT = Path(__file__).resolve().parents[1] / 'data_snapshots/jpy_3m_atm_saxo.json'
SERIES_NAME = 'USD/JPY 3M ATM 隐含波动率（Saxo，R5）'
IDENTITY = {'symbol': 'USDJPY_3M_ATM_SAXO', 'source': 'Saxo Bank',
            'pair': 'USDJPY', 'tenor': '3M', 'quote_type': 'ATM', 'unit': 'percent'}


def _now(now=None):
    stamp = pd.Timestamp(now if now is not None else datetime.now(timezone.utc))
    return stamp.tz_localize('UTC') if stamp.tzinfo is None else stamp.tz_convert('UTC')


def _validate_record(row, now=None):
    timestamp = pd.Timestamp(row['observation_timestamp'])
    if timestamp.tzinfo is None:
        raise ValueError('Source timestamp must include its timezone')
    timestamp = timestamp.tz_convert('UTC')
    if timestamp > _now(now) or timestamp.strftime('%Y-%m-%d') != row['observation_date']:
        raise ValueError('Future or mismatched observation date')
    if isinstance(row['value'], bool):
        raise ValueError('Boolean is not an implied volatility quote')
    value = float(row['value'])
    if not math.isfinite(value) or not 0 < value < 100:
        raise ValueError('Invalid FX implied volatility percentage')
    return {'observation_date': row['observation_date'],
            'observation_timestamp': timestamp.isoformat(), 'value': value}


def parse_quote(text, now=None):
    """Locate ATM/3m by labels, excluding spot, change and risk-reversal cells."""
    root = html.fromstring(text)
    headings = root.xpath('//*[contains(concat(" ",normalize-space(@class)," ")," mainTitle ")]')
    section = next((h for h in headings if h.text_content().strip().upper() == 'ATM VOLATILITIES'), None)
    if section is None:
        raise ValueError('ATM volatility section missing')
    tables = section.xpath('following-sibling::div[1]//table')
    if len(tables) != 1:
        raise ValueError('Unexpected ATM table structure')
    table = tables[0]
    rows = table.xpath('.//tr')
    headers = [c.text_content().strip().lower() for c in rows[0].xpath('./th|./td')]
    if headers.count('pair') != 1 or headers.count('3m') != 1:
        raise ValueError('Missing or ambiguous three-month tenor')
    pair_index, value_index = headers.index('pair'), headers.index('3m')
    matches = []
    for row in rows[1:]:
        cells = [c.text_content().strip() for c in row.xpath('./th|./td')]
        if len(cells) > max(pair_index, value_index) and cells[pair_index] == 'USDJPY':
            matches.append(cells[value_index])
    if len(matches) != 1:
        raise ValueError('Missing or ambiguous USDJPY ATM row')
    quote = re.fullmatch(r'\s*(\d+(?:\.\d+)?)\s*\([+-]?\d+(?:\.\d+)?\)\s*', matches[0])
    if not quote:
        raise ValueError('Unexpected quote/change format')
    dates = root.xpath('//*[contains(concat(" ",normalize-space(@class)," ")," blogTitle ")]')
    if len(dates) != 1:
        raise ValueError('Source report date missing')
    stamp = datetime.strptime(' '.join(dates[0].text_content().split()), '%d %b %Y, %H%M GMT').replace(tzinfo=timezone.utc)
    footer = ' '.join(section.xpath('following-sibling::div[1]')[0].text_content().split())
    interval = re.search(r'Change from (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) to (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) UTC', footer)
    if not interval or interval[2] != stamp.strftime('%Y-%m-%d %H:%M'):
        raise ValueError('Header and ATM report timestamps disagree')
    return _validate_record({'observation_date': stamp.strftime('%Y-%m-%d'),
                            'observation_timestamp': stamp.isoformat(),
                            'value': float(quote[1])}, now)


def validated_records(payload, now=None):
    if any(payload.get(key) != value for key, value in IDENTITY.items()):
        raise ValueError('Unexpected source/pair/tenor/quote identity')
    records = [_validate_record(row, now) for row in payload.get('records', [])]
    dates = [r['observation_date'] for r in records]
    if dates != sorted(set(dates)):
        raise ValueError('History contains duplicate or unsorted dates')
    return records


def prepare_snapshot(text, previous=None, now=None):
    quote = parse_quote(text, now)
    records = validated_records(previous, now) if previous else []
    if records and quote['observation_timestamp'] < records[-1]['observation_timestamp']:
        raise ValueError('Source would roll back the saved observations')
    merged = {r['observation_date']: r for r in records}
    merged[quote['observation_date']] = quote
    result = [merged[key] for key in sorted(merged)]
    if result == records:
        return None
    return dict(IDENTITY, source_url=SOURCE_URL, updated_at=_now(now).isoformat(),
                coverage_start=result[0]['observation_date'], coverage_end=result[-1]['observation_date'],
                record_count=len(result), records=result)


def load_snapshot(path=SNAPSHOT):
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
        validated_records(payload)
        return payload
    except (OSError, ValueError, TypeError, KeyError, OverflowError):
        return dict(IDENTITY, source_url=SOURCE_URL, records=[])


def build_figure(date_range='5Y', payload=None):
    payload = load_snapshot() if payload is None else payload
    records = validated_records(payload)
    fig = go.Figure()
    if records:
        fig.add_scatter(x=[r['observation_date'] for r in records], y=[r['value'] for r in records],
                        mode='lines+markers', name=SERIES_NAME, marker_size=6,
                        line=dict(color='#d55e00', width=2.4), connectgaps=False,
                        meta={'observation_cadence': 'daily'},
                        customdata=[r['observation_timestamp'] for r in records],
                        hovertemplate='%{y:.2f}%<br>Saxo: %{customdata}<extra></extra>')
    fig.update_layout(yaxis_title='3M ATM 隐含波动率 · 年化%',
                      meta={'missing_series': [] if records else [SERIES_NAME]})
    return apply_time_axis(fig, date_range) if records else fig
