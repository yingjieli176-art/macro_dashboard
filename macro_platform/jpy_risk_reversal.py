"""Saxo USD call minus USD put, one-month 25-delta risk reversal."""
import json
from pathlib import Path
import plotly.graph_objects as go

from macro_platform.chart_axes import apply_time_axis
from macro_platform.jpy_implied_vol import SOURCE_URL, _now, _validate_record, parse_quote as parse_saxo

SNAPSHOT = Path(__file__).resolve().parents[1] / 'data_snapshots/jpy_1m_25d_rr_saxo.json'
SERIES_NAME = 'USD/JPY 1M 25Δ Risk Reversal（Saxo，R6）'
IDENTITY = dict(symbol='USDJPY_1M_25D_RR_SAXO', source='Saxo Bank', pair='USDJPY', tenor='1M',
                delta=25, quote_type='risk_reversal', convention='USD_call_minus_USD_put',
                unit='volatility_percentage_points')


def parse_quote(text, now=None):
    return parse_saxo(text, now, section_label='25-DELTA RISK REVERSAL', tenor='1m', allow_negative=True)


def validated_records(payload, now=None):
    if any(payload.get(k) != v for k,v in IDENTITY.items()):
        raise ValueError('Wrong risk-reversal pair/tenor/delta/direction')
    rows = [_validate_record(row, now, allow_negative=True) for row in payload.get('records', [])]
    dates = [r['observation_date'] for r in rows]
    if dates != sorted(set(dates)):
        raise ValueError('Duplicate or unsorted risk-reversal observations')
    return rows


def prepare_snapshot(text, previous=None, now=None):
    row = parse_quote(text, now)
    old = validated_records(previous, now) if previous else []
    if old and row['observation_timestamp'] < old[-1]['observation_timestamp']:
        raise ValueError('Risk-reversal source would roll back')
    merged = {r['observation_date']:r for r in old}
    merged[row['observation_date']] = row
    rows = [merged[d] for d in sorted(merged)]
    if rows == old:
        return None
    return dict(IDENTITY, source_url=SOURCE_URL, records=rows, record_count=len(rows),
                coverage_start=rows[0]['observation_date'], coverage_end=rows[-1]['observation_date'],
                updated_at=_now(now).isoformat())


def load_snapshot(path=SNAPSHOT):
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
        validated_records(payload)
        return payload
    except (OSError, ValueError, TypeError, KeyError):
        return dict(IDENTITY, records=[])


def build_figure(date_range='5Y', payload=None):
    rows = validated_records(load_snapshot() if payload is None else payload)
    fig = go.Figure()
    if rows:
        fig.add_scatter(x=[r['observation_date'] for r in rows], y=[r['value'] for r in rows],
            name=SERIES_NAME, mode='lines+markers', marker_size=6,
            line=dict(color='#be185d', width=2.6), connectgaps=False,
            meta={'observation_cadence':'daily'},
            hovertemplate='1M 25Δ RR: %{y:.2f} 个波动率百分点<extra></extra>')
    fig.update_layout(yaxis_title='1M 25Δ RR · pp',meta={'missing_series':[] if rows else [SERIES_NAME]})
    return apply_time_axis(fig,date_range) if rows else fig
