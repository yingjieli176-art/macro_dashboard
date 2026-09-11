from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"
STATE = ROOT / "macro_platform" / "watchlist_state.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"missing expected block: {label}")
    return text.replace(old, new, 1)


def sub_once(text: str, pattern: str, repl: str, label: str, flags: int = 0) -> str:
    new_text, count = re.subn(pattern, repl, text, count=1, flags=flags)
    if count != 1:
        raise RuntimeError(f"expected one regex match for {label}, got {count}")
    return new_text


def update_state() -> None:
    text = STATE.read_text(encoding="utf-8")
    text = replace_once(
        text,
        'WATCHLIST_KEYS = ("market_search_us", "market_search_crypto", "market_search_hk", "market_search_cn")',
        'WATCHLIST_KEYS = ("market_search_us", "market_search_hk", "market_search_cn")',
        "watchlist keys",
    )
    text = text.replace('    "market_search_crypto": "x",\n', '', 1)
    text = text.replace('    "market_search_crypto": "CRYPTO",\n', '', 1)
    text = replace_once(text, 'DEFAULT_WATCHLIST_REVISION = 3', 'DEFAULT_WATCHLIST_REVISION = 4', 'watchlist revision')
    text = sub_once(
        text,
        r'    "market_search_crypto": \[\n.*?    \],\n    "market_search_hk": \[',
        '    "market_search_hk": [',
        "crypto defaults",
        flags=re.S,
    )
    STATE.write_text(text, encoding="utf-8")


