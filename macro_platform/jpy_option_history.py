"""Original QCAM monthly implied-volatility quotes; never inferred daily ATM."""
from datetime import datetime
import hashlib
import io
import json
import math
from pathlib import Path
import re

import pandas as pd
import plotly.graph_objects as go

from macro_platform.chart_axes import apply_time_axis

SNAPSHOT = Path(__file__).resolve().parents[1] / 'data_snapshots/jpy_implied_qcam_monthly.json'
INDEX_URL = 'https://q-cam.com/wp-json/wp/v2/media'
SOURCE_URL = 'https://q-cam.com/news-publications/'
SERIES_NAME = 'USD/JPY 3M 市场隐含波动率（QCAM月度，R5）'
IDENTITY = dict(symbol='USDJPY_3M_IV_QCAM', source='QCAM Currency Asset Management',
                pair='USDJPY', tenor='3M', quote_type='market_implied_unspecified_moneyness',
                unit='percent', frequency='monthly')
MONTHS = {datetime(2000, n, 1).strftime('%B'): n for n in range(1, 13)}
REPORT_PATTERN = re.compile(r'https://q-cam\.com/wp-content/uploads/\d{4}/\d{2}/QCAM-MONTHLY-('
                            + '|'.join(MONTHS) + r')-(20\d{2})(?:-\d+)?\.pdf')


def report_month(url):
    match = REPORT_PATTERN.fullmatch(url)
    if not match:
        raise ValueError('Not a QCAM monthly report URL')
    return f'{match[2]}-{MONTHS[match[1]]:02d}'


def parse_page(text, source_url, page_number, now=None):
    if not re.search(r'Market\s+implied\s+3-month\s+volatility\s*\(annualised\)', text):
        raise ValueError('Three-month market-implied definition missing')
    if 'Historical Volatility' not in text or 'Implied Volatility' not in text:
        raise ValueError('Expected separate realized/implied table headers')
    dates = re.findall(r'as of\s+([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?[,]?\s+(20\d{2})', text)
    if len(set(dates)) != 1:
        raise ValueError('Missing or ambiguous table observation date')
    month, day, year = dates[0]
    date = pd.Timestamp(int(year), MONTHS[month], int(day))
    today = pd.Timestamp.now(tz='UTC').tz_localize(None).normalize() if now is None else pd.Timestamp(now)
    if today.tzinfo:
        today = today.tz_convert('UTC').tz_localize(None)
    issue = report_month(source_url)
    issue_date = pd.Timestamp(issue + '-01')
    if date > today or not issue_date-pd.Timedelta(days=10) <= date <= issue_date+pd.Timedelta(days=30):
        raise ValueError(f'Future or mismatched report observation date: {source_url}, {date.date()}')
    rows = re.findall(r'\bUSDJPY\b(.*?)\bGBPUSD\b', text, re.S)
    if len(rows) != 1:
        raise ValueError('Missing or ambiguous USDJPY row')
    values = re.findall(r'(-?\d+(?:\.\d+)?)\s*%', rows[0])
    if len(values) != 8:
        raise ValueError('Expected four realized and four implied columns')
    # Current, 1M-ago, 12M-ago, 5Y average: only the CURRENT implied column
    # is dated by the table's explicit as-of date. Do not manufacture dates
    # for the lookback columns or take the realized-volatility column.
    value = float(values[4])
    if not math.isfinite(value) or not 0 < value < 100:
        raise ValueError('Invalid implied-volatility percentage')
    return dict(observation_date=date.strftime('%Y-%m-%d'), value=value,
                issue_month=issue, source_url=source_url, source_page=page_number)


def parse_pdf(content, source_url, now=None):
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(content))
    candidates = []
    for number, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ''
        if re.search(r'Market\s+implied\s+3-month', text):
            candidates.append(parse_page(text, source_url, number, now))
    if len(candidates) != 1:
        raise ValueError('Expected exactly one FX volatility table')
    return dict(candidates[0], source_sha256=hashlib.sha256(content).hexdigest())


def discover_reports(get, *, backfill=False):
    reports = {}
    for page in (1, 2) if backfill else (1,):
        response = get(INDEX_URL, params={'search':'QCAM-MONTHLY', 'per_page':100,
                       'page':page, '_fields':'source_url,date', 'after':'2022-01-01T00:00:00'})
        response.raise_for_status()
        for node in response.json():
            url = node.get('source_url', '')
            if REPORT_PATTERN.fullmatch(url):
                # WordPress lists newest attachments first, including corrected editions.
                month = report_month(url)
                expected_path = '/uploads/' + month.replace('-', '/') + '/'
                if month not in reports or (expected_path in url and expected_path not in reports[month]):
                    reports[month] = url
    if not reports:
        raise ValueError('QCAM report index contains no monthly reports')
    return reports


def validated_records(payload, now=None):
    if any(payload.get(k) != v for k, v in IDENTITY.items()):
        raise ValueError('Wrong QCAM series identity')
    today = pd.Timestamp.now(tz='UTC').date() if now is None else pd.Timestamp(now).date()
    rows = payload.get('records', [])
    dates, issues = [], []
    for row in rows:
        date = pd.Timestamp(row['observation_date'])
        value = row['value']
        issue_date = pd.Timestamp(row['issue_month']+'-01')
        if (date.strftime('%Y-%m-%d') != row['observation_date'] or date.date() > today
                or not issue_date-pd.Timedelta(days=10) <= date <= issue_date+pd.Timedelta(days=30)
                or isinstance(value, bool) or not math.isfinite(float(value))
                or not 0 < float(value) < 100 or report_month(row['source_url']) != row['issue_month']
                or not re.fullmatch(r'[a-f0-9]{64}', row['source_sha256'])
                or type(row['source_page']) is not int or row['source_page'] < 1):
            raise ValueError('Invalid QCAM observation/provenance')
        dates.append(row['observation_date']); issues.append(row['issue_month'])
    if dates != sorted(set(dates)) or len(set(issues)) != len(issues):
        raise ValueError('Duplicate or unsorted QCAM history')
    return rows


def load_snapshot(path=SNAPSHOT):
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
        validated_records(payload)
        return payload
    except (OSError, ValueError, TypeError, KeyError):
        return dict(IDENTITY, records=[])


def build_figure(date_range='5Y', payload=None):
    rows = validated_records(load_snapshot() if payload is None else payload)
    figure = go.Figure()
    if rows:
        figure.add_scatter(x=[r['observation_date'] for r in rows], y=[r['value'] for r in rows],
            name=SERIES_NAME, mode='lines+markers', line=dict(color='#0d9488', width=2.6),
            marker_size=5, connectgaps=False, meta={'observation_cadence':'monthly',
                'publication_schedule':'qcam_monthly', 'publication_month':rows[-1]['issue_month']},
            hovertemplate='QCAM月度: %{y:.2f}%<extra></extra>')
    figure.update_layout(yaxis_title='隐含波动率 · 年化%', meta={'missing_series':[] if rows else [SERIES_NAME]})
    return apply_time_axis(figure, date_range) if rows else figure
