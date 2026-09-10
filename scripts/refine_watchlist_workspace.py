from pathlib import Path
import re

APP = Path("app.py")
STATE = Path("macro_platform/watchlist_state.py")

state_text = '''from __future__ import annotations

import base64
import json
import zlib
from typing import Any

WATCHLIST_KEYS = ("market_search_us", "market_search_hk", "market_search_cn")
_SHORT_KEY = {
    "market_search_us": "u",
    "market_search_hk": "h",
    "market_search_cn": "c",
}
_MARKET = {
    "market_search_us": "US",
    "market_search_hk": "HK",
    "market_search_cn": "CN",
}
MAX_ITEMS_PER_MARKET = 40
WATCHLIST_SCHEMA_VERSION = 3
DEFAULT_WATCHLIST_REVISION = 1

DEFAULT_WATCHLISTS = {
    "market_search_us": [
        {"symbol": "NVDA", "name": "英伟达"},
        {"symbol": "NBIS", "name": "Nebius"},
        {"symbol": "^NDX", "name": "纳斯达克100"},
    ],
    "market_search_hk": [
        {"symbol": "0700.HK", "name": "腾讯控股"},
        {"symbol": "0189.HK", "name": "东岳集团"},
    ],
    "market_search_cn": [
        {"symbol": "600160.SS", "name": "巨化股份"},
        {"symbol": "600021.SS", "name": "上海电力"},
    ],
}


def _empty() -> dict[str, list[dict[str, str]]]:
    return {key: [] for key in WATCHLIST_KEYS}


def _clean_item(item: Any, market: str) -> dict[str, str] | None:
    if not isinstance(item, dict):
        return None
    symbol = str(item.get("symbol") or "").strip().upper()
    if not symbol:
        return None
    name = str(item.get("name") or symbol).strip()[:120] or symbol
    return {
        "symbol": symbol,
        "name": name,
        "exchange": "",
        "market": market,
    }


def normalize_watchlists(payload: Any) -> dict[str, list[dict[str, str]]]:
    result = _empty()
    if not isinstance(payload, dict):
        return result

    for key in WATCHLIST_KEYS:
        raw_items = payload.get(key, [])
        if isinstance(raw_items, dict):
            raw_items = [raw_items]
        if not isinstance(raw_items, list):
            continue
        seen: set[str] = set()
        for raw in raw_items:
            item = _clean_item(raw, _MARKET[key])
            if not item or item["symbol"] in seen:
                continue
            seen.add(item["symbol"])
            result[key].append(item)
            if len(result[key]) >= MAX_ITEMS_PER_MARKET:
                break
    return result


def default_watchlists() -> dict[str, list[dict[str, str]]]:
    return normalize_watchlists(DEFAULT_WATCHLISTS)


def merge_default_watchlists(payload: Any) -> dict[str, list[dict[str, str]]]:
    result = normalize_watchlists(payload)
    defaults = default_watchlists()
    for key in WATCHLIST_KEYS:
        seen = {row["symbol"] for row in result[key]}
        for row in defaults[key]:
            if row["symbol"] not in seen and len(result[key]) < MAX_ITEMS_PER_MARKET:
                result[key].append(dict(row))
                seen.add(row["symbol"])
    return result


def encode_watchlists(payload: Any) -> str:
    normalized = normalize_watchlists(payload)
    compact: dict[str, Any] = {
        "v": WATCHLIST_SCHEMA_VERSION,
        "d": DEFAULT_WATCHLIST_REVISION,
    }
    for key in WATCHLIST_KEYS:
        rows = normalized[key]
        compact[_SHORT_KEY[key]] = [[row["symbol"], row["name"]] for row in rows]
    raw = json.dumps(compact, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    packed = zlib.compress(raw, level=9)
    token = base64.urlsafe_b64encode(packed).decode("ascii").rstrip("=")
    return "v3." + token


def _unpack_token(raw: str, prefix: str) -> dict[str, Any]:
    token = raw[len(prefix):]
    token += "=" * (-len(token) % 4)
    packed = base64.urlsafe_b64decode(token.encode("ascii"))
    compact = json.loads(zlib.decompress(packed).decode("utf-8"))
    if not isinstance(compact, dict):
        raise ValueError("invalid watchlist payload")
    return compact


def _compact_to_payload(compact: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    payload = _empty()
    reverse = {value: key for key, value in _SHORT_KEY.items()}
    for short_key, key in reverse.items():
        rows = compact.get(short_key, [])
        if not isinstance(rows, list):
            continue
        market = _MARKET[key]
        for row in rows[:MAX_ITEMS_PER_MARKET]:
            if not isinstance(row, list) or not row:
                continue
            symbol = str(row[0] or "").strip().upper()
            if not symbol:
                continue
            name = str(row[1] if len(row) > 1 else symbol).strip()[:120] or symbol
            payload[key].append({"symbol": symbol, "name": name, "exchange": "", "market": market})
    return normalize_watchlists(payload)


def _decode_v3(raw: str) -> dict[str, list[dict[str, str]]]:
    compact = _unpack_token(raw, "v3.")
    if compact.get("v") != WATCHLIST_SCHEMA_VERSION:
        raise ValueError("unsupported watchlist payload")
    return _compact_to_payload(compact)


def _decode_v2(raw: str) -> dict[str, list[dict[str, str]]]:
    compact = _unpack_token(raw, "v2.")
    if compact.get("v") != 2:
        raise ValueError("unsupported legacy watchlist payload")
    return _compact_to_payload(compact)


def decode_watchlists(raw: Any) -> dict[str, list[dict[str, str]]]:
    if raw is None:
        return _empty()
    text = str(raw).strip()
    if not text:
        return _empty()
    try:
        if text.startswith("v3."):
            return _decode_v3(text)
        if text.startswith("v2."):
            return _decode_v2(text)
        return normalize_watchlists(json.loads(text))
    except Exception:
        return _empty()


def watchlist_needs_default_migration(raw: Any) -> bool:
    text = str(raw or "").strip()
    if not text.startswith("v3."):
        return True
    try:
        compact = _unpack_token(text, "v3.")
        return int(compact.get("d", 0)) < DEFAULT_WATCHLIST_REVISION
    except Exception:
        return True
'''
STATE.write_text(state_text, encoding="utf-8")

