from pathlib import Path
import re

APP = Path("app.py")
text = APP.read_text(encoding="utf-8")

import_anchor = "from macro_platform.us_equity_risk import load_vixeq_snapshot\n"
watchlist_import = "from macro_platform.watchlist_state import WATCHLIST_KEYS, decode_watchlists, encode_watchlists\n"
if watchlist_import not in text:
    if import_anchor not in text:
        raise RuntimeError("watchlist import anchor not found")
    text = text.replace(import_anchor, import_anchor + watchlist_import, 1)

old_state = '''def _load_watchlists():
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
'''
new_state = '''def _load_watchlists():
    if st.session_state.get("_watchlist_loaded"):
        return
    payload = decode_watchlists(st.query_params.get(WATCHLIST_PARAM, ""))
    for key in WATCHLIST_KEYS:
        st.session_state[f"{key}_confirmed"] = payload.get(key, [])
    st.session_state["_watchlist_loaded"] = True


def _save_watchlists():
    payload = {}
    for key in WATCHLIST_KEYS:
        items = st.session_state.get(f"{key}_confirmed", [])
        if isinstance(items, dict):
            items = [items]
        payload[key] = items if isinstance(items, list) else []
    # v2 is compressed + URL-safe and remains backward-compatible on load.
    st.query_params[WATCHLIST_PARAM] = encode_watchlists(payload)
'''
if old_state in text:
    text = text.replace(old_state, new_state, 1)
elif "decode_watchlists(st.query_params.get(WATCHLIST_PARAM" not in text:
    raise RuntimeError("watchlist state block not found")

quote_helper_anchor = '''def _empty_quote():
    return {"price": None, "change_pct": None, "market_state": "", "currency": "", "post_price": None, "post_change_pct": None, "pre_price": None, "pre_change_pct": None, "overnight_price": None, "overnight_change_pct": None, "regular_market_time": None, "post_market_time": None, "pre_market_time": None, "quote_source": "", "delayed_by": None, "data_source": ""}
'''
quote_helper = quote_helper_anchor + '''

YAHOO_CHART_BASES = (
    "https://query1.finance.yahoo.com/v8/finance/chart/",
    "https://query2.finance.yahoo.com/v8/finance/chart/",
)
YAHOO_QUOTE_URLS = (
    "https://query1.finance.yahoo.com/v7/finance/quote",
    "https://query2.finance.yahoo.com/v7/finance/quote",
)
YAHOO_SEARCH_URLS = (
    "https://query1.finance.yahoo.com/v1/finance/search",
    "https://query2.finance.yahoo.com/v1/finance/search",
)
'''
if "YAHOO_CHART_BASES =" not in text:
    if quote_helper_anchor not in text:
        raise RuntimeError("quote helper anchor not found")
    text = text.replace(quote_helper_anchor, quote_helper, 1)

pattern_overnight = re.compile(r'''def _get_yahoo_overnight_safe\(symbol, previous=None\):\n.*?\n    return None, None\n''', re.S)
new_overnight = '''def _get_yahoo_overnight_safe(symbol, previous=None):
    for url in YAHOO_QUOTE_URLS:
        try:
            response = requests.get(
                url,
                params={"symbols": symbol},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=3.5,
            )
            response.raise_for_status()
            rows = ((response.json() or {}).get("quoteResponse") or {}).get("result") or []
            if not rows:
                continue
            item = rows[0]
            price = item.get("overnightMarketPrice")
            pct = item.get("overnightChangePercent")
            if price is not None:
                if pct is None and previous not in (None, 0):
                    pct = (price - previous) / previous * 100
                return price, pct
        except Exception:
            continue
    return None, None
'''
if "for url in YAHOO_QUOTE_URLS:" not in text:
    text, count = pattern_overnight.subn(new_overnight, text, count=1)
    if count != 1:
        raise RuntimeError("Yahoo overnight function not found")

start = text.find("def _get_yahoo_quote_safe(symbol):")
end = text.find("\ndef _eastmoney_secid(symbol):", start)
if start < 0 or end < 0:
    raise RuntimeError("Yahoo quote function bounds not found")
