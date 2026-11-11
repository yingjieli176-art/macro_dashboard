"""Collect official BOJ settings/TONA and JSDA T+0 repo, independently."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from io import BytesIO
import html
import json
from pathlib import Path
import re
import sys
from urllib.parse import urljoin
from zoneinfo import ZoneInfo
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from macro_platform.japan_corridor import SNAPSHOT, load_payload

BOJ_API = 'https://www.stat-search.boj.or.jp/api/v1/getDataCode'
HOME = 'https://www.boj.or.jp/en/'
TONA_PAGE = 'https://www.boj.or.jp/en/statistics/market/short/mutan/index.htm'
REPO_URL = 'https://www.jsda.or.jp/shiryoshitsu/toukei/trr/files/trrts.xls'
# Published effective-date history; no negative-rate tier is treated as a floor.
DEPOSIT_EVENTS = [
 ('2024-03-21', .1, 'https://www.boj.or.jp/en/mopo/mpmdeci/state_2024/k240319a.htm'),
 ('2024-08-01', .25, 'https://www.boj.or.jp/en/mopo/mpmdeci/state_2024/k240731a.htm'),
 ('2025-01-27', .5, 'https://www.boj.or.jp/en/mopo/mpmdeci/state_2025/k250124a.htm'),
 ('2025-12-22', .75, 'https://www.boj.or.jp/en/mopo/mpmdeci/state_2025/k251219a.htm'),
 ('2026-06-17', 1., 'https://www.boj.or.jp/en/mopo/mpmdeci/mpr_2026/k260616a.pdf'),
 ('2026-09-24', 1.25, 'https://www.boj.or.jp/en/mopo/mpmsche_minu/minu_2026/g260918.pdf'),
]


def get(url, **kwargs):
    response = requests.get(url, timeout=(8, 30), headers={'User-Agent': 'MacroDashboard/1.0'}, **kwargs)
    response.raise_for_status()
    return response


def parse_api(payload, code):
    if payload.get('STATUS') != 200 or payload.get('NEXTPOSITION'):
        raise ValueError('Incomplete BOJ response')
    nodes = [n for n in payload.get('RESULTSET',[]) if n.get('SERIES_CODE') == code]
    if len(nodes) != 1 or nodes[0].get('FREQUENCY') != 'DAILY' or 'percent' not in nodes[0].get('UNIT','').lower():
        raise ValueError('Unexpected BOJ series identity or units')
    values = nodes[0]['VALUES']; dates, rates = values['SURVEY_DATES'], values['VALUES']
    if len(dates) != len(rates): raise ValueError('BOJ length mismatch')
    rows = [{'date': pd.to_datetime(str(d),format='%Y%m%d').strftime('%Y-%m-%d'), 'value': float(v)}
            for d,v in zip(dates,rates) if v is not None]
    return validate_rows(rows)


def validate_rows(rows):
    if not rows: raise ValueError('No published observations')
    f = pd.DataFrame(rows); d = pd.to_datetime(f.date,errors='raise')
    today = pd.Timestamp.now(tz='Asia/Tokyo').tz_localize(None).normalize()
    if not d.is_unique or not d.is_monotonic_increasing or d.max()>today or not f.value.between(-5,20).all():
        raise ValueError('Invalid/future/duplicate rate observations')
    return rows


def fetch_boj(code, db):
    return parse_api(get(BOJ_API,params={'format':'json','lang':'en','db':db,'code':code,'startDate':'202101'}).json(),code)


def fetch_admin():
    text = html.unescape(re.sub('<[^>]+>',' ',get(HOME).text))
    text = re.sub(r'\s+',' ',text)
    output = {}
    for key,label in [('deposit','Interest Rate Applied to the Complementary Deposit Facility'),('loan','Basic Loan Rate')]:
        match = re.search(re.escape(label)+r'\s+(-?\d+(?:\.\d+)?)\s*%\s+since\s+([A-Z][a-z]+ \d{1,2}, \d{4})',text)
        if match is None: raise ValueError('BOJ effective-date setting not found: '+key)
        output[key] = {'date': pd.Timestamp(match[2]).strftime('%Y-%m-%d'), 'value': float(match[1])}
        validate_rows([output[key]])
    return output


def parse_repo(content):
    frame = pd.read_excel(BytesIO(content), header=None)
    header = next((i for i in range(min(20,len(frame))) if str(frame.iloc[i,1]).strip()=='T+0' and str(frame.iloc[i,2]).strip()=='T+1'),None)
    if header is None or 'overnight' not in str(frame.iloc[header-1,1]).lower():
        raise ValueError('JSDA overnight T+0 schema changed')
    data = frame.iloc[header+1:,:2].copy(); data.columns=['date','value']
    data['date'] = pd.to_datetime(data.date,errors='coerce'); data['value']=pd.to_numeric(data.value,errors='coerce')
    data=data.dropna().loc[lambda f:f.date.ge('2021-01-01')].sort_values('date')
    if len(data)<700 or data.date.dt.dayofweek.ge(5).any(): raise ValueError('JSDA history incomplete')
    return validate_rows([{'date':r.date.strftime('%Y-%m-%d'),'value':float(r.value)} for r in data.itertuples()])


def fetch_tona_recent():
    text = get(TONA_PAGE).text
    links = re.findall(r'href="([^"]+/d_release/(?:mp/|md/\d{4}/)(?:mp|md)\d{8}\.xlsx)"',text)
    candidates = sorted(set(links),key=lambda x:(re.search(r'(\d{8})\.xlsx',x)[1], '/md/' in x),reverse=True)[:3]
    rows = {}
    for relative in candidates:
        try:
            url=urljoin(TONA_PAGE,relative); frame=pd.read_excel(BytesIO(get(url).content),header=None)
            day=pd.to_datetime(re.search(r'(\d{8})\.xlsx',relative)[1],format='%Y%m%d').strftime('%Y-%m-%d')
            title=' '.join(str(v) for v in frame.to_numpy().ravel() if pd.notna(v))
            if 'Uncollateralized Overnight Call Rate' not in title: raise ValueError('Wrong TONA workbook')
            row=next(row for row in frame.itertuples(index=False,name=None) if any('Average' in str(v) for v in row))
            index=next(i for i,v in enumerate(row) if 'Average' in str(v))
            value=float(row[index+1]); validate_rows([{'date':day,'value':value}])
            if day not in rows or '/md/' in relative:
                rows[day]={'date':day,'value':value,'status':'确报' if '/md/' in relative else '速報','source_url':url}
        except Exception as exc:
            print('TONA daily supplement unavailable:',type(exc).__name__,flush=True)
    return [rows[d] for d in sorted(rows)]


def merge_node(old, rows, **metadata):
    validate_rows(rows)
    previous=old.get('records',[])
    if previous and rows[-1]['date'] < previous[-1]['date']: raise ValueError('Source moved backwards')
    merged={r['date']:r for r in previous}; merged.update({r['date']:r for r in rows})
    return dict(old, **metadata, records=[merged[d] for d in sorted(merged)])


def collect(previous=None):
    previous=load_payload() if previous is None else previous
    output=dict(previous); output['series']=dict(previous.get('series',{})); errors={}
    now=datetime.now(ZoneInfo('Asia/Tokyo')); today=now.date().isoformat()
    jobs={'loan':lambda:fetch_boj('MADR1Z@D','IR01'),'tona':lambda:fetch_boj('STRDCLUCON','FM01'),
          'repo':lambda:parse_repo(get(REPO_URL).content),'admin':fetch_admin,'tona_recent':fetch_tona_recent}
    results={}
    with ThreadPoolExecutor(max_workers=3) as pool:
        tasks={pool.submit(f):key for key,f in jobs.items()}
        for future in as_completed(tasks):
            key=tasks[future]
            try: results[key]=future.result()
            except Exception as exc: errors[key]=type(exc).__name__
    for key in ('loan','tona','repo'):
        if key not in results: continue
        try:
            old=output['series'].get(key,{})
            output['series'][key]=merge_node(old,results[key],source_url=REPO_URL if key=='repo' else BOJ_API,
                                            latest_status='确报' if key=='tona' else '已公布')
        except Exception as exc: errors[key]=type(exc).__name__
    if results.get('tona_recent'):
        old=output['series'].get('tona',{})
        allrows={r['date']:r for r in old.get('records',[])}
        for row in results['tona_recent']: allrows[row['date']]={'date':row['date'],'value':row['value']}
        if allrows:
            last=max(results['tona_recent'],key=lambda r:r['date'])
            output['series']['tona']=merge_node(old,[allrows[d] for d in sorted(allrows)],source_url=last['source_url'],latest_status=last['status'])
            # The time-series API normally trails the daily release. A
            # validated fresh workbook resolves that expected API lag.
            if last['date'] >= output['series']['tona']['records'][-1]['date']:
                errors.pop('tona', None)
    if 'admin' in results:
        for key, current in results['admin'].items():
            rows=[{'date':d,'value':v,'source_url':url} for d,v,url in DEPOSIT_EVENTS] if key=='deposit' else []
            rows=[r for r in rows if r['date']<=today]
            known={r['date']:r for r in output['series'].get(key,{}).get('records',[])}
            known.update({r['date']:r for r in rows}); known[current['date']]=current
            output['series'][key]=merge_node(output['series'].get(key,{}),[known[d] for d in sorted(known)],
                                            source_url=HOME,verified_through=today,latest_status='政策设定已核实')
    output.update(schema='japan_corridor_v1', checked_at=now.isoformat(), collector_errors=errors,
        methodology={'deposit':'2024-03-21起单一超额准备金付息基准；此前分层制度不绘制统一下沿',
                     'repo':'JSDA Tokyo Repo Rate，隔夜T+0参考报价截尾均值；不是成交加权均值',
                     'clf_usage':'未核实新增执行额与净变化的完整历史口径，不以零或净变化代替实际用量'})
    return output, errors


def main():
    previous=load_payload(); output,errors=collect(previous)
    # Persist each successful family even when another publisher is down.
    if output.get('series') != previous.get('series') or output.get('collector_errors') != previous.get('collector_errors'):
        temporary=SNAPSHOT.with_suffix('.json.tmp');temporary.write_text(json.dumps(output,ensure_ascii=False,separators=(',',':'))+'\n');temporary.replace(SNAPSHOT)
    for key,node in output.get('series',{}).items(): print(key,len(node['records']),node['records'][-1],node.get('verified_through'),flush=True)
    if errors: raise SystemExit('Some sources failed; last-good history retained: '+str(errors))


if __name__=='__main__': main()
