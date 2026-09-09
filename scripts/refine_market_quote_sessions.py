from pathlib import Path
import re

path = Path('app.py')
text = path.read_text(encoding='utf-8')

# Imports for reliable US Eastern-session selection.
if 'from datetime import datetime' not in text:
    text = text.replace('import time\n', 'import time\nfrom datetime import datetime\nfrom zoneinfo import ZoneInfo\n', 1)

# Extend the quote model with an overnight timestamp.
text = text.replace(
    '"overnight_price": None, "overnight_change_pct": None, "regular_market_time": None,',
    '"overnight_price": None, "overnight_change_pct": None, "overnight_market_time": None, "regular_market_time": None,',
)

# Robust overnight quote parser: accept both observed Yahoo field spellings.
pattern = re.compile(r'def _get_yahoo_overnight_safe\(symbol, previous=None\):.*?\n\ndef _get_yahoo_quote_safe', re.S)
replacement = '''def _get_yahoo_overnight_safe(symbol, previous=None):
    try:
        response = requests.get(
            "https://query1.finance.yahoo.com/v7/finance/quote",
            params={"symbols": symbol},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=2.5,
        )
        response.raise_for_status()
        rows = ((response.json() or {}).get("quoteResponse") or {}).get("result") or []
        if rows:
            item = rows[0]
            price = item.get("overnightMarketPrice")
            pct = item.get("overnightMarketChangePercent")
            if pct is None:
                pct = item.get("overnightChangePercent")
            overnight_time = item.get("overnightMarketTime")
            if price is not None:
                if pct is None and previous not in (None, 0):
                    pct = (price - previous) / previous * 100
                return price, pct, overnight_time
    except Exception:
        pass
    return None, None, None


def _get_yahoo_quote_safe'''
text, count = pattern.subn(replacement, text, count=1)
if count != 1:
    raise SystemExit('Could not replace _get_yahoo_overnight_safe')

text = text.replace(
    'overnight_price, overnight_change_pct = _get_yahoo_overnight_safe(symbol, previous)',
    'overnight_price, overnight_change_pct, overnight_market_time = _get_yahoo_overnight_safe(symbol, previous)',
)
text = text.replace(
    '"overnight_price": overnight_price, "overnight_change_pct": overnight_change_pct, "regular_market_time": meta.get("regularMarketTime")',
    '"overnight_price": overnight_price, "overnight_change_pct": overnight_change_pct, "overnight_market_time": overnight_market_time, "regular_market_time": meta.get("regularMarketTime")',
)

# Eastmoney is the authoritative runtime route for HK/A dashboard quotes.
pattern = re.compile(r'@st.cache_data\(ttl=60, show_spinner=False\)\ndef _get_cached_quote\(symbol, refresh_key=0\):.*?@st.cache_data\(ttl=60, show_spinner=False\)\ndef _get_watchlist_quote\(symbol\): return _get_yahoo_quote_safe\(symbol\)', re.S)
replacement = '''@st.cache_data(ttl=30, show_spinner=False)
def _get_cached_quote(symbol, refresh_key=0):
    raw = str(symbol).upper()
    if raw.endswith((".SS", ".SZ", ".HK")) or raw in ("^HSI", "^HSTECH"):
        # HK/A: use the live Eastmoney route only. Do not silently fall back to a delayed Yahoo quote.
        return _get_eastmoney_quote_safe(symbol)
    return _get_yahoo_quote_safe(symbol)


def _quote_refresh_key(): return int(time.time() // 30)


def _quote_meta(row, market=""):
    source = row.get("data_source") or row.get("quote_source") or ""; delayed = row.get("delayed_by"); state = _market_state_text(row); parts = [state] if state else []
    if delayed not in (None, 0, "0") and source == "Yahoo Finance": parts.append(f"延迟{delayed}分")
    elif source: parts.append(source)
    return " · ".join(parts)


@st.cache_data(ttl=30, show_spinner=False)
def _get_watchlist_quote(symbol, market=""):
    market = str(market or "").upper()
    if market in ("HK", "CN"):
        return _get_eastmoney_quote_safe(symbol)
    return _get_yahoo_quote_safe(symbol)'''
text, count = pattern.subn(replacement, text, count=1)
if count != 1:
    raise SystemExit('Could not replace quote routing block')

