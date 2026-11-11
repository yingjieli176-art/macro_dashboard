"""Japan administered-rate references and observed overnight funding rates."""
from datetime import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
import plotly.graph_objects as go
from macro_platform.chart_axes import apply_time_axis, RANGE_OFFSETS

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / 'data_snapshots/japan_corridor.json'
REGIME_START = '2024-03-21'
SERIES = {
    'deposit': ('BOJ 补充存款利率（下沿参考）', '#2563eb'),
    'loan': ('BOJ 基本贷款利率（上沿参考）', '#dc2626'),
    'tona': ('TONA 无担保隔夜利率', '#059669'),
    'repo': ('Tokyo Repo 隔夜 T+0（参考报价）', '#9333ea'),
}


def load_payload(path=SNAPSHOT):
    try:
        payload = json.loads(Path(path).read_text())
        if payload.get('schema') != 'japan_corridor_v1':
            raise ValueError('Unexpected corridor schema')
        return payload
    except (OSError, ValueError, TypeError):
        return {'schema': 'japan_corridor_v1', 'series': {}}


def series_frame(payload, key, now=None):
    node = payload.get('series', {}).get(key, {})
    frame = pd.DataFrame(node.get('records', []), columns=['date', 'value'])
    frame['date'] = pd.to_datetime(frame.date, errors='coerce')
    frame['value'] = pd.to_numeric(frame.value, errors='coerce')
    clock = pd.Timestamp.now(tz='Asia/Tokyo') if now is None else pd.Timestamp(now)
    today = clock.tz_convert('Asia/Tokyo').tz_localize(None).normalize() if clock.tzinfo else clock.normalize()
    frame = frame.loc[frame.date.notna() & frame.date.le(today) & frame.value.between(-5, 20)]
    frame = frame.sort_values('date').drop_duplicates('date', keep='last')
    if key == 'deposit':
        frame = frame.loc[frame.date.ge(REGIME_START)]
    if key in ('deposit', 'loan') and not frame.empty:
        # Only extend an announced policy setting through the date on which
        # the publisher confirmed it. Never forward-fill market observations.
        verified = pd.Timestamp(node.get('verified_through', frame.date.max()))
        end = min(today, verified)
        if frame.date.max() < end:
            frame = pd.concat([frame, pd.DataFrame({'date': [end], 'value': [frame.value.iloc[-1]]})], ignore_index=True)
    return frame


def build_corridor_figure(date_range='5Y', payload=None, now=None):
    payload = load_payload() if payload is None else payload
    frames = {key: series_frame(payload, key, now) for key in SERIES}
    last = max((f.date.max() for f in frames.values() if not f.empty), default=pd.Timestamp.today().normalize())
    start = last - RANGE_OFFSETS.get(date_range, RANGE_OFFSETS['1Y'])
    fig = go.Figure()
    missing = []
    for key, (name, color) in SERIES.items():
        frame = frames[key]
        if frame.empty:
            missing.append(name); continue
        if key in ('deposit', 'loan'):
            # Keep one carry-in setting for correct client/server range cuts.
            before = frame.loc[frame.date.lt(start)].tail(1)
            frame = pd.concat([before, frame.loc[frame.date.ge(start)]])
        else:
            frame = frame.loc[frame.date.ge(start)]
        fig.add_trace(go.Scatter(x=list(frame.date), y=list(frame.value), name=name,
            mode='lines', connectgaps=False,
            line=dict(color=color, width=2.6 if key in ('deposit', 'loan') else 2.2,
                      shape='hv' if key in ('deposit', 'loan') else 'linear',
                      dash='dot' if key == 'repo' else 'solid'),
            hovertemplate='%{x|%Y-%m-%d}<br>%{y:.3f}%<extra>%{fullData.name}</extra>'))
    fig.update_layout(template='plotly_white', height=420, hovermode='x unified',
        yaxis=dict(title='年化利率 · %', ticksuffix='%', fixedrange=True),
        margin=dict(l=55,r=30,t=65,b=50),
        legend=dict(orientation='h', y=1.12, x=0),
        meta={'missing_series': missing, 'corridor_reference_only': True})
    return apply_time_axis(fig, date_range)


def latest_rows(payload=None):
    payload = load_payload() if payload is None else payload
    rows = []
    for key, (name, _) in SERIES.items():
        frame = series_frame(payload, key)
        node = payload.get('series', {}).get(key, {})
        rows.append({'指标': name, '最新值（%）': None if frame.empty else float(frame.value.iloc[-1]),
                     '数据日期': '缺失' if frame.empty else frame.date.max().strftime('%Y-%m-%d'),
                     '口径': '央行设定，按生效日延续' if key in ('deposit','loan') else
                              ('成交量加权均值' if key == 'tona' else 'JSDA参考机构报价截尾均值'),
                     '状态': node.get('latest_status', '已公布')})
    return rows
