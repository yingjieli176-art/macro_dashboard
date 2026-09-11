from pathlib import Path
import re

APP = Path("app.py")
text = APP.read_text(encoding="utf-8")

# Add a separate Tencent intraday endpoint and explicit freshness target.
text = text.replace(
    'TENCENT_QUOTE_URL = "https://qt.gtimg.cn/q="\n',
    'TENCENT_QUOTE_URL = "https://qt.gtimg.cn/q="\n'
    'TENCENT_MINUTE_URL = "https://web.ifzq.gtimg.cn/appstock/app/minute/query"\n'
    'DIRECT_QUOTE_FRESH_SECONDS = 90\n',
    1,
)

new_tencent = r'''def _get_tencent_quote_safe(symbol):
    code = _tencent_quote_code(symbol)
    if not code:
        return _empty_quote()
    market = _symbol_market(symbol)
    # The public Tencent quote endpoint is CDN-backed. Add a cache-buster and
    # no-cache headers so Streamlit Cloud does not repeatedly receive an old
    # edge response during the trading session.
    endpoints = (TENCENT_QUOTE_URL, TENCENT_QUOTE_URL.replace("https://", "http://", 1))
    for endpoint in endpoints:
        try:
            response = requests.get(
                endpoint + code + f"&_={int(time.time() * 1000)}",
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Referer": "https://finance.qq.com/",
                    "Cache-Control": "no-cache, no-store, max-age=0",
                    "Pragma": "no-cache",
                },
                timeout=2.5,
            )
            response.raise_for_status()
            raw = response.content.decode("gbk", errors="ignore")
            if '="' not in raw:
                continue
            payload = raw.split('="', 1)[1].split('"', 1)[0]
            fields = payload.split("~")
            if len(fields) < 33:
                continue
            try:
                price = float(fields[3])
            except (TypeError, ValueError):
                continue
            try:
                change_pct = float(fields[32])
            except (TypeError, ValueError):
                change_pct = None
            quote_time = _parse_tencent_quote_time(fields[30], market)
            currency = {"US": "USD", "HK": "HKD", "CN": "CNY"}.get(market, "")
            row = _empty_quote()
            row.update({
                "price": price,
                "change_pct": change_pct,
                "market_state": "",
                "currency": currency,
                "regular_market_time": quote_time,
                "quote_source": "Tencent Finance",
                "delayed_by": 0,
                "data_source": "腾讯实时行情",
            })
            return row
        except Exception:
            continue
    return _empty_quote()


def _parse_asia_minute_timestamp(date_value, time_value):
    date_raw = str(date_value or "").strip()
    time_raw = str(time_value or "").strip().replace(":", "")
    if not date_raw or len(time_raw) < 4:
        return None
    for date_fmt in ("%Y%m%d", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            day = datetime.strptime(date_raw, date_fmt).date()
            hour = int(time_raw[:2])
            minute = int(time_raw[2:4])
            second = int(time_raw[4:6]) if len(time_raw) >= 6 else 0
            return datetime(day.year, day.month, day.day, hour, minute, second, tzinfo=DASHBOARD_TZ).timestamp()
        except (ValueError, TypeError):
            continue
    return None


def _get_tencent_minute_quote_safe(symbol):
    """Independent intraday fallback for HK/A shares when quote snapshots lag."""
    market = _symbol_market(symbol)
    code = _tencent_quote_code(symbol)
    if market not in {"HK", "CN"} or not code:
        return _empty_quote()
    try:
        var_name = f"min_data_{code}"
        response = requests.get(
            TENCENT_MINUTE_URL,
            params={"_var": var_name, "code": code, "r": f"{time.time():.6f}"},
            headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://gu.qq.com/",
                "Cache-Control": "no-cache, no-store, max-age=0",
                "Pragma": "no-cache",
            },
            timeout=3.0,
        )
        response.raise_for_status()
        body = response.text.strip()
        if "=" in body:
            body = body.split("=", 1)[1].strip().rstrip(";")
        payload = json.loads(body)
        stock = ((payload.get("data") or {}).get(code) or {})
        qt = ((stock.get("qt") or {}).get(code) or [])
        minute_block = stock.get("data") or {}
        rows = minute_block.get("data") or []
        date_value = minute_block.get("date") or ""

        price = None
        quote_time = None
        if rows:
            parts = str(rows[-1]).split()
            if len(parts) >= 2:
                try:
                    price = float(parts[1])
                except (TypeError, ValueError):
                    price = None
                quote_time = _parse_asia_minute_timestamp(date_value, parts[0])
        if price is None and len(qt) > 3:
            try:
                price = float(qt[3])
            except (TypeError, ValueError):
                price = None
        if price is None:
            return _empty_quote()

        previous = None
        if len(qt) > 4:
            try:
                previous = float(qt[4])
            except (TypeError, ValueError):
                previous = None
        change_pct = None if previous in (None, 0) else (price - previous) / previous * 100.0
        row = _empty_quote()
        row.update({
            "price": price,
            "change_pct": change_pct,
            "market_state": "REGULAR",
            "currency": "HKD" if market == "HK" else "CNY",
            "regular_market_time": quote_time,
            "quote_source": "Tencent Intraday",
            "delayed_by": 0,
            "data_source": "腾讯分时行情",
        })
        return row
    except Exception:
        return _empty_quote()
'''

