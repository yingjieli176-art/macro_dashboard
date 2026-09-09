import html
import json
import time
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import streamlit as st
from macro_platform.hk_liquidity import build_hk_liquidity_figure, build_hk_liquidity_figures, load_hk_liquidity
from data import (get_dgs3mo, get_dgs2, get_dgs10, get_dfii10, get_sofr, get_iorb, get_effr, get_rrp_rate, get_sina_news, get_wresbal, get_wtre_gen, get_rrp_daily, _fred_series)

st.set_page_config(page_title="Macro Dashboard", page_icon="📊", layout="wide")

EASTMONEY_FOCUS_URL = "https://kuaixun.eastmoney.com/"
EASTMONEY_QUOTE_URL = "https://push2.eastmoney.com/api/qt/stock/get"
EASTMONEY_SEARCH_URL = "https://searchapi.eastmoney.com/api/suggest/get"
EASTMONEY_UT = "bd1d9ddb04089700cf9c27f4f4961f5b"
RANGES = ["5Y", "1Y", "6M", "3M", "1M"]
PLOTLY_CONFIG = {"displayModeBar": False, "scrollZoom": False, "doubleClick": False, "editable": False, "displaylogo": False}
WATCHLIST_PARAM = "watchlist"
REPO_URL = "https://github.com/yingjieli176-art/macro_dashboard"

st.markdown("""
<style>
.block-container { padding-top: 0.85rem; padding-bottom: 3rem; max-width: 1760px; }
html, body, [class*="css"] { font-family: "Noto Sans TC", "Noto Sans CJK TC", "Microsoft JhengHei", "PingFang TC", "Segoe UI", sans-serif; }
.dashboard-title { font-size: 1.9rem; font-weight: 700; letter-spacing: -0.02em; margin-bottom: 0.1rem; }
.section-title { font-size: 1.35rem; font-weight: 650; letter-spacing: -0.01em; margin-top: 0.7rem; margin-bottom: 0.15rem; min-height: 32px; display: flex; align-items: center; }
.section-description { color: #6b7280; font-size: 0.86rem; margin-bottom: 0.35rem; min-height: 22px; display: flex; align-items: center; }
.mini-description { color: #6b7280; font-size: 0.76rem; line-height: 1.5; margin: 2px 0 8px; }
.source-text { color: #6b7280; font-size: 0.74rem; margin: 3px 0 10px; line-height: 1.45; }
.source-text a { color: #6b7280; text-decoration: none !important; white-space: nowrap; }
.source-text a:hover { color: #374151; text-decoration: underline !important; }
.source-sep { color: #d1d5db; margin: 0 5px; }
.chart-divider { margin: 0.65rem 0 1rem; border-top: 1px solid #e5e7eb; }
.compact-title { font-size: 0.98rem; font-weight: 650; margin-bottom: 0.15rem; min-height: 25px; display: flex; align-items: center; }
.compact-description { color: #6b7280; font-size: 0.73rem; line-height: 1.35; margin-bottom: 0.35rem; min-height: 20px; display: flex; align-items: center; }
.news-status { color: #6b7280; font-size: 0.75rem; margin-bottom: 0.5rem; }
.news-box { border: 1px solid #e5e7eb; border-radius: 8px; padding: 6px 10px; background: #ffffff; max-height: 650px; overflow-y: auto; overflow-x: hidden; }
.news-item { display: flex; align-items: flex-start; padding: 8px 3px; border-bottom: 1px solid #eeeeee; line-height: 1.5; font-size: 0.84rem; overflow: visible; }
.news-item:last-child { border-bottom: none; }
.news-index { flex: 0 0 32px; width: 32px; color: #9ca3af; font-size: 0.72rem; font-family: "Segoe UI", sans-serif; padding-top: 2px; }
.news-time { flex: 0 0 72px; width: 72px; color: #6b7280; font-size: 0.72rem; white-space: nowrap; padding-top: 2px; margin-right: 6px; }
.news-content { flex: 1; min-width: 0; overflow: visible; white-space: normal; overflow-wrap: anywhere; word-break: break-word; }
.news-content a { color: #374151; text-decoration: none !important; display: block; white-space: normal; overflow: visible; overflow-wrap: anywhere; word-break: break-word; }
.market-groups { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 7px; margin-bottom: 0.45rem; }
.market-group { border: 1px solid #e5e7eb; border-radius: 8px; padding: 6px 8px 5px; background: #fff; min-width: 0; min-height: 82px; box-sizing: border-box; }
.market-group-title { color: #374151; font-size: 0.88rem; font-weight: 650; margin-bottom: 5px; }
.market-group-row { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 4px; min-height: 52px; align-items: start; }
.market-group-row.two { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.market-item { min-width: 0; height: 52px; min-height: 52px; max-height: 52px; padding-right: 4px; border-right: 1px solid #f0f0f0; box-sizing: border-box; overflow: hidden; }
.market-item:last-child { border-right: none; }
.market-name { color: #6b7280; font-size: 0.78rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.market-price { color: #111827; font-size: 0.98rem; font-weight: 650; margin-top: 1px; white-space: nowrap; }
.market-change { font-size: 0.76rem; white-space: nowrap; }
.market-meta { color: #9ca3af; font-size: 0.68rem; margin-top: 1px; white-space: nowrap; }
.search-title { color: #374151; font-size: 1.05rem; font-weight: 650; margin: 0.55rem 0 0.3rem; }
.search-result { padding: 4px 5px; margin-top: 1px; border-radius: 6px; height: 76px; min-height: 76px; max-height: 76px; box-sizing: border-box; overflow: hidden; }
.search-result-label { color: #374151; font-size: 0.80rem; line-height: 1.3; }
.search-result-symbol { color: #6b7280; font-size: 0.70rem; }
.search-price { color: #111827; font-size: 0.94rem; font-weight: 650; margin-top: 1px; width: 118px; max-width: 100%; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.search-after { color: #6b7280; font-size: 0.72rem; margin-top: 1px; }
.search-hint { color: #9ca3af; font-size: 0.68rem; margin-top: 1px; }
.module-delete { display: flex; justify-content: flex-end; align-items: flex-start; margin-top: -7px; margin-right: -4px; transform: none; position: relative; z-index: 5; }
.module-delete button { min-width: 24px !important; width: 24px !important; max-width: 24px !important; height: 24px !important; padding: 0 !important; margin: 0 !important; font-size: 14px !important; line-height: 24px !important; border: 0 !important; }
.search-result .search-after, .search-result .search-hint { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
@media (max-width: 900px) { .market-groups { grid-template-columns: 1fr; } }

html { scroll-behavior: smooth; }
.dashboard-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; padding: 4px 0 14px; margin-bottom: 14px; border-bottom: 1px solid #e5e7eb; }
.dashboard-heading { min-width: 0; }
.dashboard-eyebrow { color: #9ca3af; font-size: 0.68rem; font-weight: 700; letter-spacing: 0.14em; margin-bottom: 2px; }
.dashboard-subtitle { color: #6b7280; font-size: 0.82rem; line-height: 1.5; margin-top: 2px; }
.dashboard-links { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 6px; max-width: 620px; padding-top: 4px; }
.dashboard-links a { color: #374151 !important; text-decoration: none !important; font-size: 0.76rem; line-height: 1; padding: 7px 10px; border: 1px solid #e5e7eb; border-radius: 999px; background: #fff; white-space: nowrap; }
.dashboard-links a:hover { border-color: #9ca3af; background: #f9fafb; color: #111827 !important; }
.dashboard-links a.external { font-weight: 650; }
.section-anchor { height: 0; visibility: hidden; scroll-margin-top: 18px; }
.section-kicker { color: #9ca3af; font-size: 0.66rem; font-weight: 700; letter-spacing: 0.12em; margin-top: 0.4rem; margin-bottom: -0.35rem; }
.section-toolbar-note { color: #9ca3af; font-size: 0.72rem; margin-top: -0.15rem; margin-bottom: 0.5rem; }
div[data-testid="stVerticalBlockBorderWrapper"] { border-color: #e5e7eb !important; border-radius: 12px !important; }
div[data-testid="stPlotlyChart"] { border: 1px solid #eef2f7; border-radius: 12px; padding: 2px 4px 0; background: #fff; overflow: hidden; }
.stButton > button { border-radius: 8px; }
.source-text a { display: inline-block; padding: 1px 0; }
.market-group { border-radius: 12px; padding: 9px 10px 8px; }
.news-box { border-radius: 12px; padding: 8px 12px; }
@media (max-width: 1100px) {
  .dashboard-header { display: block; }
  .dashboard-links { justify-content: flex-start; max-width: none; margin-top: 10px; }
}
@media (max-width: 700px) {
  .block-container { padding-left: 0.75rem; padding-right: 0.75rem; }
  .dashboard-links a { font-size: 0.72rem; padding: 6px 8px; }
  .dashboard-title { font-size: 1.55rem; }
  .section-title { font-size: 1.12rem; }
}


.hk-liquidity-strip { display:grid; grid-template-columns:repeat(7,minmax(0,1fr)); gap:6px; margin:5px 0 10px; }
.hk-liquidity-strip > div { border:1px solid #e5e7eb; border-radius:9px; background:#fff; padding:7px 9px; min-width:0; }
.hk-liquidity-strip span { display:block; color:#9ca3af; font-size:.66rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.hk-liquidity-strip strong { display:block; color:#111827; font-size:.82rem; font-weight:650; margin-top:2px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
@media (max-width:1100px) { .hk-liquidity-strip { grid-template-columns:repeat(4,minmax(0,1fr)); } }
@media (max-width:700px) { .hk-liquidity-strip { grid-template-columns:repeat(2,minmax(0,1fr)); } }

</style>
""", unsafe_allow_html=True)