text = APP.read_text(encoding="utf-8")
old_import = "from macro_platform.watchlist_state import WATCHLIST_KEYS, decode_watchlists, encode_watchlists\n"
new_import = "from macro_platform.watchlist_state import WATCHLIST_KEYS, decode_watchlists, encode_watchlists, merge_default_watchlists, watchlist_needs_default_migration\n"
if old_import in text:
    text = text.replace(old_import, new_import, 1)
elif new_import not in text:
    raise RuntimeError("watchlist_state import not found")

old_load = '''def _load_watchlists():
    if st.session_state.get("_watchlist_loaded"):
        return
    payload = decode_watchlists(st.query_params.get(WATCHLIST_PARAM, ""))
    for key in WATCHLIST_KEYS:
        st.session_state[f"{key}_confirmed"] = payload.get(key, [])
    st.session_state["_watchlist_loaded"] = True
'''
new_load = '''def _load_watchlists():
    if st.session_state.get("_watchlist_loaded"):
        return
    raw = st.query_params.get(WATCHLIST_PARAM, "")
    payload = decode_watchlists(raw)
    if watchlist_needs_default_migration(raw):
        payload = merge_default_watchlists(payload)
        # Migrate old / empty state once. v3 remembers the default revision so
        # a user can later delete a default symbol without it being re-added.
        st.query_params[WATCHLIST_PARAM] = encode_watchlists(payload)
    for key in WATCHLIST_KEYS:
        st.session_state[f"{key}_confirmed"] = payload.get(key, [])
    st.session_state["_watchlist_loaded"] = True
'''
if old_load in text:
    text = text.replace(old_load, new_load, 1)
elif "watchlist_needs_default_migration(raw)" not in text:
    raise RuntimeError("watchlist loader not found")

