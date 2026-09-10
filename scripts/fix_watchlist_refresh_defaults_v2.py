from pathlib import Path

APP = Path("app.py")
STATE = Path("macro_platform/watchlist_state.py")

app = APP.read_text(encoding="utf-8")
state = STATE.read_text(encoding="utf-8")

# --- Watchlist state: bump the one-time default migration revision and
# canonicalize names for existing default symbols during that migration.
state = state.replace("DEFAULT_WATCHLIST_REVISION = 1", "DEFAULT_WATCHLIST_REVISION = 2", 1)

old_merge = '''def merge_default_watchlists(payload: Any) -> dict[str, list[dict[str, str]]]:
    result = normalize_watchlists(payload)
    defaults = default_watchlists()
    for key in WATCHLIST_KEYS:
        seen = {row["symbol"] for row in result[key]}
        for row in defaults[key]:
            if row["symbol"] not in seen and len(result[key]) < MAX_ITEMS_PER_MARKET:
                result[key].append(dict(row))
                seen.add(row["symbol"])
    return result
'''
new_merge = '''def merge_default_watchlists(payload: Any) -> dict[str, list[dict[str, str]]]:
    result = normalize_watchlists(payload)
    defaults = default_watchlists()
    for key in WATCHLIST_KEYS:
        by_symbol = {row["symbol"]: row for row in result[key]}
        for default_row in defaults[key]:
            symbol = default_row["symbol"]
            if symbol in by_symbol:
                # During a default-revision migration, normalize the display
                # name as well so old saved English labels become consistent.
                by_symbol[symbol]["name"] = default_row["name"]
                continue
            if len(result[key]) >= MAX_ITEMS_PER_MARKET:
                break
            added = dict(default_row)
            result[key].append(added)
            by_symbol[symbol] = added
    return result
'''
if old_merge not in state:
    raise RuntimeError("merge_default_watchlists block not found")
state = state.replace(old_merge, new_merge, 1)

# --- App timezone imports and dashboard timezone.
if "from datetime import datetime\n" not in app:
    app = app.replace("import time\n", "import time\nfrom datetime import datetime\nfrom zoneinfo import ZoneInfo\n", 1)
if 'DASHBOARD_TZ = ZoneInfo("Asia/Hong_Kong")' not in app:
    app = app.replace(
        'REPO_URL = "https://github.com/yingjieli176-art/macro_dashboard"\n',
        'REPO_URL = "https://github.com/yingjieli176-art/macro_dashboard"\nDASHBOARD_TZ = ZoneInfo("Asia/Hong_Kong")\n',
        1,
    )

# Migration must still run after a deployment even if Streamlit preserved the
# current session_state flag. This fixes the observed 1/1/1 cards after the
# first v3 rollout.
old_load = '''def _load_watchlists():
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
new_load = '''def _load_watchlists():
    raw = st.query_params.get(WATCHLIST_PARAM, "")
    needs_migration = watchlist_needs_default_migration(raw)

    if st.session_state.get("_watchlist_loaded"):
        if needs_migration:
            current = {}
            for key in WATCHLIST_KEYS:
                items = st.session_state.get(f"{key}_confirmed", [])
                if isinstance(items, dict):
                    items = [items]
                current[key] = items if isinstance(items, list) else []
            payload = merge_default_watchlists(current)
            for key in WATCHLIST_KEYS:
                st.session_state[f"{key}_confirmed"] = payload.get(key, [])
            st.query_params[WATCHLIST_PARAM] = encode_watchlists(payload)
        return

    payload = decode_watchlists(raw)
    if needs_migration:
        payload = merge_default_watchlists(payload)
        # v3 stores the default revision. Once migrated, manual deletion wins
        # and a deleted default is not silently re-added on later reruns.
        st.query_params[WATCHLIST_PARAM] = encode_watchlists(payload)
    for key in WATCHLIST_KEYS:
        st.session_state[f"{key}_confirmed"] = payload.get(key, [])
    st.session_state["_watchlist_loaded"] = True
'''
if old_load not in app:
    raise RuntimeError("_load_watchlists block not found")
app = app.replace(old_load, new_load, 1)
app = app.replace(
    "# v2 is compressed + URL-safe and remains backward-compatible on load.",
    "# v3 is compressed + URL-safe and remains backward-compatible on load.",
    1,
)

# Market overview timestamp should be the actual snapshot acquisition time in
# Hong Kong time, not the Streamlit server's UTC clock.
old_render_end = '''    st.markdown('<div class="market-groups">' + "".join(cards) + '</div>', unsafe_allow_html=True)