text, n = re.subn(
    r'def _get_tencent_quote_safe\(symbol\):.*?\n\ndef _quote_regular_age_seconds',
    new_tencent + '\n\ndef _quote_regular_age_seconds',
    text,
    count=1,
    flags=re.S,
)
if n != 1:
    raise RuntimeError("Tencent quote block not found")

new_eastmoney = r'''def _get_eastmoney_quote_safe(symbol):
    secid = _eastmoney_secid(symbol)
    if not secid:
        return _empty_quote()
    try:
        response = requests.get(
            EASTMONEY_QUOTE_URL,
            params={
                "secid": secid,
                "fields": "f43,f57,f58,f169,f170,f46,f44,f45,f47,f48,f60,f86",
                "ut": EASTMONEY_UT,
                "fltt": "2",
                "invt": "2",
                "_": int(time.time() * 1000),
            },
            headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://quote.eastmoney.com/",
                "Cache-Control": "no-cache, no-store, max-age=0",
                "Pragma": "no-cache",
            },
            timeout=2.5,
        )
        response.raise_for_status()
        data = (response.json() or {}).get("data") or {}
        if not data:
            return _empty_quote()
        price_raw, prev_raw, pct_raw = data.get("f43"), data.get("f60"), data.get("f170")
        if price_raw in (None, "-", ""):
            return _empty_quote()
        price = float(price_raw)
        previous = None if prev_raw in (None, "-") else float(prev_raw)
        change_pct = None if pct_raw in (None, "-") else float(pct_raw)
        if change_pct is None and previous not in (None, 0):
            change_pct = (price - previous) / previous * 100
        return {
            "price": price,
            "change_pct": change_pct,
            "market_state": "REGULAR",
            "currency": "HKD" if str(symbol).upper().endswith(".HK") or str(symbol).upper() in ("^HSI", "^HSTECH", "HSTECH.HK") else "CNY",
            "post_price": None,
            "post_change_pct": None,
            "pre_price": None,
            "pre_change_pct": None,
            "overnight_price": None,
            "overnight_change_pct": None,
            "regular_market_time": data.get("f86"),
            "post_market_time": None,
            "pre_market_time": None,
            "quote_source": "Eastmoney",
            "delayed_by": 0,
            "data_source": "东方财富实时行情",
        }
    except Exception:
        return _empty_quote()
'''
text, n = re.subn(
    r'def _get_eastmoney_quote_safe\(symbol\):.*?\n\ndef _valid_market_timestamp',
    new_eastmoney + '\n\ndef _valid_market_timestamp',
    text,
    count=1,
    flags=re.S,
)
if n != 1:
    raise RuntimeError("Eastmoney quote block not found")

