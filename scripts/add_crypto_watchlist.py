from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"
STATE = ROOT / "macro_platform" / "watchlist_state.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"missing expected block: {label}")
    return text.replace(old, new, 1)


def update_state() -> None:
    text = STATE.read_text(encoding="utf-8")
    text = replace_once(
        text,
        'WATCHLIST_KEYS = ("market_search_us", "market_search_hk", "market_search_cn")',
        'WATCHLIST_KEYS = ("market_search_us", "market_search_crypto", "market_search_hk", "market_search_cn")',
        "watchlist keys",
    )
    text = replace_once(
        text,
        '    "market_search_us": "u",\n    "market_search_hk": "h",',
        '    "market_search_us": "u",\n    "market_search_crypto": "x",\n    "market_search_hk": "h",',
        "short key",
    )
    text = replace_once(
        text,
        '    "market_search_us": "US",\n    "market_search_hk": "HK",',
        '    "market_search_us": "US",\n    "market_search_crypto": "CRYPTO",\n    "market_search_hk": "HK",',
        "market map",
    )
    text = replace_once(
        text,
        "DEFAULT_WATCHLIST_REVISION = 2",
        "DEFAULT_WATCHLIST_REVISION = 3",
        "default revision",
    )
    text = replace_once(
        text,
        '    "market_search_hk": [\n',
        '    "market_search_crypto": [\n'
        '        {"symbol": "BTC-USD", "name": "比特币"},\n'
        '        {"symbol": "ETH-USD", "name": "以太坊"},\n'
        '    ],\n'
        '    "market_search_hk": [\n',
        "crypto defaults",
    )
    STATE.write_text(text, encoding="utf-8")


