from pathlib import Path

path = Path('app.py')
text = path.read_text(encoding='utf-8')

text = text.replace(
    '.market-group { border: 1px solid #e5e7eb; border-radius: 8px; padding: 6px 8px 5px; background: #fff; min-width: 0; min-height: 82px; box-sizing: border-box; }',
    '.market-group { border: 1px solid #e5e7eb; border-radius: 8px; padding: 6px 8px 5px; background: #fff; min-width: 0; min-height: 96px; box-sizing: border-box; }'
)
text = text.replace(
    '.market-group-row { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 4px; min-height: 52px; align-items: start; }',
    '.market-group-row { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 4px; min-height: 66px; align-items: start; }'
)
text = text.replace(
    '.market-item { min-width: 0; height: 52px; min-height: 52px; max-height: 52px; padding-right: 4px; border-right: 1px solid #f0f0f0; box-sizing: border-box; overflow: hidden; }',
    '.market-item { min-width: 0; height: 66px; min-height: 66px; max-height: 66px; padding-right: 4px; border-right: 1px solid #f0f0f0; box-sizing: border-box; overflow: hidden; }'
)
text = text.replace(
    '.market-meta { color: #9ca3af; font-size: 0.68rem; margin-top: 1px; white-space: nowrap; }',
    '.market-meta { color: #9ca3af; font-size: 0.66rem; margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }'
)

old = '''def _market_state_text(row): return {"REGULAR": "交易中", "PRE": "盘前", "POST": "盘后", "CLOSED": "休市"}.get(row.get("market_state") or "", "")

def _market_item_html(name, price, change_pct, meta=""):
    price_text = "--" if price is None else f"{price:,.2f}"; change_text = "--" if change_pct is None else f"{change_pct:+.2f}%"
    return f'<div class="market-item"><div class="market-name">{html.escape(name)}</div><div class="market-price">{html.escape(price_text)}</div><div class="market-change">{html.escape(change_text)}</div><div class="market-meta">{html.escape(meta)}</div></div>'
'''
new = '''def _valid_market_timestamp(value):
    try:
        ts = float(value)
    except (TypeError, ValueError):
        return None
    # Some feeds may expose milliseconds; normalize to Unix seconds.
    if ts > 10_000_000_000:
        ts /= 1000.0
    # Never render epoch-zero / corrupt timestamps as market time.
    if ts < 946684800 or ts > time.time() + 6 * 3600:
        return None
    return ts


def _market_time_label(value):
    ts = _valid_market_timestamp(value)
    if ts is None:
        return ""
    dt = datetime.fromtimestamp(ts, DASHBOARD_TZ)
    now = datetime.now(DASHBOARD_TZ)
    if dt.date() == now.date():
        return dt.strftime("%H:%M HKT")
    return dt.strftime("%m-%d %H:%M HKT")


def _asia_session_state(market, quote_time):
    ts = _valid_market_timestamp(quote_time)
    if ts is None:
        return "状态未知"
    quote_dt = datetime.fromtimestamp(ts, DASHBOARD_TZ)
    now = datetime.now(DASHBOARD_TZ)
    # A stale prior-day quote on a weekend/holiday is not a live market.
    if quote_dt.date() != now.date() or now.weekday() >= 5:
        return "休市"
    minute = now.hour * 60 + now.minute
    if market == "HK":
        if 570 <= minute < 720 or 780 <= minute < 960:
            return "交易中"
        if 720 <= minute < 780:
            return "午间休市"
        return "未开盘" if minute < 570 else "休市"
    if market == "CN":
        if 570 <= minute < 690 or 780 <= minute < 900:
            return "交易中"
        if 690 <= minute < 780:
            return "午间休市"
        return "未开盘" if minute < 570 else "休市"
    return ""


def _quote_session_context(row, market=""):
    market = str(market or "").upper()
    state = str(row.get("market_state") or "").upper()
    now_ts = time.time()

    if market == "US":
        overnight_ts = _valid_market_timestamp(row.get("overnight_market_time"))
        overnight_fresh = (
            row.get("overnight_price") is not None
            and overnight_ts is not None
            and 0 <= now_ts - overnight_ts <= 18 * 3600
        )
        if state in {"PREPRE", "POSTPOST", "CLOSED"} and overnight_fresh:
            return "夜盘", overnight_ts
        if state == "PRE":
            return "盘前", _valid_market_timestamp(row.get("pre_market_time")) or _valid_market_timestamp(row.get("regular_market_time"))
        if state == "REGULAR":
            return "交易中", _valid_market_timestamp(row.get("regular_market_time"))
        if state == "POST":
            return "盘后", _valid_market_timestamp(row.get("post_market_time")) or _valid_market_timestamp(row.get("regular_market_time"))
        if state == "CLOSED":
            candidates = [
                _valid_market_timestamp(row.get("post_market_time")),
                _valid_market_timestamp(row.get("regular_market_time")),
            ]
            candidates = [x for x in candidates if x is not None]
            return "休市", max(candidates) if candidates else None
        candidates = [
            _valid_market_timestamp(row.get("overnight_market_time")),
            _valid_market_timestamp(row.get("pre_market_time")),
            _valid_market_timestamp(row.get("post_market_time")),
            _valid_market_timestamp(row.get("regular_market_time")),
        ]
        candidates = [x for x in candidates if x is not None]
        return ("状态未知", max(candidates) if candidates else None)

    quote_ts = _valid_market_timestamp(row.get("regular_market_time"))
    return _asia_session_state(market, quote_ts), quote_ts


def _market_state_text(row, market=""):
    return _quote_session_context(row, market)[0]


def _market_item_html(name, price, change_pct, meta=""):
    price_text = "--" if price is None else f"{price:,.2f}"; change_text = "--" if change_pct is None else f"{change_pct:+.2f}%"
    return f'<div class="market-item"><div class="market-name">{html.escape(name)}</div><div class="market-price">{html.escape(price_text)}</div><div class="market-change">{html.escape(change_text)}</div><div class="market-meta">{html.escape(meta)}</div></div>'
'''
if old not in text:
    raise SystemExit('market state block not found')