new_cached = r'''@st.cache_data(ttl=15, show_spinner=False)
def _get_cached_quote(symbol, refresh_key=0):
    market = _symbol_market(symbol)
    candidates = []

    # HK/A: Tencent and Eastmoney are peers. Always query both during the
    # trading session and choose the newest timestamp instead of accepting a
    # merely "less than 8 minutes old" Tencent snapshot. If both snapshots are
    # stale, query Tencent's independent intraday feed before falling back to
    # Yahoo (which can itself be delayed for Asian markets).
    if market in {"HK", "CN"}:
        for getter in (_get_tencent_quote_safe, _get_eastmoney_quote_safe):
            row = getter(symbol)
            if row.get("price") is not None:
                candidates.append(_tag_quote_role(row, "direct"))

        best = _newest_quote(candidates)
        best_age = _quote_regular_age_seconds(best) if best.get("price") is not None else None
        if _regular_session_now(market) and (
            best.get("price") is None or best_age is None or best_age > DIRECT_QUOTE_FRESH_SECONDS
        ):
            minute_row = _get_tencent_minute_quote_safe(symbol)
            if minute_row.get("price") is not None:
                candidates.append(_tag_quote_role(minute_row, "direct"))
                best = _newest_quote(candidates)
                best_age = _quote_regular_age_seconds(best)

        if best.get("price") is not None and (
            not _regular_session_now(market)
            or (best_age is not None and best_age <= 3 * 60)
        ):
            return best

        yahoo = _get_yahoo_quote_safe(symbol)
        if yahoo.get("price") is not None:
            candidates.append(_tag_quote_role(yahoo, "fallback"))
        return _newest_quote(candidates)

    # US regular session: Tencent first to reduce Yahoo delay. Outside regular
    # hours Yahoo remains first because it can expose pre/post/overnight fields.
    if _regular_session_now("US"):
        tencent = _get_tencent_quote_safe(symbol)
        if tencent.get("price") is not None:
            tagged = _tag_quote_role(tencent, "primary")
            candidates.append(tagged)
            age = _quote_regular_age_seconds(tagged)
            if age is not None and age <= 8 * 60:
                return tagged
        yahoo = _get_yahoo_quote_safe(symbol)
        if yahoo.get("price") is not None:
            candidates.append(_tag_quote_role(yahoo, "fallback"))
        return _newest_quote(candidates)

    yahoo = _get_yahoo_quote_safe(symbol)
    if yahoo.get("price") is not None:
        return _tag_quote_role(yahoo, "extended")
    tencent = _get_tencent_quote_safe(symbol)
    if tencent.get("price") is not None:
        return _tag_quote_role(tencent, "fallback")
    return _empty_quote()
'''
text, n = re.subn(
    r'@st\.cache_data\(ttl=60, show_spinner=False\)\ndef _get_cached_quote\(symbol, refresh_key=0\):.*?\n\ndef _quote_refresh_key\(\): return int\(time\.time\(\) // 60\)',
    new_cached + '\n\ndef _quote_refresh_key(): return int(time.time() // 15)',
    text,
    count=1,
    flags=re.S,
)
if n != 1:
    raise RuntimeError("cached quote block not found")

# Surface actual freshness rather than treating anything under five minutes as
# equally acceptable during an active HK/A session.
old_age = '''    if _regular_session_now(market) and age is not None and age > 5:\n        parts.append(f"报价滞后约{int(round(age))}分")'''
new_age = '''    if _regular_session_now(market) and age is not None:\n        if market in {"HK", "CN"} and age <= DIRECT_QUOTE_FRESH_SECONDS / 60.0:\n            parts.append("近实时")\n        elif age > 2:\n            parts.append(f"报价滞后约{int(round(age))}分")'''
if old_age not in text:
    raise RuntimeError("quote freshness label block not found")
text = text.replace(old_age, new_age, 1)

# Refresh the two quote-driven modules every 15 seconds. News remains 60 sec.
text = text.replace(
    '@st.fragment(run_every="60s")\ndef render_market_overview():',
    '@st.fragment(run_every="15s")\ndef render_market_overview():',
    1,
)
text = text.replace(
    '@st.fragment(run_every="60s")\ndef render_watchlists():',
    '@st.fragment(run_every="15s")\ndef render_watchlists():',
    1,
)
text = text.replace(
    '主要指数行情带 · 当前价格 / 涨跌幅 / 市场状态 / 报价时间 · 60 秒刷新',
    '主要指数行情带 · 港/A 双源择新 + 分时兜底 · 15 秒刷新',
    1,
)
text = text.replace(
    '核心标的快速监控 · 港/A/美股正常盘优先低延时多源行情 · Yahoo 仅备用或美股扩展时段 · 60 秒自动刷新',
    '核心标的快速监控 · 港/A 腾讯 + 东方财富双源择新，分时兜底 · Yahoo 仅备用 · 15 秒自动刷新',
    1,
)

APP.write_text(text, encoding="utf-8")
print("Improved HK/A quote freshness: dual-source newest selection, minute fallback, 15s refresh.")