def update_app() -> None:
    text = APP.read_text(encoding="utf-8")

    # Restore the original compact market overview geometry.
    compact_css = '''.market-groups { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 7px; margin-bottom: 0.45rem; }
.market-group { border: 1px solid #e5e7eb; border-radius: 8px; padding: 6px 8px 5px; background: #fff; min-width: 0; min-height: 96px; box-sizing: border-box; }
.market-group-title { color: #374151; font-size: 0.88rem; font-weight: 650; margin-bottom: 5px; }
.market-group-row { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 4px; min-height: 66px; align-items: start; }
.market-group-row.two { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.market-item { min-width: 0; height: 66px; min-height: 66px; max-height: 66px; padding-right: 4px; border-right: 1px solid #f0f0f0; box-sizing: border-box; overflow: hidden; }
.market-item:last-child { border-right: none; }
.market-name { color: #6b7280; font-size: 0.78rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.market-price { color: #111827; font-size: 0.98rem; font-weight: 650; margin-top: 1px; white-space: nowrap; }
.market-change { font-size: 0.76rem; white-space: nowrap; }
.market-meta { color: #9ca3af; font-size: 0.66rem; margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }'''
    text = sub_once(
        text,
        r'/\* Market overview · compact professional index tape \*/\n\.market-groups .*?@media \(max-width:1100px\) \{ \.market-groups \{ grid-template-columns:1fr; \} \}',
        compact_css,
        "market overview css",
        flags=re.S,
    )
    text = sub_once(
        text,
        r'\n\.crypto-metrics \{.*?\.crypto-metric-value \{.*?\}\n',
        '\n',
        "crypto metric css",
        flags=re.S,
    )

    old_market_item = '''def _market_item_html(name, price, change_pct, meta=""):
    price_text = "--" if price is None else f"{price:,.2f}"
    change_text = "--" if change_pct is None else f"{change_pct:+.2f}%"
    change_class = "flat" if change_pct is None or change_pct == 0 else ("up" if change_pct > 0 else "down")
    return (
        '<div class="market-item">'
        f'<div class="market-name">{html.escape(name)}</div>'
        f'<div class="market-price">{html.escape(price_text)}</div>'
        f'<div class="market-change {change_class}">{html.escape(change_text)}</div>'
        f'<div class="market-meta">{html.escape(meta)}</div>'
        '</div>'
    )'''
    new_market_item = '''def _market_item_html(name, price, change_pct, meta=""):
    price_text = "--" if price is None else f"{price:,.2f}"
    change_text = "--" if change_pct is None else f"{change_pct:+.2f}%"
    return f'<div class="market-item"><div class="market-name">{html.escape(name)}</div><div class="market-price">{html.escape(price_text)}</div><div class="market-change">{html.escape(change_text)}</div><div class="market-meta">{html.escape(meta)}</div></div>' '''
    text = replace_once(text, old_market_item, new_market_item.rstrip(), "market item compact render")

    # Remove Crypto from the watchlist/search module; Crypto now belongs in charts.
    text = text.replace('    if raw.endswith("-USD"):\n        return "CRYPTO"\n', '', 1)
    text = text.replace('    if market == "CRYPTO":\n        return True\n', '', 1)
    text = sub_once(
        text,
        r'\n    if market == "CRYPTO":\n        quote_ts = _valid_market_timestamp\(row\.get\("regular_market_time"\)\)\n        return "24/7", quote_ts\n',
        '\n',
        "crypto session branch",
    )
    text = sub_once(
        text,
        r'\n    # Crypto trades continuously\..*?        return _empty_quote\(\)\n\n    # HK/A:',
        '\n    # HK/A:',
        "crypto quote branch",
        flags=re.S,
    )
    text = replace_once(
        text,
        '''        if market == "CRYPTO":
            allowed_types = {"CRYPTOCURRENCY"}
        elif market == "US":
            allowed_types = {"EQUITY", "INDEX"}
        else:
            allowed_types = {"EQUITY"}''',
        '''        allowed_types = {"EQUITY", "INDEX"} if market == "US" else {"EQUITY"}''',
        "crypto search type",
    )
    text = text.replace('        if market == "CRYPTO" and not symbol.upper().endswith("-USD"):\n            continue\n', '', 1)

    text = sub_once(
        text,
        r'@st\.cache_data\(ttl=60, show_spinner=False\)\ndef _get_crypto_metrics\(symbol\):.*?\n\ndef _render_quote_block\(item\):',
        'def _render_quote_block(item):',
        "crypto metric helpers",
        flags=re.S,
    )
    text = sub_once(
        text,
        r'\n    if item\.get\("market"\) == "CRYPTO" and price is not None and change is not None:\n        change_text = f"24H \{change:\+\.2f\}%"',
        '',
        "crypto 24h label",
    )
    text = text.replace('    metrics_html = _crypto_metrics_html(item.get("symbol", "")) if item.get("market") == "CRYPTO" else ""\n', '', 1)
    text = text.replace("f'{session_html}<div class=\"watch-meta\">{html.escape(meta)}</div>{metrics_html}'", "f'{session_html}<div class=\"watch-meta\">{html.escape(meta)}</div>'", 1)

    text = replace_once(
        text,
        '<div class="section-title">自选观察</div><div class="section-description">核心标的快速监控 · Crypto 显示 24H / 7D / 30D / 30D波动率 / 成交额 / 市值 / ETH-BTC · 港/A 双源择新 + 分时兜底 · 15 秒自动刷新</div>',
        '<div class="section-title">自选观察</div><div class="section-description">核心标的快速监控 · 港/A 腾讯 + 东方财富双源择新，分时兜底 · Yahoo 仅备用 · 15 秒自动刷新</div>',
        "watchlist description",
    )

    start_marker = '@st.fragment(run_every="15s")\ndef render_watchlists():'
    end_marker = '\nrender_watchlists()\n'
    start = text.find(start_marker)
    end = text.find(end_marker, start)
    if start < 0 or end < 0:
        raise RuntimeError("watchlist render block not found")
    watchlist_function = '''@st.fragment(run_every="15s")
def render_watchlists():
    info_col, refresh_col = st.columns([8.6, 1.4], vertical_alignment="center")
    with info_col:
        st.markdown('<div class="watch-toolbar">多源行情按时效切换 · 行情失败时保留上次有效报价</div>', unsafe_allow_html=True)
    with refresh_col:
        if st.button("↻ 刷新", key="refresh_watchlist_quotes", help="只刷新下方自选模块报价，不刷新市场概览"):
            st.session_state["_watchlist_refresh_key"] = st.session_state.get("_watchlist_refresh_key", 0) + 1

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
'''
    text = text[:start] + watchlist_function + text[end:]

    # Add a proper crypto chart after precious metals. Default to normalized
    # price comparison, with ratio and realized volatility on separate axes.
    marker = '\nPARAM_DESCRIPTIONS = ['
    if marker not in text:
        raise RuntimeError("PARAM_DESCRIPTIONS marker missing")
    crypto_chart = r'''

def build_fig11(date_range, market_mode="Rebased 100"):
    """Crypto market: BTC, ETH, ETH/BTC and 30-day BTC realized volatility."""
    frames = []
    for symbol, column in (("BTC-USD", "BTC"), ("ETH-USD", "ETH")):
        try:
            frame = get_yahoo_daily_history(symbol).rename(columns={"close": column})
            if not frame.empty:
                frames.append(frame[["observation_date", column]])
        except Exception:
            pass

    if frames:
        data = frames[0]
        for frame in frames[1:]:
            data = data.merge(frame, on="observation_date", how="outer")
        data = data.sort_values("observation_date")
    else:
        data = pd.DataFrame(columns=["observation_date"])

    if "BTC" in data.columns and "ETH" in data.columns:
        btc = pd.to_numeric(data["BTC"], errors="coerce")
        eth = pd.to_numeric(data["ETH"], errors="coerce")
        data["ETHBTC"] = eth.where(btc > 0) / btc.where(btc > 0)
    if "BTC" in data.columns:
        btc_returns = pd.to_numeric(data["BTC"], errors="coerce").pct_change(fill_method=None)
        data["BTC_VOL_30D"] = btc_returns.rolling(30, min_periods=20).std() * (365.0 ** 0.5) * 100.0

    data = filter_range(data, date_range)
    fig = go.Figure()

    if market_mode == "Rebased 100":
        if "BTC" in data.columns:
            data["BTC_R100"] = _rebase_100(data["BTC"])
        if "ETH" in data.columns:
            data["ETH_R100"] = _rebase_100(data["ETH"])
        add_line(fig, data, "BTC_R100", "BTC · R100", 2.9, unit="")
        add_line(fig, data, "ETH_R100", "ETH · R100", 2.6, unit="")
        add_line(fig, data, "ETHBTC", "ETH/BTC", 2.2, "dash", "y2", "")
        add_line(fig, data, "BTC_VOL_30D", "BTC 30D Realized Vol", 2.2, "dot", "y3", "%")
        fig.update_layout(
            yaxis2=dict(overlaying="y", side="right", anchor="free", position=0.87),
            yaxis3=dict(overlaying="y", side="right", anchor="free", position=0.98),
        )
        fig = apply_chart_style(fig, chart_height(320, 440), date_range)
        fig.update_layout(
            margin=dict(l=62, r=150, t=72, b=34, pad=2),
            legend=dict(y=1.09, x=0.01),
            xaxis=dict(domain=[0.0, 0.84]),
            yaxis=dict(title="BTC / ETH · Rebased 100", tickformat=".1f"),
            yaxis2=dict(title="R1 · ETH/BTC", overlaying="y", side="right", anchor="free", position=0.87, showgrid=False, fixedrange=True, tickformat=".4f"),
            yaxis3=dict(title="R2 · BTC 30D Vol (%)", overlaying="y", side="right", anchor="free", position=0.98, showgrid=False, fixedrange=True, tickformat=".0f"),
        )
        return fig

    add_line(fig, data, "BTC", "BTC", 2.9, unit=" USD")
    add_line(fig, data, "ETH", "ETH", 2.6, None, "y2", " USD")
    add_line(fig, data, "ETHBTC", "ETH/BTC", 2.2, "dash", "y3", "")
    add_line(fig, data, "BTC_VOL_30D", "BTC 30D Realized Vol", 2.2, "dot", "y4", "%")
    fig.update_layout(
        yaxis2=dict(overlaying="y", side="right", anchor="free", position=0.78),
        yaxis3=dict(overlaying="y", side="right", anchor="free", position=0.88),
        yaxis4=dict(overlaying="y", side="right", anchor="free", position=0.98),
    )
    fig = apply_chart_style(fig, chart_height(330, 450), date_range)
    fig.update_layout(
        margin=dict(l=72, r=220, t=72, b=34, pad=2),
        legend=dict(y=1.09, x=0.01),
        xaxis=dict(domain=[0.0, 0.75]),
        yaxis=dict(title="BTC · USD", tickformat=",.0f"),
        yaxis2=dict(title="R1 · ETH · USD", overlaying="y", side="right", anchor="free", position=0.78, showgrid=False, fixedrange=True, tickformat=",.0f"),
        yaxis3=dict(title="R2 · ETH/BTC", overlaying="y", side="right", anchor="free", position=0.88, showgrid=False, fixedrange=True, tickformat=".4f"),
        yaxis4=dict(title="R3 · BTC 30D Vol (%)", overlaying="y", side="right", anchor="free", position=0.98, showgrid=False, fixedrange=True, tickformat=".0f"),
    )
    return fig


CRYPTO_MARKET_DESCRIPTION = (
    '<b>参数概念：</b><br>'
    '1. BTC / ETH：比特币与以太坊美元价格；默认 Rebased 100 以可视区间首个有效值归一到 100，重点比较相对强弱。<br>'
    '2. ETH/BTC（R1）：ETH 价格除以 BTC 价格；上升表示 ETH 相对 BTC 走强，下降表示资金表现更偏向 BTC。<br>'
    '3. BTC 30D Realized Vol（R2/R3）：基于 BTC 日收益率计算的 30 日年化实际波动率，反映已经发生的价格波动强度，不是期权隐含波动率。<br><br>'
    '<b>读取提示：</b>默认优先看 Rebased 100 的 BTC / ETH 强弱，再结合 ETH/BTC 判断风险偏好是否从 BTC 向 ETH 扩散；波动率快速抬升意味着仓位风险同步放大。'
)
'''
    text = text.replace(marker, crypto_chart + marker, 1)

    render_marker = '''    add_sources([
        ("Yahoo Finance · Gold Futures GC=F", "https://finance.yahoo.com/quote/GC=F/history/"),
        ("Yahoo Finance · Silver Futures SI=F", "https://finance.yahoo.com/quote/SI=F/history/"),
        ("FRED · Cboe Gold ETF Volatility Index (GVZCLS)", "https://fred.stlouisfed.org/series/GVZCLS"),
        ("Cboe · Gold Volatility", "https://www.cboe.com/tradable_products/vix/vix_historical_data/"),
    ])
    st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)
'''
    if render_marker not in text:
        raise RuntimeError("precious metals render marker missing")
    crypto_render = render_marker + '''
    st.markdown(
        '<div class="section-kicker">CRYPTO MARKET</div>'
        '<div class="section-title">11. Crypto Market</div>'
        '<div class="section-description">BTC / ETH · ETH/BTC Ratio (R1) · BTC 30D Realized Volatility (R2/R3)</div>',
        unsafe_allow_html=True,
    )
    crypto_range = st.radio(
        "时间范围", RANGES, horizontal=True, index=1,
        key="crypto_market_range", label_visibility="collapsed",
    )
    crypto_mode = st.radio(
        "市场显示", ["Rebased 100", "Raw"], horizontal=True, index=0,
        key="crypto_market_mode", label_visibility="collapsed",
    )
    st.plotly_chart(build_fig11(crypto_range, crypto_mode), use_container_width=True, config=PLOTLY_CONFIG)
    st.markdown(f'<div class="mini-description">{CRYPTO_MARKET_DESCRIPTION}</div>', unsafe_allow_html=True)
    add_sources([
        ("Yahoo Finance · Bitcoin BTC-USD", "https://finance.yahoo.com/quote/BTC-USD/history/"),
        ("Yahoo Finance · Ethereum ETH-USD", "https://finance.yahoo.com/quote/ETH-USD/history/"),
    ])
    st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)
'''
    text = text.replace(render_marker, crypto_render, 1)

    APP.write_text(text, encoding="utf-8")


def main() -> None:
    update_state()
    update_app()
    print("crypto module replaced by chart; market overview compact restored")


if __name__ == "__main__":
    main()