st.markdown('<div id="market-overview" class="section-anchor"></div><div class="section-kicker">MARKET OVERVIEW</div>', unsafe_allow_html=True)
st.markdown('<div class="section-title">市场概览</div><div class="section-description">美股、港股与 A 股主要指数 · 行情模块每 60 秒刷新</div>', unsafe_allow_html=True)
render_market_groups()
st.caption(f"行情数据刷新时间：{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}")
'''
new_render_end = '''    st.markdown('<div class="market-groups">' + "".join(cards) + '</div>', unsafe_allow_html=True)
    return snapshot_time

st.markdown('<div id="market-overview" class="section-anchor"></div><div class="section-kicker">MARKET OVERVIEW</div>', unsafe_allow_html=True)
st.markdown('<div class="section-title">市场概览</div><div class="section-description">美股、港股与 A 股主要指数 · 行情模块每 60 秒刷新</div>', unsafe_allow_html=True)
market_snapshot_time = render_market_groups()
market_refresh_text = datetime.fromtimestamp(market_snapshot_time, DASHBOARD_TZ).strftime("%Y-%m-%d %H:%M:%S")
st.caption(f"行情数据刷新时间（HKT）：{market_refresh_text}")
'''
if old_render_end not in app:
    raise RuntimeError("market overview timestamp block not found")
app = app.replace(old_render_end, new_render_end, 1)

# Move refresh into the fragment so clicking it reruns only WATCHLIST. The
# manual refresh key bypasses the cached quote for these cards without clearing
# the cache shared by the market overview.
old_refresh = '''def render_watchlist_refresh_control():
    info_col, refresh_col = st.columns([5, 1], vertical_alignment="center")
    with info_col:
        st.markdown('<div class="watch-toolbar">默认组合已启用；行情失败时保留上次有效报价。</div>', unsafe_allow_html=True)
    with refresh_col:
        if st.button("↻ 刷新报价", key="refresh_watchlist_quotes", use_container_width=True, help="立即重新获取自选与市场概览报价"):
            _get_cached_quote.clear()
            st.session_state["_watchlist_refresh_key"] = st.session_state.get("_watchlist_refresh_key", 0) + 1

st.markdown('<div id="watchlist" class="section-anchor"></div><div class="section-kicker">WATCHLIST</div>', unsafe_allow_html=True)
st.markdown('<div class="section-title">自选观察</div><div class="section-description">核心标的快速监控 · 60 秒自动刷新 · 添加、删除后自动保存到当前链接</div>', unsafe_allow_html=True)
render_watchlist_refresh_control()

@st.fragment(run_every="60s")
def render_watchlists():
    search_cols = st.columns(3, gap="small", vertical_alignment="top")
'''
new_refresh = '''st.markdown('<div id="watchlist" class="section-anchor"></div><div class="section-kicker">WATCHLIST</div>', unsafe_allow_html=True)
st.markdown('<div class="section-title">自选观察</div><div class="section-description">核心标的快速监控 · 60 秒自动刷新 · 添加、删除后自动保存到当前链接</div>', unsafe_allow_html=True)

@st.fragment(run_every="60s")
def render_watchlists():
    info_col, refresh_col = st.columns([8.6, 1.4], vertical_alignment="center")
    with info_col:
        st.markdown('<div class="watch-toolbar">默认组合已启用 · 行情失败时保留上次有效报价</div>', unsafe_allow_html=True)
    with refresh_col:
        if st.button("↻ 刷新", key="refresh_watchlist_quotes", help="只刷新下方自选模块报价，不刷新市场概览"):
            st.session_state["_watchlist_refresh_key"] = st.session_state.get("_watchlist_refresh_key", 0) + 1

    search_cols = st.columns(3, gap="small", vertical_alignment="top")
'''
if old_refresh not in app:
    raise RuntimeError("watchlist refresh block not found")
app = app.replace(old_refresh, new_refresh, 1)

APP.write_text(app, encoding="utf-8")
STATE.write_text(state, encoding="utf-8")
print("fixed watchlist-only refresh, HKT timestamp, and default migration revision 2")