if "for base in YAHOO_CHART_BASES:" not in text[start:end]:
    new_quote = '''def _get_yahoo_quote_safe(symbol):
    for base in YAHOO_CHART_BASES:
        try:
            response = requests.get(
                base + symbol,
                params={"range": "1d", "interval": "5m", "includePrePost": "true"},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=3.5,
            )
            response.raise_for_status()
            results = response.json().get("chart", {}).get("result") or []
            if not results:
                continue
            result = results[0]
            meta = result.get("meta", {})
            previous = meta.get("previousClose") or meta.get("regularMarketPreviousClose")
            price = meta.get("regularMarketPrice")
            pre_price = meta.get("preMarketPrice")
            post_price = meta.get("postMarketPrice")
            regular_change_pct = meta.get("regularMarketChangePercent")
            post_change_pct = meta.get("postMarketChangePercent")
            pre_change_pct = meta.get("preMarketChangePercent")
            periods = meta.get("currentTradingPeriod") or {}
            pre_period = periods.get("pre") or {}
            regular_period = periods.get("regular") or {}
            post_period = periods.get("post") or {}
            timestamps = result.get("timestamp") or []
            closes = ((result.get("indicators", {}).get("quote") or [{}])[0]).get("close") or []

            def _last_close_in_period(period):
                period_start, period_end = period.get("start"), period.get("end")
                if period_start is None:
                    return None
                values = [
                    close for ts, close in zip(timestamps, closes)
                    if close is not None and ts >= period_start and (period_end is None or ts <= period_end)
                ]
                return values[-1] if values else None

            if price is None:
                price = _last_close_in_period(regular_period) or next((v for v in reversed(closes) if v is not None), None)
            if pre_price is None:
                pre_price = _last_close_in_period(pre_period)
            if post_price is None:
                post_price = _last_close_in_period(post_period)
            if regular_change_pct is None and price is not None and previous not in (None, 0):
                regular_change_pct = (price - previous) / previous * 100
            if post_change_pct is None and post_price is not None and previous not in (None, 0):
                post_change_pct = (post_price - previous) / previous * 100
            if pre_change_pct is None and pre_price is not None and previous not in (None, 0):
                pre_change_pct = (pre_price - previous) / previous * 100
            overnight_price, overnight_change_pct = _get_yahoo_overnight_safe(symbol, previous)
            row = _empty_quote()
            row.update({
                "price": price,
                "change_pct": regular_change_pct,
                "market_state": meta.get("marketState", ""),
                "currency": meta.get("currency", ""),
                "post_price": post_price,
                "post_change_pct": post_change_pct,
                "pre_price": pre_price,
                "pre_change_pct": pre_change_pct,
                "overnight_price": overnight_price,
                "overnight_change_pct": overnight_change_pct,
                "regular_market_time": meta.get("regularMarketTime"),
                "post_market_time": meta.get("postMarketTime"),
                "pre_market_time": meta.get("preMarketTime"),
                "quote_source": meta.get("quoteSourceName", ""),
                "delayed_by": meta.get("exchangeDataDelayedBy"),
                "data_source": "Yahoo Finance",
            })
            if row.get("price") is not None:
                return row
        except Exception:
            continue
    return _empty_quote()
'''
    text = text[:start] + new_quote + text[end:]

old_watchlist_quote = '''@st.cache_data(ttl=60, show_spinner=False)
def _get_watchlist_quote(symbol): return _get_yahoo_quote_safe(symbol)
'''
new_watchlist_quote = '''@st.cache_resource(show_spinner=False)
def _last_good_quote_store():
    return {}


def _stable_quote(symbol, refresh_key=0):
    row = _get_cached_quote(symbol, refresh_key)
    store = _last_good_quote_store()
    cache_key = str(symbol or "").upper().strip()
    if row.get("price") is not None:
        saved = dict(row)
        saved["_stale"] = False
        saved["_cached_at"] = time.time()
        store[cache_key] = saved
        return saved
    previous = store.get(cache_key)
    if isinstance(previous, dict) and previous.get("price") is not None:
        stale = dict(previous)
        stale["_stale"] = True
        return stale
    return row


def _get_watchlist_quote(symbol):
    manual_key = st.session_state.get("_watchlist_refresh_key", 0)
    return _stable_quote(symbol, f"{_quote_refresh_key()}:{manual_key}")
'''
if old_watchlist_quote in text:
    text = text.replace(old_watchlist_quote, new_watchlist_quote, 1)
elif "def _stable_quote(symbol" not in text:
    raise RuntimeError("watchlist quote function not found")