css_marker = '''.search-result .search-after, .search-result .search-hint { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
'''
new_css = css_marker + '''
/* Watchlist workstation */
.watch-toolbar { display:flex; align-items:center; min-height:34px; color:#6b7280; font-size:.74rem; }
.watch-market-head { display:flex; align-items:center; justify-content:space-between; gap:10px; margin:2px 0 7px; }
.watch-market-head-main { min-width:0; }
.watch-market-title { color:#111827; font-size:.90rem; font-weight:700; line-height:1.25; }
.watch-market-subtitle { color:#9ca3af; font-size:.64rem; letter-spacing:.08em; margin-top:2px; }
.watch-count { display:inline-flex; min-width:24px; height:22px; padding:0 7px; align-items:center; justify-content:center; border:1px solid #e5e7eb; border-radius:999px; color:#6b7280; background:#f9fafb; font-size:.68rem; font-weight:650; }
.watch-card-body { min-width:0; padding:2px 1px 1px; }
.watch-card-top { display:flex; align-items:baseline; gap:7px; min-width:0; padding-right:2px; }
.watch-card-name { color:#111827; font-size:.86rem; font-weight:680; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.watch-card-symbol { color:#9ca3af; font-size:.66rem; font-family:"Segoe UI",sans-serif; white-space:nowrap; }
.watch-price-row { display:flex; align-items:baseline; gap:9px; margin-top:4px; min-width:0; }
.watch-price { color:#111827; font-size:1.08rem; line-height:1.15; font-weight:720; letter-spacing:-.01em; white-space:nowrap; }
.watch-change { font-size:.78rem; font-weight:650; white-space:nowrap; }
.watch-up { color:#15803d; }
.watch-down { color:#b91c1c; }
.watch-flat { color:#6b7280; }
.watch-session { color:#6b7280; font-size:.69rem; margin-top:4px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.watch-meta { color:#9ca3af; font-size:.64rem; margin-top:3px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.watch-search-note { color:#9ca3af; font-size:.67rem; margin:4px 0 5px; }
.watch-empty { color:#9ca3af; font-size:.72rem; padding:9px 2px 7px; }
.module-delete { margin-top:-4px; margin-right:-3px; }
.module-delete button { color:#9ca3af !important; border-radius:999px !important; }
.module-delete button:hover { color:#b91c1c !important; background:#fef2f2 !important; }
'''
if ".watch-market-head" not in text:
    if css_marker not in text:
        raise RuntimeError("CSS marker not found")
    text = text.replace(css_marker, new_css, 1)

old_filter = '''    for item in quotes:
        if item.get("quoteType") != "EQUITY":
            continue
        symbol = str(item.get("symbol") or "")
'''
new_filter = '''    for item in quotes:
        quote_type = str(item.get("quoteType") or "").upper()
        allowed_types = {"EQUITY", "INDEX"} if market == "US" else {"EQUITY"}
        if quote_type not in allowed_types:
            continue
        symbol = str(item.get("symbol") or "")
'''
if old_filter in text:
    text = text.replace(old_filter, new_filter, 1)
elif 'allowed_types = {"EQUITY", "INDEX"}' not in text:
    raise RuntimeError("Yahoo search quoteType filter not found")

start = text.find("def _render_quote_block(item):")
end = text.find("\ndef _add_confirmed(key, item):", start)
if start < 0 or end < 0:
    raise RuntimeError("quote block bounds not found")