text = text.replace(old, new)

old = '''def _quote_meta(row, market=""):
    source = row.get("data_source") or row.get("quote_source") or ""; delayed = row.get("delayed_by"); state = _market_state_text(row); parts = [state] if state else []
    if delayed not in (None, 0, "0") and source == "Yahoo Finance": parts.append(f"延迟{delayed}分")
    elif source: parts.append(source)
    if row.get("_stale"): parts.append("上次有效报价")
    return " · ".join(parts)
'''
new = '''def _quote_meta(row, market=""):
    source = row.get("data_source") or row.get("quote_source") or ""
    delayed = row.get("delayed_by")
    state, quote_ts = _quote_session_context(row, market)
    parts = [state] if state else []
    time_label = _market_time_label(quote_ts)
    parts.append(time_label if time_label else "时间暂缺")
    if delayed not in (None, 0, "0") and source == "Yahoo Finance":
        parts.append(f"延迟{delayed}分")
    elif source:
        parts.append(source)
    if row.get("_stale"):
        parts.append("上次有效报价")
    return " · ".join(parts)
'''
if old not in text:
    raise SystemExit('quote meta block not found')
text = text.replace(old, new)

old = '''    groups = [("🇺🇸 美股", [_market_item_html("纳斯达克", q["nasdaq"].get("price"), q["nasdaq"].get("change_pct"), _quote_meta(q["nasdaq"])), _market_item_html("标普500", q["sp500"].get("price"), q["sp500"].get("change_pct"), _quote_meta(q["sp500"])), _market_item_html("道琼斯", q["dow"].get("price"), q["dow"].get("change_pct"), _quote_meta(q["dow"]))], "three"), ("🇭🇰 港股", [_market_item_html("恒生指数", q["hsi"].get("price"), q["hsi"].get("change_pct"), _quote_meta(q["hsi"])), _market_item_html("恒生科技", q["hstech"].get("price"), q["hstech"].get("change_pct"), _quote_meta(q["hstech"]))], "two"), ("🇨🇳 A股", [_market_item_html("上证指数", q["sh"].get("price"), q["sh"].get("change_pct"), _quote_meta(q["sh"])), _market_item_html("深证成指", q["sz"].get("price"), q["sz"].get("change_pct"), _quote_meta(q["sz"])) , _market_item_html("沪深300", q["csi300"].get("price"), q["csi300"].get("change_pct"), _quote_meta(q["csi300"]))], "three")]
'''
new = '''    groups = [("🇺🇸 美股", [_market_item_html("纳斯达克", q["nasdaq"].get("price"), q["nasdaq"].get("change_pct"), _quote_meta(q["nasdaq"], "US")), _market_item_html("标普500", q["sp500"].get("price"), q["sp500"].get("change_pct"), _quote_meta(q["sp500"], "US")), _market_item_html("道琼斯", q["dow"].get("price"), q["dow"].get("change_pct"), _quote_meta(q["dow"], "US"))], "three"), ("🇭🇰 港股", [_market_item_html("恒生指数", q["hsi"].get("price"), q["hsi"].get("change_pct"), _quote_meta(q["hsi"], "HK")), _market_item_html("恒生科技", q["hstech"].get("price"), q["hstech"].get("change_pct"), _quote_meta(q["hstech"], "HK"))], "two"), ("🇨🇳 A股", [_market_item_html("上证指数", q["sh"].get("price"), q["sh"].get("change_pct"), _quote_meta(q["sh"], "CN")), _market_item_html("深证成指", q["sz"].get("price"), q["sz"].get("change_pct"), _quote_meta(q["sz"], "CN")) , _market_item_html("沪深300", q["csi300"].get("price"), q["csi300"].get("change_pct"), _quote_meta(q["csi300"], "CN"))], "three")]
'''
if old not in text:
    raise SystemExit('market groups block not found')