# Market overview should get the same last-known-good protection as watchlist cards.
old_snapshot = '''snapshot = {"nasdaq": _get_cached_quote("^IXIC", refresh_key), "sp500": _get_cached_quote("^GSPC", refresh_key), "dow": _get_cached_quote("^DJI", refresh_key), "hsi": _get_cached_quote("^HSI", refresh_key), "hstech": _get_cached_quote("HSTECH.HK", refresh_key), "sh": _get_cached_quote("000001.SS", refresh_key), "sz": _get_cached_quote("399001.SZ", refresh_key), "csi300": _get_cached_quote("000300.SS", refresh_key)}'''
new_snapshot = '''snapshot = {"nasdaq": _stable_quote("^IXIC", refresh_key), "sp500": _stable_quote("^GSPC", refresh_key), "dow": _stable_quote("^DJI", refresh_key), "hsi": _stable_quote("^HSI", refresh_key), "hstech": _stable_quote("HSTECH.HK", refresh_key), "sh": _stable_quote("000001.SS", refresh_key), "sz": _stable_quote("399001.SZ", refresh_key), "csi300": _stable_quote("000300.SS", refresh_key)}'''
if old_snapshot in text:
    text = text.replace(old_snapshot, new_snapshot, 1)
elif '_stable_quote("^IXIC"' not in text:
    raise RuntimeError("market overview snapshot block not found")

# Expose when a retained last-good quote is being shown instead of turning the card blank.
old_source = '''source = row.get("data_source") or row.get("quote_source") or ""; delay = row.get("delayed_by"); source_text = f"{source} · 延迟{delay}分" if delay not in (None, 0, "0") and source == "Yahoo Finance" else source'''
new_source = '''source = row.get("data_source") or row.get("quote_source") or ""; delay = row.get("delayed_by"); source_text = f"{source} · 延迟{delay}分" if delay not in (None, 0, "0") and source == "Yahoo Finance" else source
    if row.get("_stale"): source_text = (source_text + " · 上次有效报价").strip(" ·")'''
if old_source in text:
    text = text.replace(old_source, new_source, 1)

# Manual refresh now clears the actual source cache; _get_watchlist_quote is intentionally uncached.
text = text.replace('''_get_watchlist_quote.clear(); st.session_state["_watchlist_refresh_key"] = st.session_state.get("_watchlist_refresh_key", 0) + 1''', '''_get_cached_quote.clear(); st.session_state["_watchlist_refresh_key"] = st.session_state.get("_watchlist_refresh_key", 0) + 1''')

# Make Yahoo symbol search tolerate one Yahoo host being blocked/rate-limited.
search_start = text.find("@st.cache_data(ttl=20, show_spinner=False)\ndef _search_yahoo(market, query):")
search_end = text.find("\ndef _render_quote_block(item):", search_start)
if search_start < 0 or search_end < 0:
    raise RuntimeError("Yahoo search function bounds not found")
if "for search_url in YAHOO_SEARCH_URLS:" not in text[search_start:search_end]:
    new_search = '''@st.cache_data(ttl=20, show_spinner=False)
def _search_yahoo(market, query):
    query = str(query or "").strip()
    if not query:
        return []
    quotes = []
    for search_url in YAHOO_SEARCH_URLS:
        try:
            response = requests.get(
                search_url,
                params={"q": query, "quotesCount": 10, "newsCount": 0},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=3.5,
            )
            response.raise_for_status()
            quotes = response.json().get("quotes") or []
            if quotes:
                break
        except Exception:
            continue
    results = []
    for item in quotes:
        if item.get("quoteType") != "EQUITY":
            continue
        symbol = str(item.get("symbol") or "")
        if market == "US" and ("." in symbol or symbol.endswith(("=F", "=X"))):
            continue
        if market == "HK" and not symbol.upper().endswith(".HK"):
            continue
        if market == "CN" and not symbol.upper().endswith((".SS", ".SZ")):
            continue
        results.append({
            "symbol": symbol,
            "name": item.get("longname") or item.get("shortname") or symbol,
            "exchange": item.get("exchange") or item.get("exchDisp") or "",
        })
    return results[:6]
'''
    text = text[:search_start] + new_search + text[search_end:]

APP.write_text(text, encoding="utf-8")
print("stabilized watchlist persistence and quote fallbacks")