new_quote_block = '''def _render_quote_block(item):
    row = _get_watchlist_quote(item["symbol"])
    price = row.get("price")
    change = row.get("change_pct")
    price_text = "--" if price is None else f"{price:,.2f}"
    change_text = "数据暂缺" if price is None else ("--" if change is None else f"{change:+.2f}%")
    direction_class = "watch-flat"
    if change is not None:
        direction_class = "watch-up" if change > 0 else ("watch-down" if change < 0 else "watch-flat")

    session_text = ""
    if item.get("market") == "US":
        pp, pc = row.get("post_price"), row.get("post_change_pct")
        pre_price, pre_change = row.get("pre_price"), row.get("pre_change_pct")
        overnight_price, overnight_change = row.get("overnight_price"), row.get("overnight_change_pct")
        market_state = row.get("market_state")
        if market_state in ("POSTPOST", "CLOSED") and overnight_price is not None:
            session_text = f'夜盘 {overnight_price:,.2f} · {"--" if overnight_change is None else f"{overnight_change:+.2f}%"}'
        elif market_state in ("PRE", "PREPRE") and pre_price is not None:
            session_text = f'盘前 {pre_price:,.2f} · {"--" if pre_change is None else f"{pre_change:+.2f}%"}'
        elif market_state == "POST" and pp is not None:
            session_text = f'盘后 {pp:,.2f} · {"--" if pc is None else f"{pc:+.2f}%"}'
        elif pp is not None and row.get("post_market_time"):
            session_text = f'最近盘后 {pp:,.2f} · {"--" if pc is None else f"{pc:+.2f}%"}'

    meta = _quote_meta(row, item.get("market", ""))
    name = html.escape(str(item.get("name") or item.get("symbol") or ""))
    symbol = html.escape(str(item.get("symbol") or ""))
    session_html = f'<div class="watch-session">{html.escape(session_text)}</div>' if session_text else ''
    return (
        '<div class="watch-card-body">'
        f'<div class="watch-card-top"><span class="watch-card-name">{name}</span><span class="watch-card-symbol">{symbol}</span></div>'
        f'<div class="watch-price-row"><span class="watch-price">{html.escape(price_text)}</span><span class="watch-change {direction_class}">{html.escape(change_text)}</span></div>'
        f'{session_html}<div class="watch-meta">{html.escape(meta)}</div>'
        '</div>'
    )
'''
text = text[:start] + new_quote_block + text[end:]

old_header = '''st.markdown('<div id="watchlist" class="section-anchor"></div><div class="section-kicker">WATCHLIST</div>', unsafe_allow_html=True)
st.markdown('<div class="section-title">自选观察</div><div class="section-description">按市场添加股票模块；刷新、搜索与删除操作集中在本区域</div>', unsafe_allow_html=True)
render_watchlist_refresh_control()
'''
new_header = '''st.markdown('<div id="watchlist" class="section-anchor"></div><div class="section-kicker">WATCHLIST</div>', unsafe_allow_html=True)
st.markdown('<div class="section-title">自选观察</div><div class="section-description">核心标的快速监控 · 60 秒自动刷新 · 添加、删除后自动保存到当前链接</div>', unsafe_allow_html=True)
render_watchlist_refresh_control()
'''
if old_header in text:
    text = text.replace(old_header, new_header, 1)

start = text.find('@st.fragment(run_every="60s")\ndef render_watchlists():')
end = text.find('\nrender_watchlists()\n', start)
if start < 0 or end < 0:
    raise RuntimeError("watchlist renderer bounds not found")