text = text.replace(old, new)

text = text.replace('''    st.markdown('<div class="market-groups">' + "".join(cards) + '</div>', unsafe_allow_html=True)\n    return snapshot_time\n\nst.markdown('<div id="market-overview" class="section-anchor"></div><div class="section-kicker">MARKET OVERVIEW</div>', unsafe_allow_html=True)\nst.markdown('<div class="section-title">市场概览</div><div class="section-description">美股、港股与 A 股主要指数 · 行情模块每 60 秒刷新</div>', unsafe_allow_html=True)\nmarket_snapshot_time = render_market_groups()\nmarket_refresh_text = datetime.fromtimestamp(market_snapshot_time, DASHBOARD_TZ).strftime("%Y-%m-%d %H:%M:%S")\nst.caption(f"行情数据刷新时间（HKT）：{market_refresh_text}")\n''', '''    st.markdown('<div class="market-groups">' + "".join(cards) + '</div>', unsafe_allow_html=True)\n\nst.markdown('<div id="market-overview" class="section-anchor"></div><div class="section-kicker">MARKET OVERVIEW</div>', unsafe_allow_html=True)\nst.markdown('<div class="section-title">市场概览</div><div class="section-description">美股、港股与 A 股主要指数 · 状态与报价时间来自行情源 · 60 秒刷新</div>', unsafe_allow_html=True)\n\n@st.fragment(run_every="60s")\ndef render_market_overview():\n    render_market_groups()\n\nrender_market_overview()\n''')

if 'market_snapshot_time = render_market_groups()' in text or '1970-01-01' in text:
    raise SystemExit('fake refresh timestamp block still present')
if '_quote_meta(q["nasdaq"], "US")' not in text:
    raise SystemExit('US quote context not wired')
if '@st.fragment(run_every="60s")\ndef render_market_overview' not in text:
    raise SystemExit('market overview fragment missing')

path.write_text(text, encoding='utf-8')
print('market quote truth patch applied')
