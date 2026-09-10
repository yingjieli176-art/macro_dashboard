from pathlib import Path


APP = Path("app.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count == 0:
        if new in text:
            return text
        raise RuntimeError(f"patch target missing: {label}")
    if count != 1:
        raise RuntimeError(f"patch target not unique ({count}): {label}")
    return text.replace(old, new, 1)


def replace_between(text: str, start: str, end: str, new_block: str, label: str) -> str:
    start_i = text.find(start)
    if start_i < 0:
        if new_block.strip() in text:
            return text
        raise RuntimeError(f"patch start missing: {label}")
    end_i = text.find(end, start_i)
    if end_i < 0:
        raise RuntimeError(f"patch end missing: {label}")
    return text[:start_i] + new_block + text[end_i:]


text = APP.read_text(encoding="utf-8")

text = replace_once(
    text,
    'EASTMONEY_UT = "bd1d9ddb04089700cf9c27f4f4961f5b"\n',
    'EASTMONEY_UT = "bd1d9ddb04089700cf9c27f4f4961f5b"\nTENCENT_QUOTE_URL = "https://qt.gtimg.cn/q="\n',
    "Tencent quote endpoint",
)

anchor = '''YAHOO_SEARCH_URLS = (
    "https://query1.finance.yahoo.com/v1/finance/search",
    "https://query2.finance.yahoo.com/v1/finance/search",
)
'''
helpers = '''YAHOO_SEARCH_URLS = (
    "https://query1.finance.yahoo.com/v1/finance/search",
    "https://query2.finance.yahoo.com/v1/finance/search",
)


def _symbol_market(symbol):
    raw = str(symbol or "").upper().strip()
    if raw.endswith(".HK") or raw in {"^HSI", "^HSTECH", "HSTECH.HK"}:
        return "HK"
    if raw.endswith((".SS", ".SZ")):
        return "CN"
    return "US"


def _tencent_quote_code(symbol):
    raw = str(symbol or "").upper().strip()
    index_map = {
        "^HSI": "hkHSI",
        "^HSTECH": "hkHSTECH",
        "HSTECH.HK": "hkHSTECH",
        "^IXIC": "usIXIC",
        "^GSPC": "usINX",
        "^DJI": "usDJI",
        "^NDX": "usNDX",
    }
    if raw in index_map:
        return index_map[raw]
    if raw.endswith(".HK"):
        return "hk" + raw[:-3].zfill(5)
    if raw.endswith(".SS"):
        return "sh" + raw[:-3]
    if raw.endswith(".SZ"):
        return "sz" + raw[:-3]
    if raw and not raw.startswith("^") and "=" not in raw:
        return "us" + raw
    return ""


def _parse_tencent_quote_time(value, market):
    raw = str(value or "").strip()
    if not raw:
        return None
    formats = ("%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y%m%d%H%M%S")
    for fmt in formats:
        try:
            dt = datetime.strptime(raw, fmt)
            tz = ZoneInfo("America/New_York") if market == "US" else DASHBOARD_TZ
            return dt.replace(tzinfo=tz).timestamp()
        except ValueError:
            continue
    return None


def _get_tencent_quote_safe(symbol):
    code = _tencent_quote_code(symbol)
    if not code:
        return _empty_quote()
    market = _symbol_market(symbol)
    try:
        response = requests.get(
            TENCENT_QUOTE_URL + code,
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.qq.com/"},
            timeout=2.5,
        )
        response.raise_for_status()
        raw = response.content.decode("gbk", errors="ignore")
        if '=\"' not in raw:
            return _empty_quote()
        payload = raw.split('=\"', 1)[1].split('\"', 1)[0]
        fields = payload.split("~")
        if len(fields) < 33:
            return _empty_quote()
        try:
            price = float(fields[3])
        except (TypeError, ValueError):
            return _empty_quote()
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
            "delayed_by": None,
            "data_source": "腾讯行情",
        })
        return row
    except Exception:
        return _empty_quote()


def _quote_regular_age_seconds(row):
    ts = _valid_market_timestamp(row.get("regular_market_time"))
    if ts is None:
        return None
    return max(0.0, time.time() - ts)


def _asia_clock_state(market):
    now = datetime.now(DASHBOARD_TZ)
    if now.weekday() >= 5:
        return "休市"
    minute = now.hour * 60 + now.minute
    if market == "HK":
        if 570 <= minute < 720 or 780 <= minute < 960:
            return "交易中"
        if 720 <= minute < 780:
            return "午间休市"
        return "未开盘" if minute < 570 else "已收盘"
    if market == "CN":
        if 570 <= minute < 690 or 780 <= minute < 900:
            return "交易中"
        if 690 <= minute < 780:
            return "午间休市"
        return "未开盘" if minute < 570 else "已收盘"
    return ""


def _us_clock_state():
    ny = datetime.now(ZoneInfo("America/New_York"))
    minute = ny.hour * 60 + ny.minute
    if _us_overnight_window_now():
        return "夜盘时段 · 正常盘最近价"
    if ny.weekday() >= 5:
        return "休市"
    if 4 * 60 <= minute < 9 * 60 + 30:
        return "盘前时段 · 正常盘最近价"
    if 9 * 60 + 30 <= minute < 16 * 60:
        return "交易中"
    if 16 * 60 <= minute < 20 * 60:
        return "盘后时段 · 正常盘最近价"
    return "休市"


def _regular_session_now(market):
    market = str(market or "").upper()
    if market in {"HK", "CN"}:
        return _asia_clock_state(market) == "交易中"
    if market == "US":
        ny = datetime.now(ZoneInfo("America/New_York"))
        minute = ny.hour * 60 + ny.minute
        return ny.weekday() < 5 and 9 * 60 + 30 <= minute < 16 * 60
    return False


def _tag_quote_role(row, role):
    tagged = dict(row)
    tagged["_provider_role"] = role
    return tagged


def _newest_quote(rows):
    valid = [row for row in rows if isinstance(row, dict) and row.get("price") is not None]
    if not valid:
        return _empty_quote()
    def key(row):
        values = [
            _valid_market_timestamp(row.get("overnight_market_time")),
            _valid_market_timestamp(row.get("pre_market_time")),
            _valid_market_timestamp(row.get("post_market_time")),
            _valid_market_timestamp(row.get("regular_market_time")),
        ]
        return max((value for value in values if value is not None), default=0)
    return max(valid, key=key)
'''
text = replace_once(text, anchor, helpers, "quote provider helpers")

asia_block = '''def _asia_session_state(market, quote_time):
    clock_state = _asia_clock_state(market)
    ts = _valid_market_timestamp(quote_time)
    if ts is None:
        return clock_state
    quote_dt = datetime.fromtimestamp(ts, DASHBOARD_TZ)
    now = datetime.now(DASHBOARD_TZ)
    if clock_state == "交易中" and quote_dt.date() != now.date():
        return "交易时段 · 上次报价"
    return clock_state


'''
text = replace_between(
    text,
    "def _asia_session_state(market, quote_time):\n",
    "def _us_overnight_window_now():\n",
    asia_block,
    "Asia session state",
)

session_block = '''def _quote_session_context(row, market=""):
    market = str(market or "").upper()
    state = str(row.get("market_state") or "").upper()
    now_ts = time.time()

    if market == "US":
        regular_ts = _valid_market_timestamp(row.get("regular_market_time"))
        pre_ts = _valid_market_timestamp(row.get("pre_market_time"))
        post_ts = _valid_market_timestamp(row.get("post_market_time"))
        overnight_ts = _valid_market_timestamp(row.get("overnight_market_time"))
        overnight_fresh = (
            row.get("overnight_price") is not None
            and overnight_ts is not None
            and 0 <= now_ts - overnight_ts <= 18 * 3600
        )
        overnight_active = overnight_fresh and (
            state in {"PREPRE", "POSTPOST"} or (state == "CLOSED" and _us_overnight_window_now())
        )
        if overnight_active:
            return "夜盘", overnight_ts
        if state in {"PREPRE", "POSTPOST"}:
            return "夜盘时段 · 正常盘最近价", regular_ts
        if state == "PRE":
            if row.get("pre_price") is not None:
                return "盘前", pre_ts
            return "盘前时段 · 正常盘最近价", regular_ts
        if state == "REGULAR":
            return "交易中", regular_ts
        if state == "POST":
            if row.get("post_price") is not None:
                return "盘后", post_ts
            return "盘后时段 · 正常盘最近价", regular_ts
        if state == "CLOSED":
            if _us_overnight_window_now():
                return "夜盘时段 · 正常盘最近价", regular_ts
            candidates = [x for x in (post_ts, regular_ts) if x is not None]
            return "休市", max(candidates) if candidates else None
        candidates = [x for x in (overnight_ts, pre_ts, post_ts, regular_ts) if x is not None]
        return _us_clock_state(), max(candidates) if candidates else regular_ts

    quote_ts = _valid_market_timestamp(row.get("regular_market_time"))
    return _asia_session_state(market, quote_ts), quote_ts


'''
text = replace_between(
    text,
    "def _quote_session_context(row, market=\"\"):\n",
    "def _market_state_text(row, market=\"\"):\n",
    session_block,
    "quote session context",
)

cached_block = '''@st.cache_data(ttl=60, show_spinner=False)
def _get_cached_quote(symbol, refresh_key=0):
    market = _symbol_market(symbol)
    candidates = []

    # HK/CN: prefer Tencent's quote feed, then Eastmoney; Yahoo is last-resort.
    if market in {"HK", "CN"}:
        for getter, role in (
            (_get_tencent_quote_safe, "primary"),
            (_get_eastmoney_quote_safe, "secondary"),
        ):
            row = getter(symbol)
            if row.get("price") is None:
                continue
            tagged = _tag_quote_role(row, role)
            candidates.append(tagged)
            age = _quote_regular_age_seconds(tagged)
            if not _regular_session_now(market) or (age is not None and age <= 8 * 60):
                return tagged
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


def _quote_refresh_key(): return int(time.time() // 60)

'''
text = replace_between(
    text,
    "@st.cache_data(ttl=60, show_spinner=False)\ndef _get_cached_quote(symbol, refresh_key=0):\n",
    "def _quote_meta(row, market=\"\"):\n",
    cached_block,
    "cached quote provider order",
)

meta_block = '''def _quote_meta(row, market=""):
    market = str(market or "").upper()
    source = row.get("data_source") or row.get("quote_source") or ""
    delayed = row.get("delayed_by")
    role = row.get("_provider_role") or ""
    state, quote_ts = _quote_session_context(row, market)
    parts = [state] if state else []
    time_label = _market_time_label(quote_ts)
    parts.append(time_label if time_label else "时间暂缺")

    source_label = source
    if source_label:
        if role == "fallback":
            source_label += "（备用）"
        elif role == "secondary":
            source_label += "（次选）"
        elif role == "extended":
            source_label += "（扩展时段）"
        parts.append(source_label)

    if delayed not in (None, 0, "0") and source == "Yahoo Finance":
        parts.append(f"源标注延迟{delayed}分")

    age = None
    if quote_ts is not None:
        age = max(0.0, time.time() - quote_ts) / 60.0
    if _regular_session_now(market) and age is not None and age > 5:
        parts.append(f"报价滞后约{int(round(age))}分")
    if row.get("_stale"):
        parts.append("上次有效报价")
    return " · ".join(parts)

'''
text = replace_between(
    text,
    "def _quote_meta(row, market=\"\"):\n",
    "@st.cache_resource(show_spinner=False)\ndef _last_good_quote_store():\n",
    meta_block,
    "quote metadata",
)

text = text.replace(
    '<div class="section-title">自选观察</div><div class="section-description">核心标的快速监控 · 60 秒自动刷新 · 添加、删除后自动保存到当前链接</div>',
    '<div class="section-title">自选观察</div><div class="section-description">核心标的快速监控 · 港/A/美股正常盘优先低延时多源行情 · Yahoo 仅备用或美股扩展时段 · 60 秒自动刷新</div>',
)
text = text.replace(
    '<div class="watch-toolbar">默认组合已启用 · 行情失败时保留上次有效报价</div>',
    '<div class="watch-toolbar">多源行情按时效切换 · 行情失败时保留上次有效报价</div>',
)

if 'return "状态未知"' in text:
    raise RuntimeError('legacy unknown-state return remains in app.py')

APP.write_text(text, encoding="utf-8")
print("watchlist quote freshness patch applied")