end += len('\nrender_watchlists()\n')
new_renderer = '''@st.fragment(run_every="60s")
def render_watchlists():
    search_cols = st.columns(3, gap="small", vertical_alignment="top")
    search_config = [
        (search_cols[0], "US", "🇺🇸 美股", "US EQUITY / INDEX", "NVDA / NBIS / Nasdaq 100", "market_search_us"),
        (search_cols[1], "HK", "🇭🇰 港股", "HK EQUITY", "0700 / 腾讯 / 东岳", "market_search_hk"),
        (search_cols[2], "CN", "🇨🇳 A股", "A-SHARE", "600160 / 巨化 / 上海电力", "market_search_cn"),
    ]
    for col, market, title, subtitle, placeholder, key in search_config:
        with col:
            confirmed_list = st.session_state.get(f"{key}_confirmed", [])
            confirmed_list = [confirmed_list] if isinstance(confirmed_list, dict) else (confirmed_list if isinstance(confirmed_list, list) else [])
            st.markdown(
                f'<div class="watch-market-head"><div class="watch-market-head-main"><div class="watch-market-title">{title}</div><div class="watch-market-subtitle">{subtitle}</div></div><span class="watch-count">{len(confirmed_list)}</span></div>',
                unsafe_allow_html=True,
            )
            if confirmed_list:
                for idx, confirmed in enumerate(confirmed_list):
                    if not isinstance(confirmed, dict):
                        continue
                    with st.container(border=True):
                        quote_col, delete_col = st.columns([1, 0.075], gap="small", vertical_alignment="top")
                        with quote_col:
                            st.markdown(_render_quote_block({**confirmed, "market": market}), unsafe_allow_html=True)
                        with delete_col:
                            st.markdown('<div class="module-delete">', unsafe_allow_html=True)
                            st.button(
                                "×",
                                key=f"{key}_delete_{idx}",
                                on_click=_delete_confirmed,
                                args=(key, confirmed.get("symbol")),
                                help=f"删除 {confirmed.get('name') or confirmed.get('symbol')}",
                                type="tertiary",
                                use_container_width=True,
                            )
                            st.markdown('</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div class="watch-empty">暂无标的，可从下方添加。</div>', unsafe_allow_html=True)

            is_open = st.session_state.get(f"{key}_open", False)
            if not is_open:
                st.button("＋ 添加标的", key=f"{key}_open_button", use_container_width=True, on_click=_open_search, args=(key,), help="搜索并添加股票或指数")
            else:
                st.markdown('<div class="watch-search-note">输入名称或代码，搜索后确认添加。</div>', unsafe_allow_html=True)
                input_col, search_col, cancel_col = st.columns([5.0, 1.25, 1.25], gap="small")
                with input_col:
                    st.text_input("搜索", placeholder=placeholder, key=key, label_visibility="collapsed")
                with search_col:
                    st.button("搜索", key=f"{key}_search_button", use_container_width=True, on_click=_run_search, args=(key, market))
                with cancel_col:
                    st.button("取消", key=f"{key}_cancel_button", use_container_width=True, on_click=_cancel_search, args=(key,))
                results = st.session_state.get(f"{key}_results", [])
                if results:
                    options = [f'{item.get("name", "")} · {item.get("symbol", "")} · {item.get("exchange", "")}' for item in results]
                    st.selectbox(
                        "搜索结果",
                        range(len(options)),
                        format_func=lambda i: options[i],
                        key=f"{key}_result_select",
                        label_visibility="collapsed",
                    )
                    st.button("确认添加", key=f"{key}_confirm_selected", use_container_width=True, on_click=_confirm_selected, args=(key,), type="primary")
                elif st.session_state.get(key, "").strip() and f"{key}_results" in st.session_state:
                    st.caption("没有找到匹配标的，请检查名称或代码。")

render_watchlists()
'''
text = text[:start] + new_renderer + text[end:]

# Make the manual refresh row read like a toolbar instead of an isolated button.
old_refresh = '''def render_watchlist_refresh_control():
    _, refresh_col = st.columns([5, 1], vertical_alignment="top")
    with refresh_col:
        if st.button("↻ 刷新股价", key="refresh_watchlist_quotes", use_container_width=True, help="立即重新获取已添加模块的最新报价"):
            _get_cached_quote.clear(); st.session_state["_watchlist_refresh_key"] = st.session_state.get("_watchlist_refresh_key", 0) + 1
'''
new_refresh = '''def render_watchlist_refresh_control():
    info_col, refresh_col = st.columns([5, 1], vertical_alignment="center")
    with info_col:
        st.markdown('<div class="watch-toolbar">默认组合已启用；行情失败时保留上次有效报价。</div>', unsafe_allow_html=True)
    with refresh_col:
        if st.button("↻ 刷新报价", key="refresh_watchlist_quotes", use_container_width=True, help="立即重新获取自选与市场概览报价"):
            _get_cached_quote.clear()
            st.session_state["_watchlist_refresh_key"] = st.session_state.get("_watchlist_refresh_key", 0) + 1
'''
if old_refresh in text:
    text = text.replace(old_refresh, new_refresh, 1)
elif "默认组合已启用" not in text:
    raise RuntimeError("refresh control not found")

APP.write_text(text, encoding="utf-8")
print("refined watchlist workspace, defaults, and migration")