def update_app() -> None:
    text = APP.read_text(encoding="utf-8")

    text = replace_once(
        text,
        'def _symbol_market(symbol):\n    raw = str(symbol or "").upper().strip()\n    if raw.endswith(".HK")',
        'def _symbol_market(symbol):\n    raw = str(symbol or "").upper().strip()\n    if raw.endswith("-USD"):\n        return "CRYPTO"\n    if raw.endswith(".HK")',
        "crypto market detection",
    )

    text = replace_once(
        text,
        '    if market == "US":\n        regular_ts = _valid_market_timestamp(row.get("regular_market_time"))',
        '    if market == "CRYPTO":\n'
        '        quote_ts = _valid_market_timestamp(row.get("regular_market_time"))\n'
        '        return "24/7", quote_ts\n\n'
        '    if market == "US":\n'
        '        regular_ts = _valid_market_timestamp(row.get("regular_market_time"))',
        "crypto session label",
    )

    text = replace_once(
        text,
        'def _regular_session_now(market):\n    market = str(market or "").upper()\n    if market in {"HK", "CN"}:',
        'def _regular_session_now(market):\n    market = str(market or "").upper()\n    if market == "CRYPTO":\n        return True\n    if market in {"HK", "CN"}:',
        "crypto always-open clock",
    )

    text = replace_once(
        text,
        'def _get_cached_quote(symbol, refresh_key=0):\n    market = _symbol_market(symbol)\n    candidates = []\n\n    # HK/A:',
        'def _get_cached_quote(symbol, refresh_key=0):\n'
        '    market = _symbol_market(symbol)\n'
        '    candidates = []\n\n'
        '    # Crypto trades continuously. Use Yahoo directly so crypto never\n'
        '    # inherits US equity session labels or Tencent fallback behavior.\n'
        '    if market == "CRYPTO":\n'
        '        yahoo = _get_yahoo_quote_safe(symbol)\n'
        '        if yahoo.get("price") is not None:\n'
        '            return _tag_quote_role(yahoo, "primary")\n'
        '        return _empty_quote()\n\n'
        '    # HK/A:',
        "crypto quote routing",
    )

    text = replace_once(
        text,
        '        allowed_types = {"EQUITY", "INDEX"} if market == "US" else {"EQUITY"}\n        if quote_type not in allowed_types:',
        '        if market == "CRYPTO":\n'
        '            allowed_types = {"CRYPTOCURRENCY"}\n'
        '        elif market == "US":\n'
        '            allowed_types = {"EQUITY", "INDEX"}\n'
        '        else:\n'
        '            allowed_types = {"EQUITY"}\n'
        '        if quote_type not in allowed_types:',
        "crypto search quote type",
    )
    text = replace_once(
        text,
        '        if market == "US" and ("." in symbol or symbol.endswith(("=F", "=X"))):\n            continue\n        if market == "HK"',
        '        if market == "US" and ("." in symbol or symbol.endswith(("=F", "=X"))):\n'
        '            continue\n'
        '        if market == "CRYPTO" and not symbol.upper().endswith("-USD"):\n'
        '            continue\n'
        '        if market == "HK"',
        "crypto search symbol filter",
    )

    text = replace_once(
        text,
        '<div class="section-title">自选观察</div><div class="section-description">核心标的快速监控 · 港/A 腾讯 + 东方财富双源择新，分时兜底 · Yahoo 仅备用 · 15 秒自动刷新</div>',
        '<div class="section-title">自选观察</div><div class="section-description">核心标的快速监控 · 美股 / 港股 / A股 / Crypto 分组 · Crypto 24/7 Yahoo · 港/A 双源择新 + 分时兜底 · 15 秒自动刷新</div>',
        "watchlist description",
    )

    start_marker = '@st.fragment(run_every="15s")\ndef render_watchlists():'
    end_marker = '\nrender_watchlists()\n'
    start = text.find(start_marker)
    if start < 0:
        raise RuntimeError("render_watchlists start not found")
    end = text.find(end_marker, start)
    if end < 0:
        raise RuntimeError("render_watchlists end not found")

    function = r'''@st.fragment(run_every="15s")
def render_watchlists():
    info_col, refresh_col = st.columns([8.6, 1.4], vertical_alignment="center")
    with info_col:
        st.markdown('<div class="watch-toolbar">多源行情按时效切换 · Crypto 24/7 · 行情失败时保留上次有效报价</div>', unsafe_allow_html=True)
    with refresh_col:
        if st.button("↻ 刷新", key="refresh_watchlist_quotes", help="只刷新下方自选模块报价，不刷新市场概览"):
            st.session_state["_watchlist_refresh_key"] = st.session_state.get("_watchlist_refresh_key", 0) + 1

    # Readability first: two wide columns per row instead of squeezing four
    # market groups into one line. Global/24h assets are on top; Asia below.
    search_config = [
        ("US", "🇺🇸 美股", "US EQUITY / INDEX", "NVDA / NBIS / Nasdaq 100", "market_search_us"),
        ("CRYPTO", "₿ 加密资产", "CRYPTO · 24/7", "BTC / ETH / Bitcoin", "market_search_crypto"),
        ("HK", "🇭🇰 港股", "HK EQUITY", "0700 / 腾讯 / 东岳", "market_search_hk"),
        ("CN", "🇨🇳 A股", "A-SHARE", "600160 / 巨化 / 上海电力", "market_search_cn"),
    ]

    for row_start in range(0, len(search_config), 2):
        row_cols = st.columns(2, gap="small", vertical_alignment="top")
        for col, config in zip(row_cols, search_config[row_start:row_start + 2]):
            market, title, subtitle, placeholder, key = config
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
                    help_text = "搜索并添加加密资产" if market == "CRYPTO" else "搜索并添加股票或指数"
                    st.button("＋ 添加标的", key=f"{key}_open_button", use_container_width=True, on_click=_open_search, args=(key,), help=help_text)
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
'''.replace('\\"', '"')

    text = text[:start] + function + text[end:]
    APP.write_text(text, encoding="utf-8")


def main() -> None:
    update_state()
    update_app()
    print("crypto watchlist migration applied")


if __name__ == "__main__":
    main()
