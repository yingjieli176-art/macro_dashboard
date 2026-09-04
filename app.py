import html
import json
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from data import (get_dgs3mo, get_dgs2, get_dgs10, get_dfii10, get_sofr, get_iorb, get_effr, get_rrp_rate, get_sina_news)

st.set_page_config(page_title="Macro Dashboard", page_icon="📊", layout="wide")
EASTMONEY_FOCUS_URL = "https://kuaixun.eastmoney.com/"
EASTMONEY_QUOTE_URL = "https://push2.eastmoney.com/api/qt/stock/get"
EASTMONEY_SEARCH_URL = "https://searchapi.eastmoney.com/api/suggest/get"
EASTMONEY_UT = "bd1d9ddb04089700cf9c27f4f4961f5b"
RANGES = ["5Y", "1Y", "6M", "3M", "1M"]
PLOTLY_CONFIG = {"displayModeBar": False, "scrollZoom": False, "doubleClick": False, "editable": False, "displaylogo": False}
WATCHLIST_PARAM = "watchlist"

st.markdown("""
<style>
.block-container { padding-top: 1.05rem; padding-bottom: 2.5rem; max-width: 1400px; }
html, body, [class*="css"] { font-family: "Noto Sans TC", "Noto Sans CJK TC", "Microsoft JhengHei", "PingFang TC", "Segoe UI", sans-serif; }
.dashboard-title { font-size: 1.9rem; font-weight: 700; letter-spacing: -0.02em; margin-bottom: 0.1rem; }
.section-title { font-size: 1.35rem; font-weight: 650; letter-spacing: -0.01em; margin-top: 0.7rem; margin-bottom: 0.15rem; }
.section-description { color: #6b7280; font-size: 0.86rem; margin-bottom: 0.35rem; }
.mini-description { color: #6b7280; font-size: 0.76rem; line-height: 1.5; margin: 2px 0 8px; }
.source-text { color: #6b7280; font-size: 0.74rem; margin: 3px 0 10px; line-height: 1.45; }
.source-text a { color: #6b7280; text-decoration: none !important; white-space: nowrap; }
.source-text a:hover { color: #374151; text-decoration: underline !important; }
.source-sep { color: #d1d5db; margin: 0 5px; }
.chart-divider { margin: 0.65rem 0 1rem; border-top: 1px solid #e5e7eb; }
.compact-title { font-size: 0.98rem; font-weight: 650; margin-bottom: 0.15rem; }
.compact-description { color: #6b7280; font-size: 0.73rem; line-height: 1.35; margin-bottom: 0.2rem; }
.news-status { color: #6b7280; font-size: 0.75rem; margin-bottom: 0.5rem; }
.news-box { border: 1px solid #e5e7eb; border-radius: 8px; padding: 6px 10px; background: #ffffff; max-height: 650px; overflow-y: auto; }
.news-item { display: flex; align-items: flex-start; padding: 8px 3px; border-bottom: 1px solid #eeeeee; line-height: 1.5; font-size: 0.84rem; }
.news-item:last-child { border-bottom: none; }
.news-index { flex: 0 0 32px; width: 32px; color: #9ca3af; font-size: 0.72rem; font-family: "Segoe UI", sans-serif; padding-top: 2px; }
.news-time { flex: 0 0 72px; width: 72px; color: #6b7280; font-size: 0.72rem; white-space: nowrap; padding-top: 2px; margin-right: 6px; }
.news-content { flex: 1; min-width: 0; }
.news-content a { color: #374151; text-decoration: none !important; }
.market-groups { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 7px; margin-bottom: 0.45rem; }
.market-group { border: 1px solid #e5e7eb; border-radius: 8px; padding: 6px 8px 5px; background: #fff; min-width: 0; }
.market-group-title { color: #374151; font-size: 0.88rem; font-weight: 650; margin-bottom: 5px; }
.market-group-row { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 4px; }
.market-group-row.two { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.market-item { min-width: 0; padding-right: 4px; border-right: 1px solid #f0f0f0; }
.market-item:last-child { border-right: none; }
.market-name { color: #6b7280; font-size: 0.78rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.market-price { color: #111827; font-size: 0.98rem; font-weight: 650; margin-top: 1px; white-space: nowrap; }
.market-change { font-size: 0.76rem; white-space: nowrap; }
.market-meta { color: #9ca3af; font-size: 0.68rem; margin-top: 1px; white-space: nowrap; }
.search-title { color: #374151; font-size: 1.05rem; font-weight: 650; margin: 0.55rem 0 0.3rem; }
.search-result { padding: 7px 5px; margin-top: 4px; border-radius: 6px; }
.search-result-label { color: #374151; font-size: 0.86rem; line-height: 1.4; }
.search-result-symbol { color: #6b7280; font-size: 0.76rem; }
.search-price { color: #111827; font-size: 1.02rem; font-weight: 650; margin-top: 2px; }
.search-after { color: #6b7280; font-size: 0.78rem; margin-top: 3px; }
.search-hint { color: #9ca3af; font-size: 0.76rem; margin-top: 2px; }
.module-delete { display: flex; justify-content: flex-end; margin-top: -1px; margin-right: -2px; }
.module-delete button { min-width: 14px !important; width: 14px !important; height: 14px !important; padding: 0 !important; margin: 0 !important; font-size: 9px !important; line-height: 14px !important; border: 0 !important; }
.module-refresh button { min-height: 30px !important; height: 30px !important; padding: 0 10px !important; font-size: 0.78rem !important; }
@media (max-width: 900px) { .market-groups { grid-template-columns: 1fr; } }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="dashboard-title">Macro Dashboard</div>', unsafe_allow_html=True)

def _load_watchlists():
    if st.session_state.get("_watchlist_loaded"): return
    raw = st.query_params.get(WATCHLIST_PARAM, "")
    try: payload = json.loads(raw) if raw else {}
    except (TypeError, ValueError, json.JSONDecodeError): payload = {}
    if not isinstance(payload, dict): payload = {}
    for key in ("market_search_us", "market_search_hk", "market_search_cn"):
        items = payload.get(key, [])
        if isinstance(items, dict): items = [items]
        if not isinstance(items, list): items = []
        st.session_state[f"{key}_confirmed"] = [item for item in items if isinstance(item, dict) and item.get("symbol")]
    st.session_state["_watchlist_loaded"] = True

def _save_watchlists():
    payload = {}
    for key in ("market_search_us", "market_search_hk", "market_search_cn"):
        items = st.session_state.get(f"{key}_confirmed", [])
        if isinstance(items, dict): items = [items]
        if not isinstance(items, list): items = []
        payload[key] = [item for item in items if isinstance(item, dict) and item.get("symbol")]
    st.query_params[WATCHLIST_PARAM] = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
_load_watchlists()

def _empty_quote():
    return {"price": None, "change_pct": None, "market_state": "", "currency": "", "post_price": None, "post_change_pct": None, "pre_price": None, "pre_change_pct": None, "overnight_price": None, "overnight_change_pct": None, "regular_market_time": None, "post_market_time": None, "pre_market_time": None, "quote_source": "", "delayed_by": None, "data_source": ""}

def _yahoo_raw_value(value):
    if isinstance(value, dict): return value.get("raw") if value.get("raw") is not None else value.get("fmt")
    return value

@st.cache_data(ttl=60, show_spinner=False)
def _get_yahoo_overnight_safe(symbol):
    if not symbol or "." in str(symbol) or str(symbol).startswith("^"): return None, None
    try:
        session = requests.Session(); headers = {"User-Agent": "Mozilla/5.0"}
        session.get("https://fc.yahoo.com", headers=headers, timeout=4)
        crumb = session.get("https://query1.finance.yahoo.com/v1/test/getcrumb", headers=headers, timeout=4).text.strip()
        if not crumb or crumb.startswith("{"): return None, None
        response = session.get(f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{symbol}", params={"formatted": "true", "modules": "price", "overnightPrice": "true", "lang": "en-US", "region": "US", "crumb": crumb}, headers=headers, timeout=5)
        response.raise_for_status(); payload = response.json(); result = ((payload.get("quoteSummary") or {}).get("result") or [None])[0] or {}; price = result.get("price") or {}
        return _yahoo_raw_value(price.get("overnightPrice")), _yahoo_raw_value(price.get("overnightChangePercent"))
    except Exception: return None, None

def _get_yahoo_quote_safe(symbol):
    try:
        response = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/" + symbol, params={"range": "1d", "interval": "5m", "includePrePost": "true"}, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        response.raise_for_status(); result = (response.json().get("chart", {}).get("result") or [])[0]; meta = result.get("meta", {})
        previous = meta.get("previousClose") or meta.get("regularMarketPreviousClose"); price = meta.get("regularMarketPrice"); pre_price = meta.get("preMarketPrice"); post_price = meta.get("postMarketPrice")
        regular_change_pct = meta.get("regularMarketChangePercent"); post_change_pct = meta.get("postMarketChangePercent"); pre_change_pct = meta.get("preMarketChangePercent")
        periods = meta.get("currentTradingPeriod") or {}; pre_period = periods.get("pre") or {}; regular_period = periods.get("regular") or {}; post_period = periods.get("post") or {}
        timestamps = result.get("timestamp") or []; closes = ((result.get("indicators", {}).get("quote") or [{}])[0]).get("close") or []
        def _last_close_in_period(period):
            start, end = period.get("start"), period.get("end")
            if start is None: return None
            candidates = [close for ts, close in zip(timestamps, closes) if close is not None and ts >= start and (end is None or ts <= end)]
            return candidates[-1] if candidates else None
        if price is None: price = _last_close_in_period(regular_period) or next((v for v in reversed(closes) if v is not None), None)
        if pre_price is None: pre_price = _last_close_in_period(pre_period)
        if post_price is None: post_price = _last_close_in_period(post_period)
        if regular_change_pct is None and price is not None and previous not in (None, 0): regular_change_pct = (price - previous) / previous * 100
        if post_change_pct is None and post_price is not None and previous not in (None, 0): post_change_pct = (post_price - previous) / previous * 100
        if pre_change_pct is None and pre_price is not None and previous not in (None, 0): pre_change_pct = (pre_price - previous) / previous * 100
        overnight_price, overnight_change_pct = _get_yahoo_overnight_safe(symbol)
        row = _empty_quote(); row.update({"price": price, "change_pct": regular_change_pct, "market_state": meta.get("marketState", ""), "currency": meta.get("currency", ""), "post_price": post_price, "post_change_pct": post_change_pct, "pre_price": pre_price, "pre_change_pct": pre_change_pct, "overnight_price": overnight_price, "overnight_change_pct": overnight_change_pct, "regular_market_time": meta.get("regularMarketTime"), "post_market_time": meta.get("postMarketTime"), "pre_market_time": meta.get("preMarketTime"), "quote_source": meta.get("quoteSourceName", ""), "delayed_by": meta.get("exchangeDataDelayedBy"), "data_source": "Yahoo Finance"}); return row
    except Exception: return _empty_quote()

def _eastmoney_secid(symbol):
    raw = str(symbol or "").upper().strip()
    if raw.endswith(".SS"): return f"1.{raw[:-3]}"
    if raw.endswith(".SZ"): return f"0.{raw[:-3]}"
    return ""

def _get_eastmoney_quote_safe(symbol):
    secid = _eastmoney_secid(symbol)
    if not secid: return _empty_quote()
    try:
        response = requests.get(EASTMONEY_QUOTE_URL, params={"secid": secid, "fields": "f43,f57,f58,f169,f170,f46,f44,f45,f47,f48,f60,f86", "ut": EASTMONEY_UT, "fltt": "2", "invt": "2"}, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}, timeout=5); response.raise_for_status(); data = (response.json() or {}).get("data") or {}
        if not data: return _empty_quote()
        price_raw, prev_raw, pct_raw = data.get("f43"), data.get("f60"), data.get("f170")
        if price_raw in (None, "-", ""): return _empty_quote()
        price = float(price_raw); previous = None if prev_raw in (None, "-", "") else float(prev_raw)
        if price > 10000: price /= 100
        if previous is not None and previous > 10000: previous /= 100
        change_pct = None if pct_raw in (None, "-", "") else float(pct_raw)
        if change_pct is None and previous not in (None, 0): change_pct = (price - previous) / previous * 100
        return {"price": price, "change_pct": change_pct, "market_state": "REGULAR", "currency": "CNY", "post_price": None, "post_change_pct": None, "pre_price": None, "pre_change_pct": None, "overnight_price": None, "overnight_change_pct": None, "regular_market_time": data.get("f86"), "post_market_time": None, "pre_market_time": None, "quote_source": "Eastmoney", "delayed_by": 0, "data_source": "东方财富"}
    except Exception: return _empty_quote()

def _market_state_text(row): return {"REGULAR": "交易中", "PRE": "盘前", "POST": "盘后", "CLOSED": "休市"}.get(row.get("market_state") or "", "")
def _market_item_html(name, price, change_pct, meta=""):
    price_text = "--" if price is None else f"{price:,.2f}"; change_text = "--" if change_pct is None else f"{change_pct:+.2f}%"
    return f'<div class="market-item"><div class="market-name">{html.escape(name)}</div><div class="market-price">{html.escape(price_text)}</div><div class="market-change">{html.escape(change_text)}</div><div class="market-meta">{html.escape(meta)}</div></div>'

@st.cache_data(ttl=300, show_spinner=False)
def _get_cached_quote(symbol):
    if str(symbol).upper().endswith((".SS", ".SZ")):
        row = _get_eastmoney_quote_safe(symbol)
        if row.get("price") is not None: return row
    return _get_yahoo_quote_safe(symbol)

def _quote_meta(row, market=""):
    source = row.get("data_source") or row.get("quote_source") or ""; delayed = row.get("delayed_by"); state = _market_state_text(row); parts = [state] if state else []
    if delayed not in (None, 0, "0") and source == "Yahoo Finance": parts.append(f"延迟{delayed}分")
    elif source: parts.append(source)
    return " · ".join(parts)

def _refresh_quote_cache():
    _get_cached_quote.clear()
    _get_yahoo_overnight_safe.clear()

@st.fragment(run_every="300s")
def render_market_groups():
    quotes = {"nasdaq": _get_cached_quote("^IXIC"), "sp500": _get_cached_quote("^GSPC"), "dow": _get_cached_quote("^DJI"), "hsi": _get_cached_quote("^HSI"), "hstech": _get_cached_quote("HSTECH.HK"), "sh": _get_cached_quote("000001.SS"), "sz": _get_cached_quote("399001.SZ"), "csi300": _get_cached_quote("000300.SS")}
    groups = [("🇺🇸 美股", [_market_item_html("纳斯达克", quotes["nasdaq"].get("price"), quotes["nasdaq"].get("change_pct"), _quote_meta(quotes["nasdaq"], "US")), _market_item_html("标普500", quotes["sp500"].get("price"), quotes["sp500"].get("change_pct"), _quote_meta(quotes["sp500"], "US")), _market_item_html("道琼斯", quotes["dow"].get("price"), quotes["dow"].get("change_pct"), _quote_meta(quotes["dow"], "US"))], "three"), ("🇭🇰 港股", [_market_item_html("恒生指数", quotes["hsi"].get("price"), quotes["hsi"].get("change_pct"), _quote_meta(quotes["hsi"], "HK")), _market_item_html("恒生科技", quotes["hstech"].get("price"), quotes["hstech"].get("change_pct"), _quote_meta(quotes["hstech"], "HK"))], "two"), ("🇨🇳 A股", [_market_item_html("上证指数", quotes["sh"].get("price"), quotes["sh"].get("change_pct"), _quote_meta(quotes["sh"], "CN")), _market_item_html("深证成指", quotes["sz"].get("price"), quotes["sz"].get("change_pct"), _quote_meta(quotes["sz"], "CN")), _market_item_html("沪深300", quotes["csi300"].get("price"), quotes["csi300"].get("change_pct"), _quote_meta(quotes["csi300"], "CN"))], "three")]
    cols = st.columns(3, gap="small")
    for col, (title, items, grid_class) in zip(cols, groups):
        with col: st.markdown(f'<div class="market-group"><div class="market-group-title">{title}</div><div class="market-group-row {grid_class}">' + "".join(items) + '</div></div>', unsafe_allow_html=True)
render_market_groups()

@st.cache_data(ttl=20, show_spinner=False)
def _search_yahoo(market, query):
    if not query.strip(): return []
    try:
        response = requests.get("https://query1.finance.yahoo.com/v1/finance/search", params={"q": query.strip(), "quotesCount": 10, "newsCount": 0}, headers={"User-Agent": "Mozilla/5.0"}, timeout=5); response.raise_for_status(); quotes = response.json().get("quotes") or []; results = []
        for item in quotes:
            if item.get("quoteType") != "EQUITY": continue
            symbol = str(item.get("symbol") or "")
            if market == "US" and ("." in symbol or symbol.endswith(("=F", "=X"))): continue
            if market == "HK" and not symbol.upper().endswith(".HK"): continue
            if market == "CN" and not symbol.upper().endswith((".SS", ".SZ")): continue
            results.append({"symbol": symbol, "name": item.get("longname") or item.get("shortname") or symbol, "exchange": item.get("exchange") or item.get("exchDisp") or ""})
        return results[:6]
    except Exception: return []

@st.cache_data(ttl=60, show_spinner=False)
def _search_eastmoney_cn(query):
    if not query.strip(): return []
    try:
        response = requests.get(EASTMONEY_SEARCH_URL, params={"input": query.strip(), "type": 14, "count": 6}, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}, timeout=5); response.raise_for_status(); payload = response.json() or {}; table = payload.get("QuotationCodeTable") or {}; rows = table.get("Data") or payload.get("data") or []; results = []
        for item in rows:
            if not isinstance(item, dict): continue
            code = str(item.get("SecurityCode") or item.get("Code") or item.get("code") or "").strip(); name = str(item.get("SecurityName") or item.get("Name") or item.get("name") or "").strip(); quote_id = str(item.get("QuoteID") or item.get("quoteId") or "").strip()
            if not code and quote_id: code = quote_id.split(".")[-1]
            if not code or not name: continue
            market = "SS" if quote_id.startswith("1.") or code.startswith(("5", "6", "9")) else ("SZ" if quote_id.startswith("0.") or code.startswith(("0", "2", "3")) else "")
            if market: results.append({"symbol": f"{code}.{market}", "name": name, "exchange": "SH" if market == "SS" else "SZ"})
        return results[:6]
    except Exception: return []

def _direct_symbol(market, query):
    q = query.strip().upper()
    if market == "US": return {"NVDIA": "NVDA", "NVIDA": "NVDA"}.get(q, q)
    digits = "".join(ch for ch in q if ch.isdigit())
    if market == "HK": return f"{digits.zfill(4)}.HK" if digits else q
    if not digits: return q
    return f"{digits}.SS" if digits.startswith(("5", "6", "68", "9")) else f"{digits}.SZ"

def _render_quote_block(item):
    row = _get_cached_quote(item["symbol"]); price, change = row.get("price"), row.get("change_pct"); price_text = "--" if price is None else f"{price:,.2f}"; change_text = "数据暂缺" if price is None else ("--" if change is None else f"{change:+.2f}%"); state = _market_state_text(row); after = ""
    if item.get("market") == "US":
        pp, pc = row.get("post_price"), row.get("post_change_pct"); pre_price, pre_change = row.get("pre_price"), row.get("pre_change_pct"); overnight_price, overnight_change = row.get("overnight_price"), row.get("overnight_change_pct")
        if overnight_price is not None: after = f'<div class="search-after">夜盘：<strong>{overnight_price:,.2f}</strong> <span>{"--" if overnight_change is None else f"{overnight_change:+.2f}%"}</span></div>'
        elif row.get("market_state") in ("POST", "POSTPOST", "CLOSED") and pp is not None: after = f'<div class="search-after">盘后：<strong>{pp:,.2f}</strong> <span>{"--" if pc is None else f"{pc:+.2f}%"}</span></div>'
        elif row.get("market_state") in ("PRE", "PREPRE") and pre_price is not None: after = f'<div class="search-after">盘前：<strong>{pre_price:,.2f}</strong> <span>{"--" if pre_change is None else f"{pre_change:+.2f}%"}</span></div>'
        elif pp is not None and row.get("post_market_time"): after = f'<div class="search-after">最近盘后：<strong>{pp:,.2f}</strong> <span>{"--" if pc is None else f"{pc:+.2f}%"}</span></div>'
    source = row.get("data_source") or row.get("quote_source") or ""; delay = row.get("delayed_by"); source_text = f"{source} · 延迟{delay}分" if delay not in (None, 0, "0") and source == "Yahoo Finance" else source
    return f'<div class="search-result"><div class="search-result-label">{html.escape(item["name"])} <span class="search-result-symbol">· {html.escape(item["symbol"])} · {html.escape(item.get("exchange", ""))}</span></div><div class="search-price">{html.escape(price_text)} <span class="market-change">{html.escape(change_text)} {html.escape(state)}</span></div>{after}<div class="search-hint">{html.escape(source_text)}</div></div>'

def _add_confirmed(key, item):
    confirmed = st.session_state.get(f"{key}_confirmed", []); confirmed = [confirmed] if isinstance(confirmed, dict) else (confirmed if isinstance(confirmed, list) else [])
    if not any(x.get("symbol") == item.get("symbol") for x in confirmed if isinstance(x, dict)): confirmed.append(item)
    st.session_state[f"{key}_confirmed"] = confirmed; st.session_state[key] = ""; st.session_state[f"{key}_open"] = False; st.session_state.pop(f"{key}_select", None); st.session_state.pop(f"{key}_confirm", None); _save_watchlists()

def _delete_confirmed(key, symbol):
    confirmed = st.session_state.get(f"{key}_confirmed", []); confirmed = [confirmed] if isinstance(confirmed, dict) else (confirmed if isinstance(confirmed, list) else [])
    st.session_state[f"{key}_confirmed"] = [item for item in confirmed if not (isinstance(item, dict) and item.get("symbol") == symbol)]; st.session_state[f"{key}_open"] = False; _save_watchlists()

def _open_search(key): st.session_state[f"{key}_open"] = True

def _confirm_search(key, market):
    query = str(st.session_state.get(key, "")).strip()
    if not query: return
    results = (_search_eastmoney_cn(query) if market == "CN" else _search_yahoo(market, query))
    if market == "CN" and not results: results = _search_yahoo(market, query)
    if results: selected = {**results[0], "market": market}
    else: selected = {"symbol": _direct_symbol(market, query), "name": query, "exchange": "", "market": market}
    _add_confirmed(key, selected)

@st.fragment(run_every="300s")
def render_watchlists():
    refresh_col, _, _ = st.columns([1.2, 3.8, 1])
    with refresh_col:
        st.markdown('<div class="module-refresh">', unsafe_allow_html=True)
        st.button("↻ 刷新股价", key="refresh_watchlist_quotes", use_container_width=True, on_click=_refresh_quote_cache, help="立即重新获取已添加模块的最新报价")
        st.markdown('</div>', unsafe_allow_html=True)
    search_cols = st.columns(3, gap="small")
    search_config = [(search_cols[0], "US", "🇺🇸 美股", "NVDA / Apple", "market_search_us"), (search_cols[1], "HK", "🇭🇰 港股", "0700 / 腾讯", "market_search_hk"), (search_cols[2], "CN", "🇨🇳 A股", "600519 / 贵州茅台", "market_search_cn")]
    for col, market, title, placeholder, key in search_config:
        with col:
            confirmed_list = st.session_state.get(f"{key}_confirmed", []); confirmed_list = [confirmed_list] if isinstance(confirmed_list, dict) else (confirmed_list if isinstance(confirmed_list, list) else [])
            if confirmed_list:
                st.markdown(f'<div class="market-group-title">{title}</div>', unsafe_allow_html=True)
                for idx, confirmed in enumerate(confirmed_list):
                    if not isinstance(confirmed, dict): continue
                    with st.container(border=True):
                        quote_col, delete_col = st.columns([1, 0.05], gap="small", vertical_alignment="top")
                        with quote_col: st.markdown(_render_quote_block({**confirmed, "market": market}), unsafe_allow_html=True)
                        with delete_col:
                            st.markdown('<div class="module-delete">', unsafe_allow_html=True)
                            st.button("×", key=f"{key}_delete_{idx}", on_click=_delete_confirmed, args=(key, confirmed.get("symbol")), help="删除此模块", type="tertiary")
                            st.markdown('</div>', unsafe_allow_html=True)
            is_open = st.session_state.get(f"{key}_open", False)
            if not is_open:
                st.button("+", key=f"{key}_open_button", use_container_width=True, on_click=_open_search, args=(key,), help="添加模块")
            else:
                input_col, confirm_col = st.columns([6, 1], gap="small")
                with input_col: st.text_input("搜索", placeholder=placeholder, key=key, label_visibility="collapsed")
                with confirm_col: st.button("✓", key=f"{key}_confirm", use_container_width=True, on_click=_confirm_search, args=(key, market), help="确认并新增")
render_watchlists()

def add_sources(sources):
    links = [f'<a href="{html.escape(url, quote=True)}" target="_blank" rel="noopener noreferrer">{html.escape(text)}</a>' for text, url in sources]
    st.markdown('<div class="source-text">Source: ' + '<span class="source-sep">|</span>'.join(links) + '</div>', unsafe_allow_html=True)

def add_line(fig, data, column, name, width=2.5, dash=None, yaxis=None, unit="%"):
    line = {"width": width}
    if dash: line["dash"] = dash
    trace = go.Scatter(x=data["observation_date"], y=data[column], name=name, mode="lines", line=line, hovertemplate=f"{name}: %{{y:.3f}}{unit}<extra></extra>")
    if yaxis: trace.update(yaxis=yaxis)
    fig.add_trace(trace)

def apply_chart_style(fig, height):
    fig.update_layout(height=height, template="plotly_white", hovermode="x unified", dragmode=False, margin=dict(l=35, r=35, t=30, b=35), legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0, font=dict(size=10)), hoverlabel=dict(bgcolor="white", font_size=11), font=dict(size=10 if compact_mode else 12), xaxis=dict(showgrid=False, showline=True, linecolor="#d1d5db", fixedrange=True, hoverformat="%Y-%m-%d"), yaxis=dict(showgrid=True, gridcolor="#eeeeee", zeroline=False, fixedrange=True)); fig.update_xaxes(fixedrange=True); fig.update_yaxes(fixedrange=True); return fig

def get_start_date(date_range):
    end = pd.Timestamp.today().normalize(); return {"5Y": end - pd.DateOffset(years=5), "1Y": end - pd.DateOffset(years=1), "6M": end - pd.DateOffset(months=6), "3M": end - pd.DateOffset(months=3), "1M": end - pd.DateOffset(months=1)}[date_range]
def filter_range(data, date_range): return data[data["observation_date"] >= get_start_date(date_range)].copy()
def chart_height(compact, normal): return compact if compact_mode else normal

def build_fig1(date_range):
    data = get_iorb().merge(get_rrp_rate(), on="observation_date", how="outer").merge(get_effr(), on="observation_date", how="outer").merge(get_sofr(), on="observation_date", how="outer").sort_values("observation_date"); data = filter_range(data, date_range); fig = go.Figure()
    for column, name, width in [("IORB", "IORB", 2.6), ("RRPONTSYAWARD", "ON RRP", 2.6), ("EFFR", "EFFR", 2.6), ("SOFR", "SOFR", 2.2)]: add_line(fig, data, column, name, width)
    fig.update_layout(yaxis_title="Rate (%)"); return apply_chart_style(fig, chart_height(190, 470))

def build_fig2(date_range):
    data = get_dgs10().merge(get_dfii10(), on="observation_date", how="inner").sort_values("observation_date"); data = filter_range(data, date_range); data["Breakeven"] = data["DGS10"] - data["DFII10"]; fig = go.Figure()
    for column, name, width, dash in [("DGS10", "10Y Nominal", 2.8, None), ("DFII10", "10Y Real", 2.6, None), ("Breakeven", "10Y Breakeven", 2.5, "dot")]: add_line(fig, data, column, name, width, dash)
    fig.update_layout(yaxis_title="Yield (%)"); return apply_chart_style(fig, chart_height(190, 470))

def build_fig3(date_range):
    data = get_dgs3mo().merge(get_dgs2(), on="observation_date", how="outer").merge(get_dgs10(), on="observation_date", how="outer").sort_values("observation_date"); data = filter_range(data, date_range); data["10Y-2Y"] = data["DGS10"] - data["DGS2"]; data["10Y-3M"] = data["DGS10"] - data["DGS3MO"]; fig = go.Figure()
    for column, name, width in [("DGS3MO", "3M", 2.2), ("DGS2", "2Y", 2.4), ("DGS10", "10Y", 2.8)]: add_line(fig, data, column, name, width)
    add_line(fig, data, "10Y-2Y", "10Y−2Y", 2.2, "dot", "y2", " bp"); add_line(fig, data, "10Y-3M", "10Y−3M", 2.2, "dash", "y2", " bp")
    fig.update_traces(selector=dict(name="10Y−2Y"), hovertemplate="10Y−2Y: %{y:.1f} bp<extra></extra>"); fig.update_traces(selector=dict(name="10Y−3M"), hovertemplate="10Y−3M: %{y:.1f} bp<extra></extra>")
    fig.update_layout(yaxis=dict(title="Yield (%)", fixedrange=True), yaxis2=dict(title="Spread (bp)", overlaying="y", side="right", showgrid=False, zeroline=True, zerolinecolor="#9ca3af", fixedrange=True)); return apply_chart_style(fig, chart_height(200, 500))

PARAM_DESCRIPTIONS = ["IORB（Interest on Reserve Balances）：美联储对存放在美联储的准备金余额支付的利率。ON RRP（Overnight Reverse Repurchase Agreement）：美联储隔夜逆回购工具的利率。EFFR（Effective Federal Funds Rate）：美国联邦基金市场的有效隔夜利率。SOFR（Secured Overnight Financing Rate）：以美国国债为抵押的隔夜融资利率。", "10Y Nominal：10年期美国国债名义收益率。10Y Real：10年期美国国债实际收益率，通常指10年期TIPS实际收益率。Breakeven：10年期盈亏平衡通胀率，即名义收益率与实际收益率之差。", "3M：3个月期美国国债收益率。2Y：2年期美国国债收益率。10Y：10年期美国国债收益率。10Y−2Y：10年期与2年期美国国债收益率之差。10Y−3M：10年期与3个月期美国国债收益率之差。"]
def show_parameter_description(index): st.markdown(f'<div class="mini-description">{PARAM_DESCRIPTIONS[index]}</div>', unsafe_allow_html=True)
compact_mode = True

@st.fragment(run_every="3600s")
def render_core_charts():
    global compact_mode
    st.markdown('<div class="section-title">US monetary policy, Treasury yields and inflation expectations</div>', unsafe_allow_html=True); toggle_col, _ = st.columns([1, 5])
    with toggle_col: compact_mode = st.toggle("缩小图表 / 快速浏览", value=True, key="compact_mode", help="开启后，三个核心图表横向并排显示。")
    if compact_mode:
        cols = st.columns(3, gap="small")
        configs = [(cols[0], '<div class="compact-title">🏦 1. Fed Policy Rate</div>', '<div class="compact-description">IORB / ON RRP / EFFR / SOFR</div>', "compact_corridor_range", build_fig1, [("IORB", "https://fred.stlouisfed.org/series/IORB"), ("ON RRP", "https://fred.stlouisfed.org/series/RRPONTSYAWARD"), ("EFFR", "https://fred.stlouisfed.org/series/EFFR"), ("SOFR", "https://fred.stlouisfed.org/series/SOFR")], 0), (cols[1], '<div class="compact-title">2. 10Y Yield Structure</div>', '<div class="compact-description">10Y Nominal / Real / Breakeven</div>', "compact_yield10_range", build_fig2, [("DGS10", "https://fred.stlouisfed.org/series/DGS10"), ("DFII10", "https://fred.stlouisfed.org/series/DFII10"), ("T10YIE", "https://fred.stlouisfed.org/series/T10YIE")], 1), (cols[2], '<div class="compact-title">3. Treasury Yield</div>', '<div class="compact-description">3M / 2Y / 10Y / Curve Spread</div>', "compact_treasury_range", build_fig3, [("DGS3MO", "https://fred.stlouisfed.org/series/DGS3MO"), ("DGS2", "https://fred.stlouisfed.org/series/DGS2"), ("DGS10", "https://fred.stlouisfed.org/series/DGS10")], 2)]
        for column, title, description, key, builder, sources, desc_index in configs:
            with column: st.markdown(title, unsafe_allow_html=True); st.markdown(description, unsafe_allow_html=True); date_range = st.radio("时间范围", RANGES, horizontal=True, index=1, key=key, label_visibility="collapsed"); st.plotly_chart(builder(date_range), use_container_width=True, config=PLOTLY_CONFIG); show_parameter_description(desc_index); add_sources(sources)
    else:
        configs = [('<div class="section-title">🏦 1. Fed Policy Rate & Money Market</div>', '<div class="section-description">IORB、ON RRP Rate、EFFR 与 SOFR</div>', "normal_corridor_range", build_fig1, [("IORB", "https://fred.stlouisfed.org/series/IORB"), ("ON RRP", "https://fred.stlouisfed.org/series/RRPONTSYAWARD"), ("EFFR", "https://fred.stlouisfed.org/series/EFFR"), ("SOFR", "https://fred.stlouisfed.org/series/SOFR")], 0, True), ('<div class="section-title">2. 10Y Yield Structure</div>', '<div class="section-description">10Y Nominal / 10Y Real / 10Y Breakeven</div>', "normal_yield10_range", build_fig2, [("DGS10", "https://fred.stlouisfed.org/series/DGS10"), ("DFII10", "https://fred.stlouisfed.org/series/DFII10"), ("T10YIE", "https://fred.stlouisfed.org/series/T10YIE")], 1, True), ('<div class="section-title">3. Treasury Yield & Curve Spread</div>', '<div class="section-description">3M、2Y、10Y Treasury Yield 与曲线利差</div>', "normal_treasury_range", build_fig3, [("DGS3MO", "https://fred.stlouisfed.org/series/DGS3MO"), ("DGS2", "https://fred.stlouisfed.org/series/DGS2"), ("DGS10", "https://fred.stlouisfed.org/series/DGS10"), ("T10Y2Y", "https://fred.stlouisfed.org/series/T10Y2")], 2, False)]
        for title, description, key, builder, sources, desc_index, divider in configs:
            st.markdown(title, unsafe_allow_html=True); st.markdown(description, unsafe_allow_html=True); date_range = st.radio("时间范围", RANGES, horizontal=True, index=1, key=key, label_visibility="collapsed"); st.plotly_chart(builder(date_range), use_container_width=True, config=PLOTLY_CONFIG); show_parameter_description(desc_index); add_sources(sources)
            if divider: st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)
render_core_charts()

st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)
st.markdown('<div class="section-title">📰 7×24 重点财经快讯</div>', unsafe_allow_html=True)
st.markdown('<div class="section-description">东方财富「红字焦点快讯」 · 平台已筛选重点 · 每60秒自动刷新</div>', unsafe_allow_html=True)
@st.fragment(run_every="60s")
def render_news_panel():
    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("🔄 立即刷新", key="refresh_7x24", use_container_width=True): get_sina_news.clear(); st.rerun()
    news_items, news_error = get_sina_news(limit=50)
    if news_items:
        st.markdown(f'<div class="news-status">当前显示 {len(news_items)} 条 · 来源：东方财富红字焦点快讯 · 60秒自动刷新</div>', unsafe_allow_html=True); news_html = '<div class="news-box">'
        for idx, item in enumerate(news_items, start=1):
            news_time = html.escape(str(item.get("time", ""))); news_title = html.escape(str(item.get("title", ""))); news_content = html.escape(str(item.get("content", ""))); news_url = html.escape(str(item.get("url", EASTMONEY_FOCUS_URL)), quote=True)
            if not news_url.startswith(("http://", "https://")): news_url = EASTMONEY_FOCUS_URL
            body = f"<strong>{news_title}</strong><div style=\"margin-top:3px;\">{news_content}</div>" if news_title and news_content and news_title != news_content else (news_content or news_title)
            news_html += f'<div class="news-item"><span class="news-index">{idx}.</span><span class="news-time">{news_time}</span><div class="news-content"><a href="{news_url}" target="_blank" rel="noopener noreferrer">{body}</a></div></div>'
        st.html(news_html + "</div>")
    else:
        st.warning("暂时无法取得东方财富红字焦点快讯。");
        if news_error: st.caption(f"错误：{news_error}")
    add_sources([("东方财富红字焦点快讯", EASTMONEY_FOCUS_URL)])
render_news_panel()
st.markdown(f'<div class="source-text">Source: <a href="{EASTMONEY_FOCUS_URL}" target="_blank" rel="noopener noreferrer">Eastmoney 7×24 Focus News</a></div>', unsafe_allow_html=True)