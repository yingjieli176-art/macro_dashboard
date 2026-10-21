"""Compare repository observations against independently fetched source dates.

An outage remains unverified; a successful job is not proof of source freshness.
No observations are changed by this audit.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from functools import lru_cache
import io
import json
from pathlib import Path
import sys
from urllib.parse import quote

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from macro_platform.market_history import completed_daily_closes


def get(url, **kwargs):
    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0 MacroDashboard/1.0"},
                            timeout=(12, 25), **kwargs)
    response.raise_for_status()
    return response


def latest(frame, date, value):
    dates = pd.to_datetime(frame[date], errors="coerce")
    if date == "end_of_month":
        dates = dates + pd.offsets.MonthEnd(0)
    values = pd.to_numeric(frame[value], errors="coerce")
    valid = dates.notna() & values.notna() & values.abs().lt(float("inf"))
    return dates.loc[valid].max().strftime("%Y-%m-%d") if valid.any() else None


def snapshot(filename, date, value, symbol=None):
    try:
        data = json.loads((ROOT / "data_snapshots" / filename).read_text())
        if symbol:
            data = data["series"][symbol]
        frame = pd.DataFrame(data["records"])
        result = latest(frame, date, value)
        return result
    except (OSError, ValueError, KeyError, TypeError):
        return None


def fred(symbol):
    from scripts.sync_fred_verified_cache import CBOE_FILES, TREASURY_FIELDS
    if symbol in CBOE_FILES:
        name = CBOE_FILES[symbol].removesuffix("_History.csv")
        return cboe(name)
    if symbol in TREASURY_FIELDS:
        import xml.etree.ElementTree as ET
        kind = "daily_treasury_real_yield_curve" if symbol.startswith("DFII") else "daily_treasury_yield_curve"
        url = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"
        raw = get(url,params={"data":kind,"field_tdr_date_value":datetime.now(timezone.utc).year}).text
        ns={"a":"http://www.w3.org/2005/Atom","m":"http://schemas.microsoft.com/ado/2007/08/dataservices/metadata"}
        records=[]
        for entry in ET.fromstring(raw).findall("a:entry",ns):
            node=entry.find("a:content/m:properties",ns)
            if node is not None:
                records.append({child.tag.rsplit("}",1)[-1]:child.text for child in node})
        return latest(pd.DataFrame(records),"NEW_DATE",TREASURY_FIELDS[symbol]),url
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv"
    frame = pd.read_csv(io.StringIO(get(url, params={"id": symbol}).text))
    return latest(frame, frame.columns[0], symbol), url + "?id=" + symbol


def yahoo(symbol):
    if symbol == "HSTECH":
        from scripts.update_hk_market_daily import _fetch_hstech
        frame = _fetch_hstech()
        return latest(frame, "observation_date", "close"), "https://stock.finance.sina.com.cn/hkstock/history/HSTECH.html"
    url = "https://query1.finance.yahoo.com/v8/finance/chart/" + quote(symbol, safe="")
    node = get(url, params={"range": "1mo", "interval": "1d"}).json()["chart"]["result"][0]
    frame = completed_daily_closes(node)
    return latest(frame, "observation_date", "close"), url


def cboe(symbol):
    url = f"https://cdn.cboe.com/api/global/us_indices/daily_prices/{symbol}_History.csv"
    frame = pd.read_csv(io.StringIO(get(url).text))
    value = "CLOSE" if "CLOSE" in frame else symbol
    return latest(frame, "DATE", value), url


@lru_cache(maxsize=12)
def hkma_table(endpoint, date):
    url = "https://api.hkma.gov.hk/public/market-data-and-statistics/" + endpoint
    from scripts.update_hkma_snapshot import _fetch_proxy_records
    rows = _fetch_proxy_records(url, {"pagesize": 15, "sortby": date, "sortorder": "desc"})
    return pd.DataFrame(rows), url


def hkma(endpoint, value, date):
    frame, url = hkma_table(endpoint, date)
    return latest(frame, date, value), url


def asia(country, value):
    from macro_platform.asia_rates import load_china_gov_yields, load_japan_gov_yields, JAPAN_CURRENT_URL, CHINA_TREASURY_URL
    if country == "china":
        params={"type":"RPTA_WEB_TREASURYYIELD","sty":"ALL","st":"SOLAR_DATE","sr":"-1",
                "token":"894050c76af8597a853f5b408b759f5d","p":1,"ps":10,"pageNo":1,"pageNum":1}
        rows=get(CHINA_TREASURY_URL,params=params).json()["result"]["data"]
        return latest(pd.DataFrame(rows),"SOLAR_DATE",{"china_2y":"EMM00588704","china_10y":"EMM00166466"}[value]),CHINA_TREASURY_URL
    frame = load_japan_gov_yields() if country == "japan" else load_china_gov_yields()
    return latest(frame, "observation_date", value), JAPAN_CURRENT_URL if country == "japan" else CHINA_TREASURY_URL


def hibor(field):
    from scripts.update_hkma_daily_snapshot import HKAB_URL, parse_hkab_latest
    row = parse_hkab_latest(get(HKAB_URL).text)
    return row["end_of_date"] if row.get(field) is not None else None, HKAB_URL


def tga():
    from scripts.sync_tga_daily_snapshot import fetch_latest_official, ENDPOINT
    _, frame = fetch_latest_official(requests.Session())
    return latest(frame, "observation_date", "TGA_DAILY"), ENDPOINT


def cme():
    from scripts.update_copper_snapshot import _fetch_cme_stocks, CME_STOCKS_URL
    return _fetch_cme_stocks()["date"], CME_STOCKS_URL


def lme(value):
    from scripts.update_copper_snapshot import _fetch_westmetall_year, WESTMETALL_URL
    frame = _fetch_westmetall_year(datetime.now().year)
    return latest(frame, "date", value), WESTMETALL_URL.format(year=datetime.now().year)


def jobs():
    output = []
    def add(key, charts, cadence, stored, fetch):
        output.append((key, charts, cadence, stored, fetch))
    for symbol, charts in {
        "IORB": [1], "RRPONTSYAWARD": [1], "EFFR": [1], "SOFR": [1],
        "DGS3MO": [3], "DGS2": [3], "DGS10": [2,3], "DFII5": [2,13], "DFII10": [2], "T10YIE": [2],
        "WALCL": [4], "WRESBAL": [4], "RRPONTSYD": [4], "VIXCLS": [9], "VXVCLS": [9], "SP500": [9], "GVZCLS": [10],
    }.items():
        add(symbol, charts, "weekly" if symbol in ("WALCL", "WRESBAL") else "daily",
            snapshot(f"fred_cache/{symbol}.json", "date", "value"), lambda symbol=symbol: fred(symbol))
    for symbol, charts, filename, field in (
        ("HKD=X", [8], "usdhkd_daily.json", "value"), ("JPY=X", [14], "jpy_market_daily.json", "usd_jpy_close"),
        ("0700.HK", [5,8], "hk_market_daily.json", "close"), ("0388.HK", [5,8], "hk_market_daily.json", "close"),
        ("^HSI", [5,8], "hk_market_daily.json", "close"), ("HSTECH", [5,8], "hk_market_daily.json", "close"),
        ("GC=F", [10], None, "close"), ("SI=F", [10], None, "close"),
        ("BTC-USD", [11], None, "close"), ("ETH-USD", [11], None, "close"),
        ("^N225", [14], None, "close"), ("HG=F", [12], "copper_market_daily.json", "comex_price_usd_lb"),
    ):
        key = "date" if filename in ("jpy_market_daily.json", "copper_market_daily.json") else "observation_date"
        stored = snapshot(filename, key, field, symbol if filename == "hk_market_daily.json" else None) if filename else None
        add(symbol, charts, "daily", stored, lambda symbol=symbol: yahoo(symbol))
    for symbol in ("VIXEQ", "COR1M", "COR3M"):
        add(symbol, [9], "daily", snapshot(f"{symbol.lower()}_daily.json", "observation_date", "close"), lambda symbol=symbol: cboe(symbol))
    for field, charts in (("m2_hkd", [5]), ("m3_hkd", [5])):
        add(field, charts, "monthly", snapshot("censtat_hkd_money_supply.json", "end_of_month", field),
            lambda field=field: hkma("monthly-statistical-bulletin/financial/monetary-statistics", field, "end_of_month"))
    for field in ("aggr_balance_bf_disc_win", "outstanding_efbn", "ow_lb_bf_disc_win", "mb_bf_disc_win_total"):
        saved = {"aggr_balance_bf_disc_win": "aggr_balance", "mb_bf_disc_win_total": "monetary_base_total"}.get(field, field)
        add(field, [5,6], "monthly", snapshot("hkma_monetary_statistics.json", "end_of_month", saved),
            lambda field=field: hkma("monthly-statistical-bulletin/monetary-operation/monetary-base-endperiod", field, "end_of_month"))
    for field in ("hibor_overnight", "hibor_3m", "disc_win_base_rate", "closing_balance"):
        add(field, [7], "daily", snapshot("hkma_banking_liquidity_daily.json", "end_of_date", field),
            (lambda field=field: hibor(field)) if field.startswith("hibor_") else
            (lambda field=field: hkma("daily-monetary-statistics/daily-figures-interbank-liquidity", field, "end_of_date")))
    for country, chart in (("china", 13), ("japan", 14)):
        for tenor in ("2y", "10y"):
            key = f"{country}_{tenor}"
            add(key, [chart], "daily", None, lambda country=country,key=key: asia(country,key))
    from macro_platform.treasury_cash import read_verified_tga_snapshot
    saved_tga = read_verified_tga_snapshot(ROOT / "data_snapshots/treasury_tga_daily.json")
    add("TGA_DAILY", [4], "daily", latest(saved_tga, "observation_date", "TGA_DAILY"), tga)
    add("comex_stock_t", [12], "daily", snapshot("copper_market_daily.json", "date", "comex_stock_t"), cme)
    for field in ("lme_stock_t", "lme_3m_usd_t"):
        add(field, [12], "daily", snapshot("copper_market_daily.json", "date", field), lambda field=field: lme(field))
    return output


def check(job):
    key, charts, cadence, stored, fetch = job
    row = {"id": key, "charts": charts, "cadence": cadence, "repository_latest": stored,
           "checked_at": datetime.now(timezone.utc).isoformat()}
    try:
        source, url = fetch()
        row.update({"source_latest": source, "source_url": url})
        row["status"] = ("unverified" if source is None else "live_only" if stored is None else
                         "pipeline_lag" if source > stored else "source_behind_repository" if source < stored else "at_source_latest")
    except Exception as error:
        row.update({"source_latest": None, "status": "unverified", "error": type(error).__name__ + ": " + str(error)[:220]})
    if row.get("source_latest") is None and row.get("status") != "unverified":
        row["status"] = "unverified"
    return row


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="all_source_freshness.json")
    parser.add_argument("--retry-from")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    rows = json.loads(Path(args.retry_from).read_text())["sources"] if args.retry_from else []
    retry = {row["id"] for row in rows if row["status"] in ("unverified", "source_behind_repository")}
    rows = [row for row in rows if row["id"] not in retry]
    with ThreadPoolExecutor(max_workers=6) as pool:
        tasks = [pool.submit(check, job) for job in jobs() if not args.retry_from or job[0] in retry]
        for future in as_completed(tasks):
            row = future.result(); rows.append(row)
            print(row["id"], row["repository_latest"], "->", row["source_latest"], row["status"], flush=True)
    payload = {"checked_at": datetime.now(timezone.utc).isoformat(), "sources": sorted(rows,key=lambda r:r["id"])}
    Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    from collections import Counter
    counts = dict(Counter(row["status"] for row in rows))
    print("SOURCE CHECK SUMMARY", counts)
    if args.strict and any(row["status"] in ("unverified", "pipeline_lag") for row in rows):
        raise SystemExit("Some sources are unverified or ahead of repository data; see the saved report")


if __name__ == "__main__":
    main()