st.markdown(
    f"""
    <div class="dashboard-header">
      <div class="dashboard-heading">
        <div class="dashboard-eyebrow">MACRO · LIQUIDITY · RATES</div>
        <div class="dashboard-title">Macro Dashboard</div>
        <div class="dashboard-subtitle">跨市场行情、利率、流动性与 7×24 财经信息面板</div>
      </div>
      <div class="dashboard-links">
        <a href="#market-overview">市场概览</a>
        <a href="#watchlist">自选观察</a>
        <a href="#macro-charts">宏观图表</a>
        <a href="#news">财经快讯</a>
        <a class="external" href="{REPO_URL}" target="_blank" rel="noopener noreferrer">GitHub ↗</a>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

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

def _get_yahoo_overnight_safe(symbol, previous=None):
    try:
        response = requests.get("https://query1.finance.yahoo.com/v7/finance/quote", params={"symbols": symbol}, headers={"User-Agent": "Mozilla/5.0"}, timeout=2.5)
        response.raise_for_status(); rows = ((response.json() or {}).get("quoteResponse") or {}).get("result") or []
        if rows:
            item = rows[0]; price = item.get("overnightMarketPrice"); pct = item.get("overnightChangePercent")
            if price is not None:
                if pct is None and previous not in (None, 0): pct = (price - previous) / previous * 100
                return price, pct
    except Exception: pass
    return None, None

def _get_yahoo_quote_safe(symbol):
    try:
        response = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/" + symbol, params={"range": "1d", "interval": "5m", "includePrePost": "true"}, headers={"User-Agent": "Mozilla/5.0"}, timeout=2.5)
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
        overnight_price, overnight_change_pct = _get_yahoo_overnight_safe(symbol, previous)
        row = _empty_quote(); row.update({"price": price, "change_pct": regular_change_pct, "market_state": meta.get("marketState", ""), "currency": meta.get("currency", ""), "post_price": post_price, "post_change_pct": post_change_pct, "pre_price": pre_price, "pre_change_pct": pre_change_pct, "overnight_price": overnight_price, "overnight_change_pct": overnight_change_pct, "regular_market_time": meta.get("regularMarketTime"), "post_market_time": meta.get("postMarketTime"), "pre_market_time": meta.get("preMarketTime"), "quote_source": meta.get("quoteSourceName", ""), "delayed_by": meta.get("exchangeDataDelayedBy"), "data_source": "Yahoo Finance"}); return row
    except Exception: return _empty_quote()

def _eastmoney_secid(symbol):
    raw = str(symbol or "").upper().strip()
    if raw == "^HSI": return "100.HSI"
    if raw in ("HSTECH.HK", "^HSTECH"): return "100.HSTECH"
    if raw.endswith(".HK"): return f"116.{raw[:-3].zfill(5)}"
    if raw.endswith(".SS"): return f"1.{raw[:-3]}"
    if raw.endswith(".SZ"): return f"0.{raw[:-3]}"
    return ""

def _get_eastmoney_quote_safe(symbol):
    secid = _eastmoney_secid(symbol)
    if not secid: return _empty_quote()
    try:
        response = requests.get(EASTMONEY_QUOTE_URL, params={"secid": secid, "fields": "f43,f57,f58,f169,f170,f46,f44,f45,f47,f48,f60,f86", "ut": EASTMONEY_UT, "fltt": "2", "invt": "2"}, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}, timeout=2.5); response.raise_for_status(); data = (response.json() or {}).get("data") or {}
        if not data: return _empty_quote()
        price_raw, prev_raw, pct_raw = data.get("f43"), data.get("f60"), data.get("f170")
        if price_raw in (None, "-", ""): return _empty_quote()
        divisor = 1 if str(symbol).upper() in ("^HSI", "HSTECH.HK", "^HSTECH", "000001.SS", "399001.SZ", "000300.SS") else 100
        price = float(price_raw) / divisor; previous = None if prev_raw in (None, "-") else float(prev_raw) / divisor
        change_pct = None if pct_raw in (None, "-") else float(pct_raw)
        if change_pct is None and previous not in (None, 0): change_pct = (price - previous) / previous * 100
        return {"price": price, "change_pct": change_pct, "market_state": "REGULAR", "currency": ("HKD" if str(symbol).upper().endswith(".HK") else "CNY"), "post_price": None, "post_change_pct": None, "pre_price": None, "pre_change_pct": None, "overnight_price": None, "overnight_change_pct": None, "regular_market_time": data.get("f86"), "post_market_time": None, "pre_market_time": None, "quote_source": "Eastmoney", "delayed_by": 0, "data_source": "东方财富"}
    except Exception: return _empty_quote()

def _market_state_text(row): return {"REGULAR": "交易中", "PRE": "盘前", "POST": "盘后", "CLOSED": "休市"}.get(row.get("market_state") or "", "")

def _market_item_html(name, price, change_pct, meta=""):
    price_text = "--" if price is None else f"{price:,.2f}"; change_text = "--" if change_pct is None else f"{change_pct:+.2f}%"
    return f'<div class="market-item"><div class="market-name">{html.escape(name)}</div><div class="market-price">{html.escape(price_text)}</div><div class="market-change">{html.escape(change_text)}</div><div class="market-meta">{html.escape(meta)}</div></div>'

@st.cache_data(ttl=60, show_spinner=False)
def _get_cached_quote(symbol, refresh_key=0):
    if str(symbol).upper().endswith((".SS", ".SZ", ".HK")) or str(symbol).upper() in ("^HSI", "^HSTECH"):
        row = _get_eastmoney_quote_safe(symbol)
        if row.get("price") is not None: return row
    return _get_yahoo_quote_safe(symbol)

def _quote_refresh_key(): return int(time.time() // 60)

def _quote_meta(row, market=""):
    source = row.get("data_source") or row.get("quote_source") or ""; delayed = row.get("delayed_by"); state = _market_state_text(row); parts = [state] if state else []
    if delayed not in (None, 0, "0") and source == "Yahoo Finance": parts.append(f"延迟{delayed}分")
    elif source: parts.append(source)
    return " · ".join(parts)

@st.cache_data(ttl=60, show_spinner=False)
def _get_watchlist_quote(symbol): return _get_yahoo_quote_safe(symbol)

def render_market_groups():
    now = time.time(); snapshot = st.session_state.get("_market_quotes_snapshot"); snapshot_time = st.session_state.get("_market_quotes_snapshot_time", 0)
    if not isinstance(snapshot, dict) or now - snapshot_time >= 60:
        refresh_key = _quote_refresh_key()
        snapshot = {"nasdaq": _get_cached_quote("^IXIC", refresh_key), "sp500": _get_cached_quote("^GSPC", refresh_key), "dow": _get_cached_quote("^DJI", refresh_key), "hsi": _get_cached_quote("^HSI", refresh_key), "hstech": _get_cached_quote("HSTECH.HK", refresh_key), "sh": _get_cached_quote("000001.SS", refresh_key), "sz": _get_cached_quote("399001.SZ", refresh_key), "csi300": _get_cached_quote("000300.SS", refresh_key)}
        st.session_state["_market_quotes_snapshot"] = snapshot; st.session_state["_market_quotes_snapshot_time"] = now
    q = snapshot
    groups = [("🇺🇸 美股", [_market_item_html("纳斯达克", q["nasdaq"].get("price"), q["nasdaq"].get("change_pct"), _quote_meta(q["nasdaq"])), _market_item_html("标普500", q["sp500"].get("price"), q["sp500"].get("change_pct"), _quote_meta(q["sp500"])), _market_item_html("道琼斯", q["dow"].get("price"), q["dow"].get("change_pct"), _quote_meta(q["dow"]))], "three"), ("🇭🇰 港股", [_market_item_html("恒生指数", q["hsi"].get("price"), q["hsi"].get("change_pct"), _quote_meta(q["hsi"])), _market_item_html("恒生科技", q["hstech"].get("price"), q["hstech"].get("change_pct"), _quote_meta(q["hstech"]))], "two"), ("🇨🇳 A股", [_market_item_html("上证指数", q["sh"].get("price"), q["sh"].get("change_pct"), _quote_meta(q["sh"])), _market_item_html("深证成指", q["sz"].get("price"), q["sz"].get("change_pct"), _quote_meta(q["sz"])) , _market_item_html("沪深300", q["csi300"].get("price"), q["csi300"].get("change_pct"), _quote_meta(q["csi300"]))], "three")]
    cards = []
    for title, items, grid_class in groups: cards.append(f'<div class="market-group"><div class="market-group-title">{title}</div><div class="market-group-row {grid_class}">' + "".join(items) + '</div></div>')
    st.markdown('<div class="market-groups">' + "".join(cards) + '</div>', unsafe_allow_html=True)

st.markdown('<div id="market-overview" class="section-anchor"></div><div class="section-kicker">MARKET OVERVIEW</div>', unsafe_allow_html=True)
st.markdown('<div class="section-title">市场概览</div><div class="section-description">美股、港股与 A 股主要指数 · 行情模块每 60 秒刷新</div>', unsafe_allow_html=True)
render_market_groups()
st.caption(f"行情数据刷新时间：{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}")

@st.cache_data(ttl=20, show_spinner=False)
def _search_yahoo(market, query):
    if not query.strip(): return []
    try:
        response = requests.get("https://query1.finance.yahoo.com/v1/finance/search", params={"q": query.strip(), "quotesCount": 10, "newsCount": 0}, headers={"User-Agent": "Mozilla/5.0"}, timeout=2.5); response.raise_for_status(); quotes = response.json().get("quotes") or []; results = []
        for item in quotes:
            if item.get("quoteType") != "EQUITY": continue
            symbol = str(item.get("symbol") or "")
            if market == "US" and ("." in symbol or symbol.endswith(("=F", "=X"))): continue
            if market == "HK" and not symbol.upper().endswith(".HK"): continue
            if market == "CN" and not symbol.upper().endswith((".SS", ".SZ")): continue
            results.append({"symbol": symbol, "name": item.get("longname") or item.get("shortname") or symbol, "exchange": item.get("exchange") or item.get("exchDisp") or ""})
        return results[:6]
    except Exception: return []

def _render_quote_block(item):
    row = _get_watchlist_quote(item["symbol"]); price, change = row.get("price"), row.get("change_pct"); price_text = "--" if price is None else f"{price:,.2f}"; change_text = "数据暂缺" if price is None else ("--" if change is None else f"{change:+.2f}%"); state = _market_state_text(row); after = ""
    if item.get("market") == "US":
        pp, pc = row.get("post_price"), row.get("post_change_pct"); pre_price, pre_change = row.get("pre_price"), row.get("pre_change_pct"); overnight_price, overnight_change = row.get("overnight_price"), row.get("overnight_change_pct"); market_state = row.get("market_state")
        if market_state in ("POSTPOST", "CLOSED") and overnight_price is not None: after = f'<div class="search-after">夜盘：<strong>{overnight_price:,.2f}</strong> <span>{"--" if overnight_change is None else f"{overnight_change:+.2f}%"}</span></div>'
        elif market_state in ("PRE", "PREPRE") and pre_price is not None: after = f'<div class="search-after">盘前：<strong>{pre_price:,.2f}</strong> <span>{"--" if pre_change is None else f"{pre_change:+.2f}%"}</span></div>'
        elif market_state == "POST" and pp is not None: after = f'<div class="search-after">盘后：<strong>{pp:,.2f}</strong> <span>{"--" if pc is None else f"{pc:+.2f}%"}</span></div>'
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

def _run_search(key, market):
    query = str(st.session_state.get(key, "")).strip()
    if not query: return
    results = _search_yahoo(market, query); st.session_state[f"{key}_results"] = [{**item, "market": market} for item in results]

def _confirm_selected(key):
    results = st.session_state.get(f"{key}_results", []); index = st.session_state.get(f"{key}_result_select")
    if not results or index is None: return
    try: item = results[int(index)]
    except (ValueError, TypeError, IndexError): return
    _add_confirmed(key, item); st.session_state.pop(f"{key}_results", None)

def _cancel_search(key):
    st.session_state[f"{key}_open"] = False; st.session_state.pop(f"{key}_results", None)

def render_watchlist_refresh_control():
    _, refresh_col = st.columns([5, 1], vertical_alignment="top")
    with refresh_col:
        if st.button("↻ 刷新股价", key="refresh_watchlist_quotes", use_container_width=True, help="立即重新获取已添加模块的最新报价"):
            _get_watchlist_quote.clear(); st.session_state["_watchlist_refresh_key"] = st.session_state.get("_watchlist_refresh_key", 0) + 1

st.markdown('<div id="watchlist" class="section-anchor"></div><div class="section-kicker">WATCHLIST</div>', unsafe_allow_html=True)
st.markdown('<div class="section-title">自选观察</div><div class="section-description">按市场添加股票模块；刷新、搜索与删除操作集中在本区域</div>', unsafe_allow_html=True)
render_watchlist_refresh_control()

@st.fragment(run_every="60s")
def render_watchlists():
    search_cols = st.columns(3, gap="small", vertical_alignment="top")
    search_config = [(search_cols[0], "US", "🇺🇸 美股", "NVDA / Apple", "market_search_us"), (search_cols[1], "HK", "🇭🇰 港股", "0700 / 腾讯", "market_search_hk"), (search_cols[2], "CN", "🇨🇳 A股", "600519 / 贵州茅台", "market_search_cn")]
    for col, market, title, placeholder, key in search_config:
        with col:
            confirmed_list = st.session_state.get(f"{key}_confirmed", []); confirmed_list = [confirmed_list] if isinstance(confirmed_list, dict) else (confirmed_list if isinstance(confirmed_list, list) else [])
            if confirmed_list:
                st.markdown(f'<div class="market-group-title">{title}</div>', unsafe_allow_html=True)
                for idx, confirmed in enumerate(confirmed_list):
                    if not isinstance(confirmed, dict): continue
                    with st.container(border=True):
                        quote_col, delete_col = st.columns([1, 0.08], gap="small", vertical_alignment="top")
                        with quote_col: st.markdown(_render_quote_block({**confirmed, "market": market}), unsafe_allow_html=True)
                        with delete_col:
                            st.markdown('<div class="module-delete">', unsafe_allow_html=True); st.button("×", key=f"{key}_delete_{idx}", on_click=_delete_confirmed, args=(key, confirmed.get("symbol")), help="删除此模块", type="tertiary", use_container_width=True); st.markdown('</div>', unsafe_allow_html=True)
            is_open = st.session_state.get(f"{key}_open", False)
            if not is_open: st.button("+", key=f"{key}_open_button", use_container_width=True, on_click=_open_search, args=(key,), help="添加模块")
            else:
                input_col, search_col, cancel_col = st.columns([5.2, 1.1, 1.1], gap="small")
                with input_col: st.text_input("搜索", placeholder=placeholder, key=key, label_visibility="collapsed")
                with search_col: st.button("搜索", key=f"{key}_search_button", use_container_width=True, on_click=_run_search, args=(key, market))
                with cancel_col: st.button("取消", key=f"{key}_cancel_button", use_container_width=True, on_click=_cancel_search, args=(key,))
                results = st.session_state.get(f"{key}_results", [])
                if results:
                    options = [f'{item.get("name", "")} · {item.get("symbol", "")} · {item.get("exchange", "")}' for item in results]
                    st.radio("搜索结果", range(len(options)), format_func=lambda i: options[i], key=f"{key}_result_select", label_visibility="collapsed")
                    st.button("确认添加", key=f"{key}_confirm_selected", use_container_width=True, on_click=_confirm_selected, args=(key,), type="primary")
                elif st.session_state.get(key, "").strip() and f"{key}_results" in st.session_state: st.caption("没有找到匹配的股票，请检查名称或代码。")

render_watchlists()

def add_sources(sources):
    links = [f'<a href="{html.escape(url, quote=True)}" target="_blank" rel="noopener noreferrer">{html.escape(text)}</a>' for text, url in sources]
    st.markdown('<div class="source-text">Source: ' + '<span class="source-sep">|</span>'.join(links) + '</div>', unsafe_allow_html=True)

def add_line(fig, data, column, name, width=2.5, dash=None, yaxis=None, unit="%"):
    if column not in data.columns or data[column].notna().sum() == 0: return
    line = {"width": width}
    if dash: line["dash"] = dash
    trace = go.Scatter(x=data["observation_date"], y=data[column], name=name, mode="lines", line=line, hovertemplate=f"{name}: %{{y:.3f}}{unit}<extra></extra>")
    if yaxis: trace.update(yaxis=yaxis)
    fig.add_trace(trace)

def _xaxis_config(date_range):
    return dict(
        type="date", showgrid=True, gridcolor="#eef2f7", griddash="dot",
        showline=True, linecolor="#9ca3af", linewidth=1, fixedrange=False,
        hoverformat="%Y-%m-%d", tickfont=dict(size=9 if compact_mode else 11),
        tickangle=0, ticklabelstandoff=5, automargin=False,
        tickmode="auto", nticks=7 if compact_mode else 10,
    )

def _year_axis_config():
    return dict(
        type="date",
        overlaying="x",
        matches="x",
        anchor="free",
        side="top",
        position=1.0,
        showgrid=False,
        showline=True,
        linecolor="#6b7280",
        linewidth=1.2,
        ticks="outside",
        ticklen=5,
        tickwidth=1,
        tickcolor="#6b7280",
        showticklabels=True,
        tickfont=dict(size=11 if compact_mode else 12),
        tickformat="%Y",
        dtick="M12",
        ticklabelstandoff=6,
        fixedrange=True,
        automargin=True,
        layer="above traces",
        title=dict(text="X轴：年份", font=dict(size=11 if compact_mode else 12), standoff=8),
    )

def apply_chart_style(fig, height, date_range):
    yaxis2 = getattr(fig.layout, "yaxis2", None)
    has_secondary = yaxis2 is not None and yaxis2.overlaying is not None
    base_left = 60
    base_right = 76 if has_secondary else 20
    base_top = 115 if compact_mode else 105
    base_bottom = 40

    fig.update_layout(
        height=height,
        template="plotly_white",
        hovermode="closest" if compact_mode else "x unified",
        dragmode=False,
        margin=dict(l=base_left, r=base_right, t=base_top, b=base_bottom, pad=2),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.08, xanchor="left", x=0,
            font=dict(size=9 if compact_mode else 11), traceorder="normal",
            itemwidth=30, bgcolor="rgba(255,255,255,0)",
        ),
        hoverlabel=dict(bgcolor="white", font_size=11, bordercolor="#e5e7eb"),
        font=dict(size=10 if compact_mode else 12),
        xaxis=_xaxis_config(date_range),
        xaxis2=_year_axis_config(),
        yaxis=dict(
            showgrid=True, gridcolor="#e5e7eb", griddash="dot", zeroline=False,
            showline=True, linecolor="#9ca3af", linewidth=1, fixedrange=True,
            tickfont=dict(size=10 if compact_mode else 11), automargin=False,
            nticks=5 if compact_mode else 7, title=dict(standoff=8),
        ),
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
    )
    if has_secondary:
        fig.update_layout(yaxis2=dict(
            automargin=False,
            tickfont=dict(size=9 if compact_mode else 10),
            title=dict(standoff=8),
        ))
    fig.update_xaxes(fixedrange=True)
    fig.update_yaxes(fixedrange=True)
    return fig

def get_start_date(date_range):
    end = pd.Timestamp.today().normalize(); return {"5Y": end - pd.DateOffset(years=5), "1Y": end - pd.DateOffset(years=1), "6M": end - pd.DateOffset(months=6), "3M": end - pd.DateOffset(months=3), "1M": end - pd.DateOffset(months=1)}[date_range]

def filter_range(data, date_range): return data[data["observation_date"] >= get_start_date(date_range)].copy()
def chart_height(compact, normal): return compact if compact_mode else normal

@st.cache_data(ttl=3600, show_spinner=False)
def get_fred_series(series_id): return _fred_series(series_id)



# === HK LIQUIDITY CHART 5 ===
def get_hk_liquidity():
    return load_hk_liquidity()


def build_fig5(date_range):
    return build_hk_liquidity_figures(date_range, compact_mode=False)


def apply_hk_chart_range(fig, date_range):
    """Apply an independent viewport using the newest observation in that figure."""
    latest_candidates = []
    for trace in fig.data:
        values = getattr(trace, "x", None)
        if values is None:
            continue
        parsed = pd.to_datetime(list(values), errors="coerce")
        parsed = parsed[~pd.isna(parsed)]
        if len(parsed):
            latest_candidates.append(parsed.max())
    if not latest_candidates:
        return fig
    latest = max(latest_candidates)
    offsets = {
        "5Y": pd.DateOffset(years=5),
        "1Y": pd.DateOffset(years=1),
        "6M": pd.DateOffset(months=6),
        "3M": pd.DateOffset(months=3),
        "1M": pd.DateOffset(months=1),
    }
    start = latest - offsets.get(date_range, offsets["1Y"])
    fig.update_xaxes(range=[start, latest])
    return fig

def build_fig1(date_range):
    data = get_iorb().merge(get_rrp_rate(), on="observation_date", how="outer").merge(get_effr(), on="observation_date", how="outer").merge(get_sofr(), on="observation_date", how="outer").sort_values("observation_date"); data = filter_range(data, date_range); fig = go.Figure()
    for column, name, width in [("IORB", "IORB", 2.6), ("RRPONTSYAWARD", "ON RRP", 2.6), ("EFFR", "EFFR", 2.6), ("SOFR", "SOFR", 2.2)]: add_line(fig, data, column, name, width)
    fig.update_layout(yaxis_title="Rate (%)"); return apply_chart_style(fig, chart_height(340, 500), date_range)

def build_fig2(date_range):
    data = get_dgs10().merge(get_dfii10(), on="observation_date", how="outer").merge(get_fred_series("T10YIE"), on="observation_date", how="outer").sort_values("observation_date"); data = filter_range(data, date_range); fig = go.Figure()
    for column, name, width, dash, yaxis in [("DGS10", "10Y Nominal", 2.8, None, None), ("DFII10", "10Y Real (R)", 2.6, None, "y2"), ("T10YIE", "10Y Breakeven (R)", 2.5, "dot", "y2")]: add_line(fig, data, column, name, width, dash, yaxis)
    fig.update_layout(yaxis_title="Nominal Yield (%)", yaxis2=dict(title="Real / Breakeven (%)", overlaying="y", side="right", anchor="free", position=1.0, showgrid=False, zeroline=False, fixedrange=True, automargin=True, tickfont=dict(size=9))); return apply_chart_style(fig, chart_height(340, 500), date_range)

def build_fig4(date_range):
    specs = [(get_wresbal, "WRESBAL"), (get_wtre_gen, "WTREGEN"), (get_rrp_daily, "RRPONTSYD")]
    series = []
    for getter, column in specs:
        try:
            frame = getter().copy(); frame["observation_date"] = pd.to_datetime(frame["observation_date"], errors="coerce"); frame[column] = pd.to_numeric(frame[column], errors="coerce"); frame = frame.dropna(subset=["observation_date", column]).sort_values("observation_date")[["observation_date", column]]
            if not frame.empty:
                if column == "RRPONTSYD": frame[column] = frame[column] / 1000.0; frame = frame.set_index("observation_date")[column].resample("W-WED").mean().rename(column).reset_index()
                else: frame[column] = frame[column] / 1000000.0
                series.append(frame)
        except Exception: continue
    if not series: return apply_chart_style(go.Figure(), chart_height(340, 500), date_range)
    data = series[0]
    for frame in series[1:]: data = data.merge(frame, on="observation_date", how="outer")
    data = data.sort_values("observation_date"); value_cols = [c for c in ["WRESBAL", "WTREGEN", "RRPONTSYD"] if c in data.columns]; data[value_cols] = data[value_cols].ffill()
    if all(c in data.columns for c in ["WRESBAL", "WTREGEN", "RRPONTSYD"]): data["NetLiquidity"] = data["WRESBAL"] - data["WTREGEN"] - data["RRPONTSYD"]
    data = filter_range(data, date_range); fig = go.Figure()
    for column, name, width, dash in [("NetLiquidity", "Net Liquidity Proxy", 3.0, None), ("WRESBAL", "Reserve Balances", 2.3, None), ("WTREGEN", "TGA", 2.1, "dash"), ("RRPONTSYD", "ON RRP", 2.1, "dot")]: add_line(fig, data, column, name, width, dash, unit=" T")
    fig.update_layout(yaxis_title="$T"); return apply_chart_style(fig, chart_height(340, 500), date_range)

def build_fig3(date_range):
    data = get_dgs3mo().merge(get_dgs2(), on="observation_date", how="outer").merge(get_dgs10(), on="observation_date", how="outer").merge(get_fred_series("T10Y2Y"), on="observation_date", how="outer").merge(get_fred_series("T10Y3M"), on="observation_date", how="outer").sort_values("observation_date"); data = filter_range(data, date_range); fig = go.Figure()
    for column, name, width in [("DGS3MO", "3M", 2.2), ("DGS2", "2Y", 2.4), ("DGS10", "10Y", 2.8)]: add_line(fig, data, column, name, width)
    add_line(fig, data, "T10Y2Y", "10Y−2Y (R)", 2.2, "dot", "y2", "%"); add_line(fig, data, "T10Y3M", "10Y−3M (R)", 2.2, "dash", "y2", "%")
    fig.update_traces(selector=dict(name="10Y−2Y (R)"), hovertemplate="10Y−2Y (R): %{y:.3f}%<extra></extra>"); fig.update_traces(selector=dict(name="10Y−3M (R)"), hovertemplate="10Y−3M (R): %{y:.3f}%<extra></extra>")
    fig.update_layout(yaxis=dict(title="Yield (%)", fixedrange=True), yaxis2=dict(title="Spread (%)", overlaying="y", side="right", anchor="free", position=1.0, showgrid=False, zeroline=True, zerolinecolor="#9ca3af", fixedrange=True, automargin=True, tickfont=dict(size=9))); return apply_chart_style(fig, chart_height(340, 500), date_range)

PARAM_DESCRIPTIONS = [
    '<b>参数概念：</b><br>1. IORB（Interest on Reserve Balances）：美联储向存款机构准备金余额支付的利率，是美国准备金利率体系的重要基准。<br>2. ON RRP（Overnight Reverse Repurchase Agreement）：美联储隔夜逆回购工具利率，金融机构可通过该工具进行隔夜资金配置。<br>3. EFFR（Effective Federal Funds Rate）：美国联邦基金市场实际成交形成的有效隔夜利率，反映银行间短期无担保资金价格。<br>4. SOFR（Secured Overnight Financing Rate）：以美国国债为抵押的隔夜融资利率，是美元有担保短期融资的重要基准。',
    '<b>参数概念：</b><br>1. 10Y Nominal：10 年期美国国债名义收益率，包含实际利率与通胀预期等因素。<br>2. 10Y Real：10 年期美国国债实际收益率，通常由通胀保值国债（TIPS）市场反映。<br>3. 10Y Breakeven：10 年期盈亏平衡通胀率，是名义国债收益率与实际收益率之间的差值，用于观察市场隐含的长期通胀预期。',
    '<b>参数概念：</b><br>1. 3M：3 个月期美国国债收益率，代表较短期限的美元无风险利率。<br>2. 2Y：2 年期美国国债收益率，通常对美联储政策路径及短中期利率预期较敏感。<br>3. 10Y：10 年期美国国债收益率，是全球金融市场重要的长期无风险利率参考。<br>4. 10Y−2Y：10 年期减 2 年期国债收益率利差，图中直接以百分比（%）显示，无需自行换算 bp。<br>5. 10Y−3M：10 年期减 3 个月期国债收益率利差，图中直接以百分比（%）显示，无需自行换算 bp。',
    '<b>参数概念：</b><br>1. Net Liquidity Proxy：Reserve Balances − TGA − ON RRP 的组合指标，用于描述美国金融体系中可观察的流动性变化方向；不是美联储官方指标。<br>2. Reserve Balances：存款机构存放在美联储的准备金余额，属于银行体系流动性的重要组成部分。<br>3. TGA（Treasury General Account）：美国财政部在美联储的总账户余额，财政资金进出会影响银行体系准备金。<br>4. ON RRP Balance：美联储隔夜逆回购工具的余额，反映资金进入该工具的规模。',
    '<b>参数概念：</b><br>1. HKD M2 MoM：港元 M2 月环比增速，用来观察广义港元货币的边际扩张或收缩；主图采用月环比以提高对当前流动性变化的敏感度。<br>2. HKD M3 MoM：港元 M3 月环比增速，统计口径较 M2 更广，用于交叉确认广义货币边际变化。<br>3. Monetary Base MoM：香港货币基础总量月环比变化，用于观察基础货币层面的边际扩张与收缩。<br>4. Aggregate Balance：银行体系总结余，单位 HK$ billion；总结余下降通常代表银行体系可用港元流动性趋紧。<br>5. O/N HIBOR：隔夜港元银行同业拆息，反映最短端港元资金价格。<br>6. 3M HIBOR：3 个月港元银行同业拆息，用来观察更持续的港元融资成本。<br>7. HKMA Base Rate：香港金管局基本利率，是港元利率体系的重要政策参考。<br>8. O/N−3M Spread（R）：隔夜 HIBOR 减 3M HIBOR，右轴单位 bp；显著转正通常代表短端资金压力上升。<br>9. USD/HKD：每 1 美元对应的港元价格；向 7.85 上升表示港元转弱，向 7.75 下降表示港元转强。<br>10. Strong-side CU 7.75：联系汇率制度下强方兑换保证。<br>11. Weak-side CU 7.85：联系汇率制度下弱方兑换保证。<br><br><b>读取提示：</b>M2/M3 为月度统计，公布存在时滞；主图使用 MoM 观察边际变化，流动性评分使用最近 3 个月 M2/M3 MoM 均值降低单月噪声。YoY 保留在数据层供后续切换与中期趋势判断。',
]

def show_parameter_description(index): st.markdown(f'<div class="mini-description">{PARAM_DESCRIPTIONS[index]}</div>', unsafe_allow_html=True)

HK_PARAMETER_DESCRIPTIONS = [
    '<b>参数概念：</b><br>1. HKD M2 MoM：港元 M2 月环比增速，用来观察广义港元货币的边际扩张或收缩。<br>2. HKD M3 MoM：港元 M3 月环比增速，统计口径较 M2 更广，用于交叉确认广义货币边际变化。<br>3. Monetary Base MoM：香港货币基础总量月环比变化。<br>4. HKEX Price（R）：港交所 0388.HK 月末收盘价，右轴单位 HKD；用于观察香港交易所股价与货币流动性变化之间的市场映射。<br>5. HSTECH Index（R）：恒生科技指数 HSTECH.HK 月末指数点位，右轴单位 points；用于观察高贝塔科技资产价格水平与香港流动性环境的关系。',
    '<b>参数概念：</b><br>1. Opening Aggregate Balance：每日开市银行体系总结余，单位 HK$ billion。<br>2. Closing Aggregate Balance：每日收市银行体系总结余，是观察即时港元银行体系流动性的核心指标。<br>3. Forecast Aggregate Balance T+1：HKMA 公布的下一交易日预计总结余，用于提前观察已知外汇交易、市场操作及贴现窗逆转后的流动性变化。<br>4. Outstanding EFBN（R）：外汇基金票据及债券未偿还总额，右轴单位 HK$ billion；EFBN 是香港货币基础的重要组成部分。<br>5. EFBN Held by Licensed Banks（R）：其中由持牌银行持有的 EFBN，右轴单位 HK$ billion，用于观察银行体系持有的高流动性港元资产规模。<br><br><b>读取提示：</b>5-2 改为 HKMA 每日数据；Opening 与 Closing 的差异反映当日总结余变化，Forecast T+1 提供前瞻信息，EFBN 两条线用于观察货币基础结构。',
    '<b>参数概念：</b><br>1. O/N HIBOR：隔夜港元银行同业拆息，反映最短端港元资金价格。<br>2. 3M HIBOR：3 个月港元银行同业拆息，用来观察更持续的港元融资成本。<br>3. HKMA Base Rate：香港金管局基本利率，是港元利率体系的重要政策参考。<br>4. O/N−3M Spread（R）：隔夜 HIBOR 减 3M HIBOR，右轴单位 bp；显著转正通常代表短端资金压力上升。',
    '<b>参数概念：</b><br>1. USD/HKD：每 1 美元对应的港元价格；向 7.85 上升表示港元转弱，向 7.75 下降表示港元转强。<br>2. Strong-side CU 7.75：联系汇率制度下强方兑换保证。<br>3. Linked Rate Center 7.80：7.75–7.85 兑换保证区间的中点参考线，用于快速判断港元当前处在偏强侧还是偏弱侧；不是额外的兑换保证触发水平。<br>4. Weak-side CU 7.85：联系汇率制度下弱方兑换保证。<br>5. HKEX Price（R）：港交所 0388.HK 月末收盘价，右轴单位 HKD。<br>6. HSTECH Index（R）：恒生科技指数 HSTECH.HK 月末指数点位，右轴单位 points。<br><br><b>读取提示：</b>灰色淡色区域表示 7.75–7.85 联系汇率兑换保证区间；7.80 为区间中点参考。市场价格水平用于对照汇率位置与香港风险资产表现。',
]

def show_hk_parameter_description(index):
    st.markdown(f'<div class="mini-description">{HK_PARAMETER_DESCRIPTIONS[index]}</div>', unsafe_allow_html=True)

compact_mode = False

def render_core_charts():
    st.markdown('<div class="section-title">US monetary policy, Treasury yields and inflation expectations</div>', unsafe_allow_html=True)

    configs = [
        ('<div class="section-title">🏦 1. Fed Policy Rate & Money Market</div>', '<div class="section-description">IORB / ON RRP Rate / EFFR / SOFR</div>', "normal_corridor_range", build_fig1, [("IORB (IORB)", "https://fred.stlouisfed.org/series/IORB"), ("ON RRP Rate (RRPONTSYAWARD)", "https://fred.stlouisfed.org/series/RRPONTSYAWARD"), ("EFFR (EFFR)", "https://fred.stlouisfed.org/series/EFFR"), ("SOFR (SOFR)", "https://fred.stlouisfed.org/series/SOFR")], 0),
        ('<div class="section-title">2. 10Y Yield Structure</div>', '<div class="section-description">10Y Nominal / 10Y Real (R) / 10Y Breakeven (R)</div>', "normal_yield10_range", build_fig2, [("10Y Nominal (DGS10)", "https://fred.stlouisfed.org/series/DGS10"), ("10Y Real (DFII10)", "https://fred.stlouisfed.org/series/DFII10"), ("10Y Breakeven (T10YIE)", "https://fred.stlouisfed.org/series/T10YIE")], 1),
        ('<div class="section-title">3. Treasury Yield & Curve Spread</div>', '<div class="section-description">3M / 2Y / 10Y / 10Y−2Y (R) / 10Y−3M (R)</div>', "normal_treasury_range", build_fig3, [("3M Treasury (DGS3MO)", "https://fred.stlouisfed.org/series/DGS3MO"), ("2Y Treasury (DGS2)", "https://fred.stlouisfed.org/series/DGS2"), ("10Y Nominal (DGS10)", "https://fred.stlouisfed.org/series/DGS10"), ("10Y−2Y Spread (T10Y2Y)", "https://fred.stlouisfed.org/series/T10Y2Y"), ("10Y−3M Spread (T10Y3M)", "https://fred.stlouisfed.org/series/T10Y3M")], 2),
        ('<div class="section-title">4. US Liquidity</div>', '<div class="section-description">Net Liquidity / Reserve Balances / TGA / ON RRP</div>', "normal_liquidity_range", build_fig4, [("Reserve Balances (WRESBAL)", "https://fred.stlouisfed.org/series/WRESBAL"), ("TGA (WTREGEN)", "https://fred.stlouisfed.org/series/WTREGEN"), ("ON RRP Balance (RRPONTSYD)", "https://fred.stlouisfed.org/series/RRPONTSYD")], 3),
    ]

    for title, description, key, builder, sources, desc_index in configs:
        st.markdown(title, unsafe_allow_html=True)
        st.markdown(description, unsafe_allow_html=True)
        date_range = st.radio("时间范围", RANGES, horizontal=True, index=1, key=key, label_visibility="collapsed")
        st.plotly_chart(builder(date_range), use_container_width=True, config=PLOTLY_CONFIG)
        show_parameter_description(desc_index)
        add_sources(sources)
        st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)

    st.markdown('<div class="section-title">5. Hong Kong Liquidity</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-description">Money supply / HKEX price & HSTECH index / Daily banking liquidity & EFBN / HIBOR / USD-HKD / 7.75–7.85 LERS band</div>', unsafe_allow_html=True)
    # Build the full data set once; each 5-x panel controls only its own visible X-axis window.
    hk_figures = build_fig5("5Y")
    hk_range_keys = [
        "hk_5_1_range",
        "hk_5_2_range",
        "hk_5_3_range",
        "hk_5_4_range",
    ]
    for hk_index, hk_figure in enumerate(hk_figures):
        hk_range = st.radio(
            "时间范围",
            RANGES,
            horizontal=True,
            index=1,
            key=hk_range_keys[hk_index],
            label_visibility="collapsed",
        )
        st.plotly_chart(
            apply_hk_chart_range(hk_figure, hk_range),
            use_container_width=True,
            config=PLOTLY_CONFIG,
        )
        show_hk_parameter_description(hk_index)
        if hk_index < len(hk_figures) - 1:
            st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)
    add_sources([
        ("HKMA Monetary Statistics", "https://apidocs.hkma.gov.hk/documentation/market-data-and-statistics/monthly-statistical-bulletin/financial/monetary-statistics/"),
        ("HKMA Daily Interbank Liquidity", "https://apidocs.hkma.gov.hk/documentation/market-data-and-statistics/daily-monetary-statistics/daily-figures-interbank-liquidity/"),
        ("HKMA Daily Monetary Base", "https://apidocs.hkma.gov.hk/documentation/market-data-and-statistics/daily-monetary-statistics/daily-figures-monetary-base/"),
        ("HKMA Open API", "https://apidocs.hkma.gov.hk/"),
        ("Yahoo Finance Market Data", "https://finance.yahoo.com/"),
    ])

st.markdown('<div id="macro-charts" class="section-anchor"></div><div class="section-kicker">MACRO CHARTS</div>', unsafe_allow_html=True)
render_core_charts()
st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)

st.markdown('<div id="news" class="section-anchor"></div><div class="section-kicker">NEWS</div>', unsafe_allow_html=True)
st.markdown('<div class="section-title">📰 7×24 重点财经快讯</div>', unsafe_allow_html=True)
st.markdown('<div class="section-description">东方财富「红字焦点快讯」 · 平台已筛选重点 · 每60秒自动刷新</div>', unsafe_allow_html=True)

def render_news_panel():
    _, action_col = st.columns([5, 1])
    with action_col:
        if st.button("🔄 立即刷新", key="refresh_7x24", use_container_width=True): get_sina_news.clear()
    news_items, news_error = get_sina_news(limit=50)
    if news_items:
        st.markdown(f'<div class="news-status">当前显示 {len(news_items)} 条 · 来源：东方财富红字焦点快讯 · 60秒自动刷新</div>', unsafe_allow_html=True); news_html = '<div class="news-box">'
        for idx, item in enumerate(news_items, start=1):
            news_time = html.escape(str(item.get("time", ""))); news_title = html.escape(str(item.get("title", ""))); news_content = html.escape(str(item.get("content", ""))); news_url = html.escape(str(item.get("url", EASTMONEY_FOCUS_URL)), quote=True)
            if not news_url.startswith(("http://", "https://")): news_url = EASTMONEY_FOCUS_URL
            body = f"<strong>{news_title}</strong><div style=\"margin-top:3px;\">{news_content}</div>" if news_title and news_content and news_title != news_content else (news_content or news_title)
            news_html += f'<div class="news-item"><span class="news-index">{idx}.</span><span class="news-time">{news_time}</span><div class="news-content"><a href="{news_url}" target="_blank" rel="noopener noreferrer">{body}</a></div></div>'
        st.markdown(news_html + "</div>", unsafe_allow_html=True)
    else:
        st.warning("暂时无法取得东方财富红字焦点快讯。")
        if news_error: st.caption(f"错误：{news_error}")
    add_sources([("东方财富红字焦点快讯", EASTMONEY_FOCUS_URL)])

render_news_panel()
st.markdown(f'<div class="source-text">Source: <a href="{EASTMONEY_FOCUS_URL}" target="_blank" rel="noopener noreferrer">Eastmoney 7×24 Focus News</a></div>', unsafe_allow_html=True)