# Session selection helpers and quote-card rendering.
pattern = re.compile(r'def _render_quote_block\(item\):.*?\n\ndef _add_confirmed', re.S)
replacement = '''def _is_us_overnight_now():
    try:
        hour = datetime.now(ZoneInfo("America/New_York")).hour
        return hour >= 20 or hour < 4
    except Exception:
        return False


def _select_us_session_quote(row):
    state = str(row.get("market_state") or "").upper()
    regular_price, regular_change = row.get("price"), row.get("change_pct")
    overnight_price, overnight_change = row.get("overnight_price"), row.get("overnight_change_pct")
    pre_price, pre_change = row.get("pre_price"), row.get("pre_change_pct")
    post_price, post_change = row.get("post_price"), row.get("post_change_pct")

    # 20:00-04:00 ET: prefer Yahoo's dedicated overnight field whenever available.
    if overnight_price is not None and (_is_us_overnight_now() or state in ("POSTPOST", "CLOSED")):
        return overnight_price, overnight_change, "夜盘"
    if state in ("PRE", "PREPRE") and pre_price is not None:
        return pre_price, pre_change, "盘前"
    if state == "POST" and post_price is not None:
        return post_price, post_change, "盘后"
    if state == "REGULAR":
        return regular_price, regular_change, "交易中"
    return regular_price, regular_change, "休市" if state == "CLOSED" else _market_state_text(row)


def _render_quote_block(item):
    market = str(item.get("market") or "").upper()
    row = _get_watchlist_quote(item["symbol"], market)

    if market == "US":
        price, change, session_label = _select_us_session_quote(row)
        regular_context = ""
        if session_label in ("夜盘", "盘前", "盘后") and row.get("price") is not None:
            regular_context = f'<div class="search-after">常规盘：<strong>{row["price"]:,.2f}</strong></div>'
    else:
        # HK/A: latest live-market quote only; no pre/post/overnight session substitution.
        price, change = row.get("price"), row.get("change_pct")
        session_label = "最新"
        regular_context = ""

    price_text = "--" if price is None else f"{price:,.2f}"
    change_text = "数据暂缺" if price is None else ("--" if change is None else f"{change:+.2f}%")
    source = row.get("data_source") or row.get("quote_source") or ""
    delay = row.get("delayed_by")
    source_text = f"{source} · 延迟{delay}分" if delay not in (None, 0, "0") and source == "Yahoo Finance" else source
    return f'<div class="search-result"><div class="search-result-label">{html.escape(item["name"])} <span class="search-result-symbol">· {html.escape(item["symbol"])} · {html.escape(item.get("exchange", ""))}</span></div><div class="search-price">{html.escape(price_text)} <span class="market-change">{html.escape(change_text)} {html.escape(session_label)}</span></div>{regular_context}<div class="search-hint">{html.escape(source_text)}</div></div>'


def _add_confirmed'''
text, count = pattern.subn(replacement, text, count=1)
if count != 1:
    raise SystemExit('Could not replace _render_quote_block')

# Refresh cadence: closer to live without excessive rate pressure.
text = text.replace('@st.fragment(run_every="60s")\ndef render_watchlists():', '@st.fragment(run_every="30s")\ndef render_watchlists():')
text = text.replace('行情模块每 60 秒刷新', '行情模块每 30 秒刷新')

# Make overview itself auto-refresh and align its snapshot gate with the cache.
if '@st.fragment(run_every="30s")\ndef render_market_groups():' not in text:
    text = text.replace('def render_market_groups():', '@st.fragment(run_every="30s")\ndef render_market_groups():', 1)
text = text.replace('now - snapshot_time >= 60', 'now - snapshot_time >= 30')

# Update state mapping for Yahoo's extended-state values.
text = text.replace(
    'def _market_state_text(row): return {"REGULAR": "交易中", "PRE": "盘前", "POST": "盘后", "CLOSED": "休市"}.get(row.get("market_state") or "", "")',
    'def _market_state_text(row): return {"REGULAR": "交易中", "PRE": "盘前", "PREPRE": "盘前", "POST": "盘后", "POSTPOST": "夜盘", "CLOSED": "休市"}.get(row.get("market_state") or "", "")',
)

path.write_text(text, encoding='utf-8')
print('Updated market quote routing and US overnight session display')
