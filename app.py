import html
from collections.abc import Mapping
from copy import deepcopy
import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import streamlit as st
from macro_platform.hk_liquidity import build_hk_liquidity_figure, build_hk_liquidity_figures, load_hk_liquidity
# The renderer is an optional module during rolling Streamlit Cloud deployments.
# Never import individual newly added helpers at startup: mixed revisions of
# app.py and macro_platform/echarts_axes.py must not crash the entire app.
try:
    import macro_platform.echarts_axes as _echarts_axes
except (ImportError, AttributeError) as _echarts_module_error:
    _echarts_axes = None
else:
    _echarts_module_error = None
from macro_platform import chart_axes as _chart_axes
RANGE_OFFSETS = _chart_axes.RANGE_OFFSETS
apply_time_axis = _chart_axes.apply_time_axis
# Extra chart helpers were added across multiple commits. Treat them as
# optional during an out-of-sync Cloud rollout instead of raising ImportError.
apply_client_time_controls = getattr(
    _chart_axes, "apply_client_time_controls", lambda fig, **_kwargs: fig
)
apply_server_time_window = getattr(_chart_axes, "apply_server_time_window", None)
from macro_platform.us_equity_risk import load_vixeq_snapshot
from macro_platform.copper import build_copper_flow_spread_figure
from macro_platform.asia_rates import build_asia_rates_figure
from macro_platform.watchlist_state import WATCHLIST_KEYS, decode_watchlists, encode_watchlists, merge_default_watchlists, watchlist_needs_default_migration
from data import (fetch_eastmoney_news, get_dgs3mo, get_dgs2, get_dgs10, get_dfii10, get_dfii5, get_sofr, get_iorb, get_effr, get_rrp_rate, get_sina_news, get_walcl, get_wresbal, get_wtre_gen, get_tga_daily, get_rrp_daily, _fred_series)

st.set_page_config(page_title="Macro Dashboard", page_icon="📊", layout="wide")

EASTMONEY_FOCUS_URL = "https://kuaixun.eastmoney.com/"
EASTMONEY_QUOTE_URL = "https://push2.eastmoney.com/api/qt/stock/get"
EASTMONEY_SEARCH_URL = "https://searchapi.eastmoney.com/api/suggest/get"
EASTMONEY_UT = "bd1d9ddb04089700cf9c27f4f4961f5b"
TENCENT_QUOTE_URL = "https://qt.gtimg.cn/q="
TENCENT_MINUTE_URL = "https://web.ifzq.gtimg.cn/appstock/app/minute/query"
DIRECT_QUOTE_FRESH_SECONDS = 90
RANGES = ["5Y", "1Y", "6M", "3M", "1M"]
DEFAULT_CHART_RANGE = "1Y"
CHART_BUILD = "2026-10-09-unified-calendar-r33"
PLOTLY_CONFIG = {"displayModeBar": False, "scrollZoom": False, "doubleClick": False, "editable": False, "displaylogo": False, "responsive": True}
WATCHLIST_PARAM = "watchlist"
REPO_URL = "https://github.com/yingjieli176-art/macro_dashboard"
DASHBOARD_TZ = ZoneInfo("Asia/Hong_Kong")
NEWS_STATIC_PATH = Path(__file__).resolve().parent / "static" / "news.json"
NEWS_BACKGROUND_INTERVAL_SECONDS = 60


def _read_existing_news_snapshot():
    try:
        payload = json.loads(NEWS_STATIC_PATH.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _write_news_snapshot():
    NEWS_STATIC_PATH.parent.mkdir(parents=True, exist_ok=True)
    items, error = fetch_eastmoney_news(limit=50)
    previous = _read_existing_news_snapshot()
    if not items:
        items = previous.get("items") if isinstance(previous.get("items"), list) else []
        error = error or "暂无新数据"
    checked_at = datetime.now(DASHBOARD_TZ).isoformat(timespec="seconds")
    payload = {
        "items": items,
        "error": error,
        "updated_at": previous.get("updated_at", "") if error else checked_at,
    }
    temp_path = NEWS_STATIC_PATH.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(temp_path, NEWS_STATIC_PATH)



@st.cache_resource(show_spinner=False)
def _start_news_background_updater():
    def worker():
        while True:
            started = time.monotonic()
            try:
                _write_news_snapshot()
            except Exception:
                pass
            time.sleep(max(1.0, NEWS_BACKGROUND_INTERVAL_SECONDS - (time.monotonic() - started)))

    thread = threading.Thread(target=worker, name="eastmoney-news-updater", daemon=True)
    thread.start()
    return thread



_start_news_background_updater()

st.markdown("""
<style>
.block-container { padding-top: 0.70rem; padding-bottom: 2rem; max-width: 1760px; }
html, body, [class*="css"] { font-family: "Noto Sans TC", "Noto Sans CJK TC", "Microsoft JhengHei", "PingFang TC", "Segoe UI", sans-serif; }
.dashboard-title { font-size: 1.9rem; font-weight: 700; letter-spacing: -0.02em; margin-bottom: 0.1rem; }
.section-title { font-size: 1.18rem; font-weight: 680; letter-spacing: -0.012em; margin-top: 0.52rem; margin-bottom: 0.04rem; min-height: 26px; display: flex; align-items: center; color:#1f2937; }
.section-description { color: #7b8493; font-size: 0.80rem; margin-bottom: 0.16rem; min-height: 17px; display: flex; align-items: center; }
.mini-description { color: #6b7280; font-size: 0.74rem; line-height: 1.42; margin: 1px 0 5px; }
.source-text { color: #6b7280; font-size: 0.72rem; margin: 2px 0 6px; line-height: 1.35; }
.source-text a { color: #6b7280; text-decoration: none !important; white-space: nowrap; }
.source-text a:hover { color: #374151; text-decoration: underline !important; }
.data-health-warning { color:#991b1b; background:rgba(254,242,242,.94); border:1px solid #fecaca; border-radius:6px; padding:3px 6px; font-size:.68rem; line-height:1.25; }
.source-sep { color: #d1d5db; margin: 0 5px; }
.chart-divider { margin: 0.18rem 0 0.38rem; border-top: 1px solid #e5e7eb; }
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
.market-group { border: 1px solid #e5e7eb; border-radius: 8px; padding: 6px 8px 5px; background: #fff; min-width: 0; min-height: 96px; box-sizing: border-box; }
.market-group-title { color: #374151; font-size: 0.88rem; font-weight: 650; margin-bottom: 5px; }
.market-group-row { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 4px; min-height: 66px; align-items: start; }
.market-group-row.two { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.market-item { min-width: 0; height: 66px; min-height: 66px; max-height: 66px; padding-right: 4px; border-right: 1px solid #f0f0f0; box-sizing: border-box; overflow: hidden; }
.market-item:last-child { border-right: none; }
.market-name { color: #6b7280; font-size: 0.78rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.market-price { color: #111827; font-size: 0.98rem; font-weight: 650; margin-top: 1px; white-space: nowrap; }
.market-change { font-size: 0.76rem; white-space: nowrap; }
.market-meta { color: #9ca3af; font-size: 0.66rem; margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
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
@media (max-width: 900px) { .market-groups { grid-template-columns: 1fr; } }

html { scroll-behavior: smooth; }
.dashboard-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; padding: 3px 0 10px; margin-bottom: 10px; border-bottom: 1px solid #e5e7eb; }
.dashboard-heading { min-width: 0; }
.dashboard-eyebrow { color: #9ca3af; font-size: 0.68rem; font-weight: 700; letter-spacing: 0.14em; margin-bottom: 2px; }
.dashboard-subtitle { color: #6b7280; font-size: 0.82rem; line-height: 1.5; margin-top: 2px; }
.dashboard-links { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 6px; max-width: 620px; padding-top: 4px; }
.dashboard-links a { color: #374151 !important; text-decoration: none !important; font-size: 0.76rem; line-height: 1; padding: 7px 10px; border: 1px solid #e5e7eb; border-radius: 999px; background: #fff; white-space: nowrap; }
.dashboard-links a:hover { border-color: #9ca3af; background: #f9fafb; color: #111827 !important; }
.dashboard-links a.external { font-weight: 650; }
.section-anchor { height: 0; visibility: hidden; scroll-margin-top: 18px; }
.section-kicker { color: #9ca3af; font-size: 0.66rem; font-weight: 700; letter-spacing: 0.12em; margin-top: 0.12rem; margin-bottom: 0.04rem; line-height: 1.1; }
.section-toolbar-note { color: #9ca3af; font-size: 0.72rem; margin-top: -0.15rem; margin-bottom: 0.5rem; }
div[data-testid="stVerticalBlockBorderWrapper"] { border-color: #e5e7eb !important; border-radius: 12px !important; }
div[data-testid="stPlotlyChart"] { border: 1px solid #e5eaf0; border-radius: 12px; padding: 0; background: #fff; overflow: hidden; box-shadow: 0 1px 2px rgba(15,23,42,.03); }
.stButton > button { border-radius: 8px; }
.source-text a { display: inline-block; padding: 1px 0; }
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
        <div class="dashboard-subtitle" style="font-size:.68rem;color:#64748b">运行代码：{CHART_BUILD} · 自适应坐标轴</div>
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


def _save_watchlists():
    payload = {}
    for key in WATCHLIST_KEYS:
        items = st.session_state.get(f"{key}_confirmed", [])
        if isinstance(items, dict):
            items = [items]
        payload[key] = items if isinstance(items, list) else []
    # v3 is compressed + URL-safe and remains backward-compatible on load.
    st.query_params[WATCHLIST_PARAM] = encode_watchlists(payload)

_load_watchlists()

def _empty_quote():
    return {"price": None, "change_pct": None, "market_state": "", "currency": "", "post_price": None, "post_change_pct": None, "pre_price": None, "pre_change_pct": None, "overnight_price": None, "overnight_change_pct": None, "overnight_market_time": None, "regular_market_time": None, "post_market_time": None, "pre_market_time": None, "quote_source": "", "delayed_by": None, "data_source": ""}


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
                "delayed_by": None if market == "HK" else 0,
                "data_source": "腾讯港股公共行情" if market == "HK" else "腾讯实时行情",
            })
            return row
        except Exception:
            continue
    return _empty_quote()


def _sina_hk_quote_code(symbol):
    raw = str(symbol or "").upper().strip()
    if raw.endswith(".HK") and raw[:-3].isdigit():
        return f"rt_hk{raw[:-3].zfill(5)}"
    return ""


def _get_sina_hk_quote_safe(symbol):
    """Free public HK quote snapshot from Sina's rt_hk feed."""
    code = _sina_hk_quote_code(symbol)
    if not code:
        return _empty_quote()
    try:
        response = requests.get(
            f"https://hq.sinajs.cn/rn={int(time.time() * 1000)}&list={code}",
            headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://finance.sina.com.cn/",
                "Cache-Control": "no-cache, no-store, max-age=0",
                "Pragma": "no-cache",
            },
            timeout=2.5,
        )
        response.raise_for_status()
        raw = response.content.decode("gbk", errors="ignore")
        if '="' not in raw:
            return _empty_quote()
        payload = raw.split('="', 1)[1].split('"', 1)[0]
        fields = payload.split(",")
        if len(fields) < 19:
            return _empty_quote()

        price = float(fields[6]) if fields[6] else None
        previous = float(fields[3]) if fields[3] else None
        change_pct = float(fields[8]) if fields[8] else None
        if price is None:
            return _empty_quote()
        if change_pct is None and previous not in (None, 0):
            change_pct = (price - previous) / previous * 100.0

        quote_time = _parse_asia_minute_timestamp(fields[17], fields[18])
        row = _empty_quote()
        row.update({
            "price": price,
            "change_pct": change_pct,
            "market_state": "REGULAR",
            "currency": "HKD",
            "regular_market_time": quote_time,
            "quote_source": "Sina Finance",
            "delayed_by": None,
            "data_source": "新浪港股公共行情",
        })
        return row
    except Exception:
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
            "delayed_by": None if market == "HK" else 0,
            "data_source": "腾讯港股分时行情" if market == "HK" else "腾讯分时行情",
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

def _get_yahoo_overnight_safe(symbol, previous=None):
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
            market_time = item.get("overnightMarketTime")
            if price is not None:
                if pct is None and previous not in (None, 0):
                    pct = (price - previous) / previous * 100
                return price, pct, market_time
        except Exception:
            continue
    return None, None, None

def _get_yahoo_quote_safe(symbol):
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
            overnight_price, overnight_change_pct, overnight_market_time = None, None, None
            if _symbol_market(symbol) == "US" and (
                _us_overnight_window_now() or meta.get("marketState") in {"PREPRE", "POSTPOST"}
            ):
                overnight_price, overnight_change_pct, overnight_market_time = _get_yahoo_overnight_safe(symbol, previous)
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
                "overnight_market_time": overnight_market_time,
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
        is_hk = str(symbol).upper().endswith(".HK") or str(symbol).upper() in ("^HSI", "^HSTECH", "HSTECH.HK")
        return {
            "price": price,
            "change_pct": change_pct,
            "market_state": "REGULAR",
            "currency": "HKD" if is_hk else "CNY",
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
            "delayed_by": None if is_hk else 0,
            "data_source": "东方财富港股公共行情" if is_hk else "东方财富实时行情",
        }
    except Exception:
        return _empty_quote()


def _valid_market_timestamp(value):
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
    clock_state = _asia_clock_state(market)
    ts = _valid_market_timestamp(quote_time)
    if ts is None:
        return clock_state
    quote_dt = datetime.fromtimestamp(ts, DASHBOARD_TZ)
    now = datetime.now(DASHBOARD_TZ)
    if clock_state == "交易中" and quote_dt.date() != now.date():
        return "交易时段 · 上次报价"
    return clock_state


def _us_overnight_window_now():
    ny = datetime.now(ZoneInfo("America/New_York"))
    minute = ny.hour * 60 + ny.minute
    # Overnight US equity venues generally cover Sunday-Thursday evenings
    # and the following weekday early-morning session. Source market-state and
    # a fresh overnight timestamp are still required before displaying a quote.
    return (ny.weekday() in {6, 0, 1, 2, 3} and minute >= 20 * 60) or (ny.weekday() in {0, 1, 2, 3, 4} and minute < 4 * 60)


def _quote_session_context(row, market=""):
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


def _market_state_text(row, market=""):
    return _quote_session_context(row, market)[0]


def _market_item_html(name, price, change_pct, meta=""):
    price_text = "--" if price is None else f"{price:,.2f}"
    change_text = "--" if change_pct is None else f"{change_pct:+.2f}%"
    return f'<div class="market-item"><div class="market-name">{html.escape(name)}</div><div class="market-price">{html.escape(price_text)}</div><div class="market-change">{html.escape(change_text)}</div><div class="market-meta">{html.escape(meta)}</div></div>'

@st.cache_data(ttl=15, max_entries=256, show_spinner=False)
def _get_cached_quote(symbol, refresh_key=0):
    return _fetch_quote(symbol)


def _fetch_quote(symbol):
    """Fetch providers without Streamlit caching or session-state access."""
    market = _symbol_market(symbol)
    candidates = []

    # HK/A: Tencent and Eastmoney are peers. Always query both during the
    # trading session and choose the newest timestamp instead of accepting a
    # merely "less than 8 minutes old" Tencent snapshot. If both snapshots are
    # stale, query Tencent's independent intraday feed before falling back to
    # Yahoo (which can itself be delayed for Asian markets).
    if market in {"HK", "CN"}:
        direct_getters = (
            (_get_sina_hk_quote_safe, _get_tencent_quote_safe, _get_eastmoney_quote_safe)
            if market == "HK"
            else (_get_tencent_quote_safe, _get_eastmoney_quote_safe)
        )
        for getter in direct_getters:
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


def _quote_refresh_key(): return int(time.time() // 15)

def _quote_meta(row, market=""):
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
    if _regular_session_now(market) and age is not None:
        if market in {"HK", "CN"} and age <= DIRECT_QUOTE_FRESH_SECONDS / 60.0:
            parts.append("近实时")
        elif age > 2:
            parts.append(f"报价滞后约{int(round(age))}分")
    if row.get("_stale"):
        parts.append("上次有效报价")
    return " · ".join(parts)

@st.cache_resource(show_spinner=False)
def _last_good_quote_store():
    return {}


def _stable_quote(symbol, refresh_key=0):
    row = _get_cached_quote(symbol, refresh_key)
    return _remember_quote(symbol, row)


def _remember_quote(symbol, row):
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
    snapshot = st.session_state.get("_watchlist_quotes_snapshot", {})
    return snapshot.get(symbol, _empty_quote())


def _request_watchlist_refresh():
    st.session_state["_watchlist_refresh_pending"] = True


def _watchlist_symbols():
    symbols = []
    for key in WATCHLIST_KEYS:
        items = st.session_state.get(f"{key}_confirmed", [])
        items = [items] if isinstance(items, dict) else (items if isinstance(items, list) else [])
        for item in items:
            if isinstance(item, dict) and item.get("symbol"):
                symbols.append(item["symbol"])
    return list(dict.fromkeys(symbols))


def _load_watchlist_quotes(symbols, manual=False, progress=None):
    """Fetch in workers; apply last-good fallback and session updates here."""
    previous = st.session_state.get("_watchlist_quotes_snapshot", {})
    snapshot = {symbol: previous[symbol] for symbol in symbols if symbol in previous}
    requested = symbols if manual else [symbol for symbol in symbols if symbol not in snapshot]
    received = changed = retained = missing = completed = 0
    if requested:
        with ThreadPoolExecutor(max_workers=min(6, len(requested)), thread_name_prefix="watchlist-quote") as executor:
            futures = {executor.submit(_fetch_quote, symbol): symbol for symbol in requested}
            for future in as_completed(futures):
                symbol = futures[future]
                try:
                    row = future.result()
                    if not isinstance(row, dict):
                        row = _empty_quote()
                except Exception:
                    row = _empty_quote()
                fetched = row.get("price") is not None
                row = _remember_quote(symbol, row)
                snapshot[symbol] = row
                if fetched:
                    received += 1
                    old = previous.get(symbol)
                    market = _symbol_market(symbol)
                    if isinstance(old, dict) and _active_quote_values(old, market) != _active_quote_values(row, market):
                        changed += 1
                elif row.get("price") is not None:
                    retained += 1
                else:
                    missing += 1
                completed += 1
                if progress is not None:
                    progress.caption(f"刷新中… {completed}/{len(requested)}")
    st.session_state["_watchlist_quotes_snapshot"] = snapshot
    if manual:
        st.session_state["_watchlist_refresh_result"] = {
            "completed_at": datetime.now(DASHBOARD_TZ).strftime("%m-%d %H:%M:%S"),
            "total": len(requested), "received": received, "changed": changed,
            "retained": retained, "missing": missing,
        }


def _watchlist_refresh_status():
    result = st.session_state.get("_watchlist_refresh_result")
    if not result:
        return ""
    text = (f"刷新 {result['completed_at']} HKT · "
            f"取得报价 {result['received']}/{result['total']}")
    if result["total"] == 0:
        return text + " · 暂无自选标的"
    if result["changed"]:
        text += f" · {result['changed']} 个变化"
    if result["retained"]:
        text += f" · {result['retained']} 个请求失败，沿用旧价"
    if result["missing"]:
        text += f" · {result['missing']} 个报价暂缺"
    if result["received"] == result["total"] and result["changed"] == 0:
        text += " · 报价未变化"
    return text


def _active_quote_values(row, market=""):
    """Return price/change from the same session named by the status label."""
    market = str(market or "").upper()
    if market == "US":
        state, _ = _quote_session_context(row, market)
        if state == "夜盘" and row.get("overnight_price") is not None:
            return row.get("overnight_price"), row.get("overnight_change_pct")
        if state == "盘前" and row.get("pre_price") is not None:
            return row.get("pre_price"), row.get("pre_change_pct")
        if state == "盘后" and row.get("post_price") is not None:
            return row.get("post_price"), row.get("post_change_pct")
    return row.get("price"), row.get("change_pct")

def _load_market_quotes(refresh_key):
    """Fetch index quotes together, keeping cache and last-good semantics."""
    symbols = {
        "nasdaq": "^IXIC", "sp500": "^GSPC", "dow": "^DJI",
        "hsi": "^HSI", "hstech": "HSTECH.HK", "sh": "000001.SS",
        "sz": "399001.SZ", "csi300": "000300.SS",
    }
    snapshot = {}
    with ThreadPoolExecutor(max_workers=6, thread_name_prefix="market-index") as executor:
        futures = {executor.submit(_get_cached_quote, symbol, refresh_key): (key, symbol)
                   for key, symbol in symbols.items()}
        for future in as_completed(futures):
            key, symbol = futures[future]
            try:
                row = future.result()
            except Exception:
                row = _empty_quote()
            snapshot[key] = _remember_quote(symbol, row)
    return snapshot


def render_market_groups():
    now = time.time(); snapshot = st.session_state.get("_market_quotes_snapshot"); snapshot_time = st.session_state.get("_market_quotes_snapshot_time", 0)
    if not isinstance(snapshot, dict) or now - snapshot_time >= 60:
        refresh_key = (_quote_refresh_key(), st.session_state.get("_market_refresh_key", 0))
        snapshot = _load_market_quotes(refresh_key)
        st.session_state["_market_quotes_snapshot"] = snapshot; st.session_state["_market_quotes_snapshot_time"] = now
    q = snapshot

    def overview_item(name, row, market):
        price, change = _active_quote_values(row, market)
        return _market_item_html(name, price, change, _quote_meta(row, market))

    groups = [
        ("🇺🇸 美股", [overview_item("纳斯达克", q["nasdaq"], "US"), overview_item("标普500", q["sp500"], "US"), overview_item("道琼斯", q["dow"], "US")], "three"),
        ("🇭🇰 港股", [overview_item("恒生指数", q["hsi"], "HK"), overview_item("恒生科技", q["hstech"], "HK")], "two"),
        ("🇨🇳 A股", [overview_item("上证指数", q["sh"], "CN"), overview_item("深证成指", q["sz"], "CN"), overview_item("沪深300", q["csi300"], "CN")], "three"),
    ]
    cards = []
    for title, items, grid_class in groups: cards.append(f'<div class="market-group"><div class="market-group-title">{title}</div><div class="market-group-row {grid_class}">' + "".join(items) + '</div></div>')
    st.markdown('<div class="market-groups">' + "".join(cards) + '</div>', unsafe_allow_html=True)

st.markdown('<div id="market-overview" class="section-anchor"></div><div class="section-kicker">MARKET OVERVIEW</div>', unsafe_allow_html=True)
st.markdown('<div class="section-title">市场概览</div><div class="section-description">美股、港股与 A 股主要指数</div>', unsafe_allow_html=True)

@st.fragment(key="market_overview")
def render_market_overview():
    _, refresh_col = st.columns([8.6, 1.4], vertical_alignment="center")
    with refresh_col:
        if st.button("↻ 刷新行情", key="refresh_market_overview", use_container_width=True):
            st.session_state["_market_quotes_snapshot_time"] = 0
            st.session_state["_market_refresh_key"] = st.session_state.get("_market_refresh_key", 0) + 1
    render_market_groups()

render_market_overview()

@st.cache_data(ttl=20, show_spinner=False)
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
        quote_type = str(item.get("quoteType") or "").upper()
        allowed_types = {"EQUITY", "INDEX"} if market == "US" else {"EQUITY"}
        if quote_type not in allowed_types:
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

def _render_quote_block(item):
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
        state_label, _ = _quote_session_context(row, "US")
        if state_label == "夜盘" and overnight_price is not None:
            time_label = _market_time_label(row.get("overnight_market_time"))
            session_text = f'夜盘 {overnight_price:,.2f} · {"--" if overnight_change is None else f"{overnight_change:+.2f}%"}' + (f" · {time_label}" if time_label else "")
        elif state_label == "盘前" and pre_price is not None:
            time_label = _market_time_label(row.get("pre_market_time"))
            session_text = f'盘前 {pre_price:,.2f} · {"--" if pre_change is None else f"{pre_change:+.2f}%"}' + (f" · {time_label}" if time_label else "")
        elif state_label == "盘后" and pp is not None:
            time_label = _market_time_label(row.get("post_market_time"))
            session_text = f'盘后 {pp:,.2f} · {"--" if pc is None else f"{pc:+.2f}%"}' + (f" · {time_label}" if time_label else "")

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

st.markdown('<div id="watchlist" class="section-anchor"></div><div class="section-kicker">WATCHLIST</div>', unsafe_allow_html=True)
st.markdown('<div class="section-title">自选观察</div>', unsafe_allow_html=True)

@st.fragment(key="watchlists")
def render_watchlists():
    pending = st.session_state.get("_watchlist_refresh_pending", False)
    info_col, refresh_col = st.columns([8.6, 1.4], vertical_alignment="center")
    with info_col:
        st.markdown('<div class="watch-toolbar">自选股票与指数 · 可添加或删除</div>', unsafe_allow_html=True)
    with refresh_col:
        refresh_slot = st.empty()
        if pending:
            refresh_slot.button("刷新中…", key="refresh_watchlist_quotes_busy", disabled=True)
        else:
            refresh_slot.button("↻ 刷新", key="refresh_watchlist_quotes", on_click=_request_watchlist_refresh, help="只刷新下方自选模块报价，不刷新市场概览")

    status_slot = st.empty()
    symbols = _watchlist_symbols()
    snapshot = st.session_state.get("_watchlist_quotes_snapshot", {})
    if pending or any(symbol not in snapshot for symbol in symbols):
        try:
            with st.spinner("正在获取自选行情…"):
                _load_watchlist_quotes(symbols, manual=pending, progress=status_slot)
        finally:
            if pending:
                st.session_state["_watchlist_refresh_pending"] = False
                refresh_slot.empty()
                refresh_slot.button("↻ 刷新", key="refresh_watchlist_quotes", on_click=_request_watchlist_refresh, help="只刷新下方自选模块报价，不刷新市场概览")
    status = _watchlist_refresh_status()
    if status:
        status_slot.caption(status)
    else:
        status_slot.empty()

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

def add_sources(sources):
    links = [f'<a href="{html.escape(url, quote=True)}" target="_blank" rel="noopener noreferrer">{html.escape(text)}</a>' for text, url in sources]
    st.markdown('<div class="source-text">Source: ' + '<span class="source-sep">|</span>'.join(links) + '</div>', unsafe_allow_html=True)

def _mark_missing_series(fig, name):
    meta = fig.layout.meta if isinstance(fig.layout.meta, dict) else {}
    meta = dict(meta or {})
    missing = list(meta.get("missing_series") or [])
    if name not in missing:
        missing.append(name)
    meta["missing_series"] = missing
    fig.update_layout(meta=meta)


def add_line(fig, data, column, name, width=2.5, dash=None, yaxis=None, unit="%"):
    if column not in data.columns or data[column].notna().sum() == 0:
        _mark_missing_series(fig, name)
        return
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
    base_right = 60 if has_secondary else 20
    # Reserve separate vertical bands for the top year axis and legend.
    base_top = 88 if compact_mode else 92
    base_bottom = 34

    fig.update_layout(
        height=height,
        template="plotly_white",
        hovermode="closest" if compact_mode else "x unified",
        dragmode=False,
        margin=dict(l=base_left, r=base_right, t=base_top, b=base_bottom, pad=2),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.105, xanchor="left", x=0,
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
    # Shared adaptive lower axis + centered upper year axis. Missing traces are
    # surfaced inside the plot instead of disappearing silently.
    fig = apply_time_axis(fig, date_range)
    meta = fig.layout.meta if isinstance(fig.layout.meta, dict) else {}
    missing = list((meta or {}).get("missing_series") or [])
    if missing:
        fig.add_annotation(
            text="⚠ 数据缺失：" + " · ".join(missing),
            x=0.006, y=0.988, xref="paper", yref="paper",
            xanchor="left", yanchor="top", showarrow=False,
            font=dict(size=10, color="#991b1b"),
            bgcolor="rgba(254,242,242,0.94)", bordercolor="#fecaca", borderwidth=1, borderpad=3,
        )
    return fig

def filter_range(data, date_range):
    """Slice from the latest valid observation, matching the shared X-axis anchor."""
    if data.empty or "observation_date" not in data.columns:
        return data.copy()
    dates = pd.to_datetime(data["observation_date"], errors="coerce")
    if getattr(dates.dt, "tz", None) is not None:
        dates = dates.dt.tz_localize(None)
    latest = dates.max()
    if pd.isna(latest):
        return data.copy()
    offset = RANGE_OFFSETS.get(date_range, RANGE_OFFSETS["1Y"])
    start = latest - offset
    return data.loc[dates >= start].copy()
def chart_height(compact, normal): return compact if compact_mode else normal

@st.cache_data(ttl=3600, show_spinner=False)
def get_fred_series(series_id): return _fred_series(series_id)



# === HK LIQUIDITY CHART 5 ===
@st.cache_data(ttl=3600, show_spinner=False, refresh_mode="background")
def get_hk_liquidity():
    return load_hk_liquidity()


def build_fig5(date_range, market_mode="Raw"):
    return build_hk_liquidity_figures(date_range, compact_mode=False, market_mode=market_mode)


def apply_hk_chart_range(fig, date_range):
    """Apply the same dashboard-wide adaptive time axis to charts 5-8."""
    return apply_time_axis(fig, date_range)

def build_fig1(date_range):
    data = get_iorb().merge(get_rrp_rate(), on="observation_date", how="outer").merge(get_effr(), on="observation_date", how="outer").merge(get_sofr(), on="observation_date", how="outer").sort_values("observation_date"); data = filter_range(data, date_range); fig = go.Figure()
    for column, name, width in [("IORB", "IORB", 2.6), ("RRPONTSYAWARD", "ON RRP", 2.6), ("EFFR", "EFFR", 2.6), ("SOFR", "SOFR", 2.2)]: add_line(fig, data, column, name, width)
    fig.update_layout(yaxis_title="Rate (%)"); return apply_chart_style(fig, chart_height(310, 420), date_range)

def build_fig2(date_range):
    """10Y Treasury yield structure plus observed 5Y TIPS real yield.

    DFII5 is the Federal Reserve's *observed* 5Y inflation-indexed
    constant-maturity yield, not DGS5 minus an inferred inflation rate.
    Missing DFII5 observations must remain missing, not interpolated.
    """
    observed_nominal = get_dgs10()
    inferred_dates = list(observed_nominal.attrs.get("identity_derived_dates", []))
    data = (
        observed_nominal
        .merge(get_dfii10(), on="observation_date", how="outer")
        .merge(get_dfii5(), on="observation_date", how="outer")
        .merge(get_fred_series("T10YIE"), on="observation_date", how="outer")
        .sort_values("observation_date")
    )
    for column in ("DGS10", "DFII10", "DFII5", "T10YIE"):
        data[column] = pd.to_numeric(data.get(column), errors="coerce")
    # Do NOT silently manufacture missing DFII10 or T10YIE observations.
    # DGS10 may contain an algebraic identity backfill from the data layer;
    # disclose such dates explicitly rather than representing them as measured.
    data = filter_range(data, date_range)
    fig = go.Figure()
    if inferred_dates:
        fig.update_layout(meta={"data_quality_notes": [
            f"10Y 名义收益率有 {len(inferred_dates)} 个日期由 DFII10＋T10YIE 恒等式重建（非独立 DGS10 实测值）。"
        ]})
    for column, name, width, dash, yaxis in [
        ("DGS10", "10Y Nominal", 2.8, None, None),
        ("DFII10", "10Y Real (R1)", 2.6, None, "y2"),
        ("DFII5", "5Y Real · TIPS (R1)", 2.6, "dash", "y2"),
        ("T10YIE", "10Y Breakeven (R1)", 2.5, "dot", "y2"),
    ]:
        add_line(fig, data, column, name, width, dash, yaxis)
    fig.update_layout(
        yaxis_title="Nominal Yield (%)",
        yaxis2=dict(
            title="Real yield / breakeven (%)", overlaying="y", side="right",
            anchor="free", position=0.99, showgrid=False, zeroline=False,
            fixedrange=True, automargin=False, tickfont=dict(size=9),
            ticks="outside", ticklen=3,
        ),
    )
    return apply_chart_style(fig, chart_height(310, 420), date_range)

def build_fig4(date_range):
    """US liquidity chart with separate scales for unlike balance magnitudes.

    L: Net Liquidity = WALCL - TGA - ON RRP, USD trillions.
    R1: Reserve Balances and TGA, USD trillions.
    R2: ON RRP, USD billions.
    """
    specs = [
        (get_walcl, "WALCL", 1_000_000.0),
        (get_wresbal, "WRESBAL", 1_000_000.0),
        (get_tga_daily, "TGA_DAILY", 1.0),
        (get_rrp_daily, "RRPONTSYD", 1.0),
    ]
    raw_series = {}
    tga_is_fallback = False
    for getter, column, divisor in specs:
        try:
            frame = getter().copy()
            if column == "TGA_DAILY":
                tga_is_fallback = bool(frame.attrs.get("is_fallback", False))
            frame["observation_date"] = pd.to_datetime(frame["observation_date"], errors="coerce")
            frame[column] = pd.to_numeric(frame[column], errors="coerce") / divisor
            frame = frame.dropna(subset=["observation_date", column]).sort_values("observation_date")[["observation_date", column]]
            if not frame.empty:
                raw_series[column] = frame
        except Exception:
            continue

    fig = go.Figure()
    if not raw_series:
        for name in ("Net Liquidity", "Reserve Balances", "TGA", "ON RRP"):
            _mark_missing_series(fig, name)
        return apply_chart_style(fig, chart_height(320, 430), date_range)

    # Calculate the proxy on a union calendar. Forward filling is only used
    # inside the mixed-frequency calculation; displayed source traces remain
    # at their native observation dates.
    calc = None
    for column in ("WALCL", "TGA_DAILY", "RRPONTSYD"):
        frame = raw_series.get(column)
        if frame is None:
            continue
        calc = frame.copy() if calc is None else calc.merge(frame, on="observation_date", how="outer")
    calc = pd.DataFrame(columns=["observation_date"]) if calc is None else calc.sort_values("observation_date")
    component_cols = [c for c in ("WALCL", "TGA_DAILY", "RRPONTSYD") if c in calc.columns]
    if component_cols:
        calc[component_cols] = calc[component_cols].ffill()
    if all(c in calc.columns for c in ("WALCL", "TGA_DAILY", "RRPONTSYD")):
        calc["NetLiquidity"] = calc["WALCL"] - calc["TGA_DAILY"] - calc["RRPONTSYD"] / 1000.0
    calc = filter_range(calc, date_range)

    add_line(fig, calc, "NetLiquidity", "Net Liquidity", 3.0, unit=" T")

    reserve = raw_series.get("WRESBAL")
    if reserve is not None:
        add_line(fig, filter_range(reserve, date_range), "WRESBAL", "Reserve Balances (R1)", 2.4, yaxis="y2", unit=" T")
    else:
        _mark_missing_series(fig, "Reserve Balances")

    tga = raw_series.get("TGA_DAILY")
    if tga is not None:
        tga_name = "TGA · Weekly fallback (R1)" if tga_is_fallback else "TGA (R1)"
        add_line(fig, filter_range(tga, date_range), "TGA_DAILY", tga_name, 2.2, "dash", "y2", " T")
    else:
        _mark_missing_series(fig, "TGA")

    rrp = raw_series.get("RRPONTSYD")
    if rrp is not None:
        add_line(fig, filter_range(rrp, date_range), "RRPONTSYD", "ON RRP (R2)", 2.2, "dot", "y3", " B")
    else:
        _mark_missing_series(fig, "ON RRP")

    # Predeclare secondary axes so apply_chart_style reserves enough space.
    fig.update_layout(
        yaxis2=dict(overlaying="y", side="right", anchor="free", position=0.925),
        yaxis3=dict(overlaying="y", side="right", anchor="free", position=0.99),
    )
    fig = apply_chart_style(fig, chart_height(320, 430), date_range)
    fig.update_layout(
        margin=dict(l=64, r=92, t=72, b=34, pad=2),
        legend=dict(y=1.09, x=0.01),
        xaxis=dict(domain=[0.0, 0.91]),
        yaxis=dict(
            title="Net Liquidity · USD T",
            showgrid=True, gridcolor="#e5e7eb", griddash="dot",
            zeroline=False, fixedrange=True, tickformat=".1f",
        ),
        yaxis2=dict(
            title="",
            overlaying="y", side="right", anchor="free", position=0.925,
            showgrid=False, zeroline=False, fixedrange=True,
            tickformat=".1f", tickfont=dict(size=9), ticks="outside", ticklen=3,
        ),
        yaxis3=dict(
            title="",
            overlaying="y", side="right", anchor="free", position=0.99,
            showgrid=False, zeroline=True, zerolinecolor="#94a3b8",
            zerolinewidth=1, fixedrange=True, tickformat=".0f",
            tickfont=dict(size=9), ticks="outside", ticklen=3,
        ),
    )
    return fig


def build_fig3(date_range):
    dgs10 = get_dgs10()
    inferred_dates = list(dgs10.attrs.get("identity_derived_dates", []))
    data = get_dgs3mo().merge(get_dgs2(), on="observation_date", how="outer").merge(dgs10, on="observation_date", how="outer").sort_values("observation_date")
    for column in ("DGS3MO", "DGS2", "DGS10"):
        data[column] = pd.to_numeric(data.get(column), errors="coerce")
    # Derive curve spreads locally from the displayed yields. This removes two
    # redundant FRED requests and guarantees spread/yield internal consistency.
    data["T10Y2Y"] = data["DGS10"] - data["DGS2"]
    data["T10Y3M"] = data["DGS10"] - data["DGS3MO"]
    data = filter_range(data, date_range); fig = go.Figure()
    if inferred_dates:
        fig.update_layout(meta={"data_quality_notes": [
            f"10Y 名义收益率有 {len(inferred_dates)} 个日期由 DFII10＋T10YIE 恒等式重建（非独立 DGS10 实测值）。"
        ]})
    for column, name, width in [("DGS3MO", "3M", 2.2), ("DGS2", "2Y", 2.4), ("DGS10", "10Y", 2.8)]: add_line(fig, data, column, name, width)
    add_line(fig, data, "T10Y2Y", "10Y−2Y (R1)", 2.2, "dot", "y2", "%"); add_line(fig, data, "T10Y3M", "10Y−3M (R1)", 2.2, "dash", "y2", "%")
    fig.update_traces(selector=dict(name="10Y−2Y (R1)"), hovertemplate="10Y−2Y (R1): %{y:.3f}%<extra></extra>"); fig.update_traces(selector=dict(name="10Y−3M (R1)"), hovertemplate="10Y−3M (R1): %{y:.3f}%<extra></extra>")
    fig.update_layout(yaxis=dict(title="Yield (%)", fixedrange=True), yaxis2=dict(title="", overlaying="y", side="right", anchor="free", position=0.99, showgrid=False, zeroline=True, zerolinecolor="#9ca3af", fixedrange=True, automargin=False, tickfont=dict(size=9), ticks="outside", ticklen=3)); return apply_chart_style(fig, chart_height(310, 420), date_range)


def build_fig9(date_range):
    """US equity risk: index vol, constituent vol, VIX term spread, and SPX."""
    frames = []
    for series_id in ("VIXCLS", "VXVCLS", "SP500"):
        try:
            frame = get_fred_series(series_id).copy()
            frame["observation_date"] = pd.to_datetime(frame["observation_date"], errors="coerce")
            frame[series_id] = pd.to_numeric(frame[series_id], errors="coerce")
            frame = frame.dropna(subset=["observation_date", series_id])[["observation_date", series_id]]
            if not frame.empty:
                frames.append(frame)
        except Exception:
            continue

    try:
        vixeq = load_vixeq_snapshot()
        if not vixeq.empty:
            frames.append(vixeq)
    except Exception:
        pass

    if not frames:
        fig = go.Figure()
        for name in ("VIX", "VIXEQ", "S&P 500 (R1)", "VIX3M−VIX (R2)"):
            _mark_missing_series(fig, name)
        return apply_chart_style(fig, chart_height(320, 440), date_range)

    data = frames[0]
    for frame in frames[1:]:
        data = data.merge(frame, on="observation_date", how="outer")
    data = data.sort_values("observation_date")
    if "VIXCLS" in data.columns and "VXVCLS" in data.columns:
        data["VIX3M-VIX"] = data["VXVCLS"] - data["VIXCLS"]
    data = filter_range(data, date_range)

    fig = go.Figure()
    add_line(fig, data, "VIXCLS", "VIX", 2.7, unit="")
    add_line(fig, data, "VIXEQ", "VIXEQ", 2.4, "dash", unit="")
    add_line(fig, data, "SP500", "S&P 500 (R1)", 2.4, None, "y2", unit=" pts")
    add_line(fig, data, "VIX3M-VIX", "VIX3M−VIX (R2)", 2.0, "dot", "y3", unit=" pts")

    fig.update_layout(
        yaxis2=dict(overlaying="y", side="right", anchor="free", position=0.925),
        yaxis3=dict(overlaying="y", side="right", anchor="free", position=0.99),
    )
    fig = apply_chart_style(fig, chart_height(320, 440), date_range)
    fig.update_layout(
        margin=dict(l=62, r=92, t=68, b=36, pad=2),
        legend=dict(y=1.095),
        xaxis=dict(domain=[0.0, 0.91]),
        yaxis=dict(
            title="VIX / VIXEQ",
            showgrid=True, gridcolor="#e5e7eb", griddash="dot",
            zeroline=False, fixedrange=True,
        ),
        yaxis2=dict(
            title="",
            overlaying="y", side="right", anchor="free", position=0.925,
            showgrid=False, zeroline=False, fixedrange=True, tickfont=dict(size=9), ticks="outside", ticklen=3,
        ),
        yaxis3=dict(
            title="",
            overlaying="y", side="right", anchor="free", position=0.99,
            showgrid=False, zeroline=True, zerolinecolor="#94a3b8",
            zerolinewidth=1, fixedrange=True, tickfont=dict(size=9), ticks="outside", ticklen=3,
        ),
    )
    return fig


@st.cache_data(ttl=3600, show_spinner=False)
def get_yahoo_daily_history(symbol):
    """Fetch five years of completed daily closes from Yahoo chart API."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{requests.utils.quote(symbol, safe='')}"
    response = requests.get(
        url,
        params={"range": "5y", "interval": "1d", "includePrePost": "false", "events": "div,splits"},
        headers={"User-Agent": "Mozilla/5.0 (compatible; MacroDashboard/1.0)"},
        timeout=(3.0, 8.0),
    )
    response.raise_for_status()
    result = ((response.json() or {}).get("chart") or {}).get("result") or []
    if not result:
        return pd.DataFrame(columns=["observation_date", "close"])
    node = result[0]
    timestamps = node.get("timestamp") or []
    quotes = (((node.get("indicators") or {}).get("quote") or [{}])[0]).get("close") or []
    if not timestamps or not quotes:
        return pd.DataFrame(columns=["observation_date", "close"])
    size = min(len(timestamps), len(quotes))
    dates = pd.to_datetime(timestamps[:size], unit="s", utc=True)
    tz_name = (node.get("meta") or {}).get("exchangeTimezoneName") or "America/New_York"
    try:
        dates = dates.tz_convert(tz_name).tz_localize(None).normalize()
    except Exception:
        dates = dates.tz_convert("America/New_York").tz_localize(None).normalize()
    frame = pd.DataFrame({"observation_date": dates, "close": pd.to_numeric(quotes[:size], errors="coerce")})
    frame = frame.dropna(subset=["observation_date", "close"]).sort_values("observation_date")
    return frame.drop_duplicates("observation_date", keep="last")


def _rebase_100(series):
    values = pd.to_numeric(series, errors="coerce")
    valid = values.dropna()
    if valid.empty or float(valid.iloc[0]) == 0:
        return values * pd.NA
    return values / float(valid.iloc[0]) * 100.0


def _load_yahoo_histories(symbols):
    """Load independent histories together without changing their data window."""
    frames = {}
    with ThreadPoolExecutor(max_workers=min(2, len(symbols)), thread_name_prefix="market-history") as executor:
        futures = {executor.submit(get_yahoo_daily_history, symbol): symbol for symbol in symbols}
        for future in as_completed(futures):
            try:
                frames[futures[future]] = future.result()
            except Exception:
                frames[futures[future]] = pd.DataFrame(columns=["observation_date", "close"])
    return frames


def build_fig10(date_range, market_mode="Rebased 100"):
    """Precious metals: gold, silver, gold/silver ratio, and GVZ."""
    frames = []
    histories = _load_yahoo_histories(("GC=F", "SI=F"))
    for symbol, column in (("GC=F", "Gold"), ("SI=F", "Silver")):
        try:
            frame = histories[symbol].rename(columns={"close": column})
            if not frame.empty:
                frames.append(frame[["observation_date", column]])
        except Exception:
            pass
    try:
        gvz = get_fred_series("GVZCLS").copy()
        gvz["observation_date"] = pd.to_datetime(gvz["observation_date"], errors="coerce")
        gvz["GVZCLS"] = pd.to_numeric(gvz["GVZCLS"], errors="coerce")
        gvz = gvz.dropna(subset=["observation_date", "GVZCLS"])[["observation_date", "GVZCLS"]]
        if not gvz.empty:
            frames.append(gvz)
    except Exception:
        pass

    if frames:
        data = frames[0]
        for frame in frames[1:]:
            data = data.merge(frame, on="observation_date", how="outer")
        data = data.sort_values("observation_date")
    else:
        data = pd.DataFrame(columns=["observation_date"])

    if "Gold" in data.columns and "Silver" in data.columns:
        gold = pd.to_numeric(data["Gold"], errors="coerce")
        silver = pd.to_numeric(data["Silver"], errors="coerce")
        data["GoldSilverRatio"] = gold.where(silver > 0) / silver.where(silver > 0)
    data = filter_range(data, date_range)

    fig = go.Figure()
    if market_mode == "Rebased 100":
        if "Gold" in data.columns:
            data["Gold_R100"] = _rebase_100(data["Gold"])
        if "Silver" in data.columns:
            data["Silver_R100"] = _rebase_100(data["Silver"])
        add_line(fig, data, "Gold_R100", "Gold · R100", 2.8, unit="")
        add_line(fig, data, "Silver_R100", "Silver · R100", 2.5, unit="")
        add_line(fig, data, "GoldSilverRatio", "Gold/Silver Ratio (R1)", 2.2, "dash", "y2", "x")
        add_line(fig, data, "GVZCLS", "Gold Volatility · GVZ (R2)", 2.2, "dot", "y3", "")
        fig.update_layout(
            yaxis2=dict(overlaying="y", side="right", anchor="free", position=0.925),
            yaxis3=dict(overlaying="y", side="right", anchor="free", position=0.99),
        )
        fig = apply_chart_style(fig, chart_height(320, 440), date_range)
        fig.update_layout(
            margin=dict(l=62, r=92, t=72, b=34, pad=2),
            legend=dict(y=1.09, x=0.01),
            xaxis=dict(domain=[0.0, 0.91]),
            yaxis=dict(title="Gold / Silver · Rebased 100", tickformat=".1f"),
            yaxis2=dict(title="", overlaying="y", side="right", anchor="free", position=0.925, showgrid=False, fixedrange=True, tickformat=".1f", tickfont=dict(size=9), ticks="outside", ticklen=3),
            yaxis3=dict(title="", overlaying="y", side="right", anchor="free", position=0.99, showgrid=False, fixedrange=True, tickformat=".1f", tickfont=dict(size=9), ticks="outside", ticklen=3),
        )
        return fig

    add_line(fig, data, "Gold", "Gold", 2.8, unit=" USD/oz")
    add_line(fig, data, "Silver", "Silver (R1)", 2.5, None, "y2", " USD/oz")
    add_line(fig, data, "GoldSilverRatio", "Gold/Silver Ratio (R2)", 2.2, "dash", "y3", "x")
    add_line(fig, data, "GVZCLS", "Gold Volatility · GVZ (R3)", 2.2, "dot", "y4", "")
    fig.update_layout(
        yaxis2=dict(overlaying="y", side="right", anchor="free", position=0.86),
        yaxis3=dict(overlaying="y", side="right", anchor="free", position=0.93),
        yaxis4=dict(overlaying="y", side="right", anchor="free", position=0.99),
    )
    fig = apply_chart_style(fig, chart_height(330, 450), date_range)
    fig.update_layout(
        margin=dict(l=68, r=132, t=72, b=34, pad=2),
        legend=dict(y=1.09, x=0.01),
        xaxis=dict(domain=[0.0, 0.84]),
        yaxis=dict(title="Gold · USD/oz", tickformat=",.0f"),
        yaxis2=dict(title="", overlaying="y", side="right", anchor="free", position=0.86, showgrid=False, fixedrange=True, tickformat=".1f", tickfont=dict(size=9), ticks="outside", ticklen=3),
        yaxis3=dict(title="", overlaying="y", side="right", anchor="free", position=0.93, showgrid=False, fixedrange=True, tickformat=".1f", tickfont=dict(size=9), ticks="outside", ticklen=3),
        yaxis4=dict(title="", overlaying="y", side="right", anchor="free", position=0.99, showgrid=False, fixedrange=True, tickformat=".1f", tickfont=dict(size=9), ticks="outside", ticklen=3),
    )
    return fig


def build_fig11(date_range, market_mode="Rebased 100"):
    """Crypto market: BTC, ETH, ETH/BTC and 30-day BTC realized volatility."""
    frames = []
    histories = _load_yahoo_histories(("BTC-USD", "ETH-USD"))
    for symbol, column in (("BTC-USD", "BTC"), ("ETH-USD", "ETH")):
        try:
            frame = histories[symbol].rename(columns={"close": column})
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
        add_line(fig, data, "BTC_R100", "BTC · 起点100", 2.9, unit="")
        add_line(fig, data, "ETH_R100", "ETH · 起点100", 2.6, unit="")
        add_line(fig, data, "ETHBTC", "ETH/BTC 强弱 · R1", 2.2, "dash", "y2", "")
        add_line(fig, data, "BTC_VOL_30D", "BTC 30D 实际波动率 · R2", 2.2, "dot", "y3", "%")
        fig.update_layout(
            yaxis2=dict(overlaying="y", side="right", anchor="free", position=0.925),
            yaxis3=dict(overlaying="y", side="right", anchor="free", position=0.99),
        )
        fig = apply_chart_style(fig, chart_height(320, 440), date_range)
        fig.update_layout(
            margin=dict(l=62, r=92, t=72, b=34, pad=2),
            legend=dict(y=1.09, x=0.01),
            xaxis=dict(domain=[0.0, 0.91]),
            yaxis=dict(title="BTC / ETH · 起点=100", tickformat=".1f"),
            yaxis2=dict(title="", overlaying="y", side="right", anchor="free", position=0.925, showgrid=False, fixedrange=True, tickformat=".4f", tickfont=dict(size=9), ticks="outside", ticklen=3),
            yaxis3=dict(title="", overlaying="y", side="right", anchor="free", position=0.99, showgrid=False, fixedrange=True, tickformat=".0f", tickfont=dict(size=9), ticks="outside", ticklen=3),
        )
        return fig

    add_line(fig, data, "BTC", "BTC · USD", 2.9, unit=" USD")
    add_line(fig, data, "ETH", "ETH · USD · R1", 2.6, None, "y2", " USD")
    add_line(fig, data, "ETHBTC", "ETH/BTC 强弱 · R2", 2.2, "dash", "y3", "")
    add_line(fig, data, "BTC_VOL_30D", "BTC 30D 实际波动率 · R3", 2.2, "dot", "y4", "%")
    fig.update_layout(
        yaxis2=dict(overlaying="y", side="right", anchor="free", position=0.86),
        yaxis3=dict(overlaying="y", side="right", anchor="free", position=0.93),
        yaxis4=dict(overlaying="y", side="right", anchor="free", position=0.99),
    )
    fig = apply_chart_style(fig, chart_height(330, 450), date_range)
    fig.update_layout(
        margin=dict(l=72, r=132, t=72, b=34, pad=2),
        legend=dict(y=1.09, x=0.01),
        xaxis=dict(domain=[0.0, 0.84]),
        yaxis=dict(title="BTC · USD", tickformat=",.0f"),
        yaxis2=dict(title="", overlaying="y", side="right", anchor="free", position=0.86, showgrid=False, fixedrange=True, tickformat=",.0f", tickfont=dict(size=9), ticks="outside", ticklen=3),
        yaxis3=dict(title="", overlaying="y", side="right", anchor="free", position=0.93, showgrid=False, fixedrange=True, tickformat=".4f", tickfont=dict(size=9), ticks="outside", ticklen=3),
        yaxis4=dict(title="", overlaying="y", side="right", anchor="free", position=0.99, showgrid=False, fixedrange=True, tickformat=".0f", tickfont=dict(size=9), ticks="outside", ticklen=3),
    )
    return fig


def build_fig12(date_range):
    return build_copper_flow_spread_figure(date_range)


CRYPTO_MARKET_DESCRIPTION = (
    '<b>读取提示：</b>BTC / ETH 看相对表现；ETH/BTC 上升表示 ETH 更强；30D 实际波动率看波动大小。Rebased 100 使用完整 5Y 样本的固定起点，Raw 显示美元价格。R1–R3 为右轴。'
)


PARAM_DESCRIPTIONS = [
    '<b>读取提示：</b>IORB / ON RRP 是美联储工具利率；EFFR / SOFR 分别反映无担保与国债抵押的隔夜资金成本。',
    '<b>读取提示：</b>美国 5Y Real（DFII5）与 10Y Real（DFII10）为 TIPS 实际收益率，使用官方原始观测值，均在 R1 右轴；10Y 名义收益率在左轴。10Y Breakeven 为通胀补偿指标，不等同于未来实际通胀。',
    '<b>读取提示：</b>10Y−2Y / 10Y−3M 上升表示曲线变陡，负值表示倒挂；利差单位为百分点。',
    '<b>读取提示：</b>净流动性代理＝美联储资产−TGA−ON RRP。左轴与 R1 为万亿美元，R2 为十亿美元；准备金为周频，TGA 不可用时回退到周频。',
    '<b>读取提示：</b>M2 / M3 同比看货币趋势，总结余与 HIBOR 看资金松紧；港元接近 7.85 时偏弱。月度数据有公布时滞。',
]


def show_parameter_description(index): st.markdown(f'<div class="mini-description">{PARAM_DESCRIPTIONS[index]}</div>', unsafe_allow_html=True)

HK_PARAMETER_DESCRIPTIONS = [
    '<b>读取提示：</b>M2 同比看趋势、环比看边际变化；货币基础同比看基础货币变化。Raw 显示价格与点位，Rebased 100 用固定 5Y 起点比较相对涨跌。月度数据有公布时滞。',
    '<b>读取提示：</b>总结余下降通常表示港元流动性收紧；EFBN 看票据及债券总量与银行持仓。单位均为十亿港元，历史为月末值。',
    '<b>读取提示：</b>O/N / 3M HIBOR 分别看短端与持续融资成本；O/N−3M 转正提示短端资金压力。历史为月末值，单位为 %。',
    '<b>读取提示：</b>USD/HKD 左轴反向：上方 7.75 为港元偏强，下方 7.85 为偏弱；红区 7.84–7.85 提示弱方压力。Rebased 100 用固定 5Y 起点比较市场资产。',
]


def show_hk_parameter_description(index):
    st.markdown(f'<div class="mini-description">{HK_PARAMETER_DESCRIPTIONS[index]}</div>', unsafe_allow_html=True)


US_EQUITY_RISK_DESCRIPTION = (
    '<b>读取提示：</b>VIX 看指数隐含波动，VIXEQ 看成分股隐含波动；VIX3M−VIX 收窄或转负提示近端压力。VIXEQ 早期数据为官方回溯序列。'
)



PRECIOUS_METALS_DESCRIPTION = (
    '<b>读取提示：</b>金银比上升表示黄金更强；GVZ 看黄金隐含波动。Rebased 100 使用固定 5Y 起点，Raw 显示 USD/oz；R1–R3 为右轴。'
)


compact_mode = False

def _prepare_chart_for_client_ranges(fig, element_key, mode=None):
    """Attach browser-side time controls to a complete five-year figure."""
    fig = apply_client_time_controls(fig, default_range=DEFAULT_CHART_RANGE)
    revision = f"{element_key}:client-range:{DEFAULT_CHART_RANGE}:r21"
    if mode is not None:
        revision += f":{mode}"
    # Do not preserve stale browser axes across a rerun: viewport Y ranges must win.
    fig.update_layout(uirevision=None)
    return fig




def _recoverable_echarts_option(fig, element_key, date_range, mode=None):
    """Retain a last-good *full-history* client chart across Streamlit reruns.

    The dashboard rebuilds figures periodically. A transient converter/data
    failure must not silently replace a working, self-rescaling ECharts chart
    with Plotly's fixed five-year Y axis. Cached data stays marked stale.
    """
    cache_key = f"_echarts_last_good_{element_key}_{mode or 'default'}"
    builder = getattr(_echarts_axes, "build_adaptive_echarts_option", None)
    option = None
    if callable(builder):
        try:
            option = builder(fig, date_range)
        except Exception:
            logging.exception("ECharts conversion failed for %s (%s)", element_key, date_range)

    state = getattr(st, "session_state", None)
    if isinstance(option, dict) and option.get("series"):
        if state is not None:
            state[cache_key] = deepcopy(option)
        return option, False

    previous = state.get(cache_key) if state is not None else None
    if not isinstance(previous, dict) or not previous.get("series"):
        return None, False

    # Every ECharts option includes all historic observations: only the
    # requested viewport changes between 5Y/1Y/6M/3M/1M.
    recovered = deepcopy(previous)
    try:
        zooms = recovered["dataZoom"]
        latest = pd.Timestamp(zooms[0]["endValue"])
        if pd.isna(latest):
            return None, False
        offset = RANGE_OFFSETS.get(date_range, RANGE_OFFSETS["1Y"])
        first = (latest - offset).isoformat()
        for zoom in zooms:
            zoom["startValue"] = first
            zoom["endValue"] = latest.isoformat()
    except (KeyError, IndexError, TypeError, ValueError, OverflowError):
        logging.exception("Invalid cached ECharts viewport for %s", element_key)
        return None, False
    # A session's last-good option can predate an application update: upgrade
    # its X-axis labels on recovery, without changing underlying observations.
    x_axis = recovered.get("xAxis")
    if isinstance(x_axis, dict):
        x_axis.setdefault("axisLabel", {}).update({
            "formatter": {
                "year": "{yyyy}-01", "month": "{yyyy}-{MM}",
                "day": "{MM}-{dd}", "hour": "{MM}-{dd} {HH}:{mm}",
            }
        })
    return recovered, True


def _viewport_scaled_plotly_fallback(base_fig, date_range):
    """Fallback stays interactive and updates both X/Y, not full-history Y."""
    copy = go.Figure(base_fig)
    if callable(apply_client_time_controls):
        return apply_client_time_controls(copy, default_range=date_range)
    if callable(apply_server_time_window):
        return apply_server_time_window(copy, date_range)
    return apply_time_axis(copy, date_range)





def _show_data_quality_notes(fig):
    """Disclose known estimated/missing observations without new fetches."""
    meta = fig.layout.meta if isinstance(fig.layout.meta, dict) else {}
    for note in (meta or {}).get("data_quality_notes", []):
        st.caption("数据质量说明：" + str(note))


def _show_macro_plot_health(fig, option, element_key):
    """Show timestamps and missing/stale observations without new network I/O."""
    meta = fig.layout.meta if isinstance(fig.layout.meta, dict) else {}
    missing = list((meta or {}).get("missing_series") or [])
    if missing:
        st.warning("以下序列缺少观测数据：" + " · ".join(missing))
    _show_data_quality_notes(fig)

    checker = getattr(_echarts_axes, "option_observation_health", None)
    if not callable(checker):
        return
    try:
        report = checker(option, chart_key=element_key)
        dates = report.get("latest_by_name", {})
        if dates:
            st.caption("实际观测日：" + " · ".join(
                f"{name} {day}" for name, day in dates.items()
            ))
        if report.get("stale_names"):
            st.warning("部分数据未及时更新（使用最后有效观测，非实时）：" +
                       " · ".join(report["stale_names"]))
        if report.get("future_names"):
            st.warning("发现超前观测日期，请检查数据源：" +
                       " · ".join(report["future_names"]))
    except Exception:
        logging.exception("Unable to describe observation health for %s", element_key)


def _render_adaptive_macro_figure(base_fig, element_key, mode=None):
    """Use viewport-filtered ECharts for every macro chart, not only US 1-4.

    Plotly's native time selector changes X without recalculating Y after
    arbitrary drag/slider zoom. ECharts filters visible data client-side and
    rescales every independent Y axis when the X viewport changes.
    """
    # Uniform Streamlit buttons work for all 13 charts, regardless of
    # whether ECharts or Plotly is currently the available renderer.
    # Their parent fragments prevent an X/Y viewport change from rerunning
    # the entire dashboard and refetching unrelated market data.
    selected_range = st.segmented_control(
        "时间范围", options=RANGES, default=DEFAULT_CHART_RANGE,
        key=f"{element_key}_time_window", label_visibility="collapsed",
    ) or DEFAULT_CHART_RANGE
    renderer = getattr(st, "echarts_chart", None)
    if callable(renderer):
        option, reused = _recoverable_echarts_option(
            base_fig, element_key, selected_range, mode
        )
        if option is not None:
            try:
                renderer(
                    option,
                    height=465,
                    width="stretch",
                    key=f"{element_key}_adaptive_{mode or 'default'}_{selected_range}",
                    theme=None,
                )
                if reused:
                    st.caption("动态 Y 轴已保留上次有效数据；数据更新暂不可用。")
                _show_macro_plot_health(base_fig, option, element_key)
                return
            except Exception:
                logging.exception("Adaptive chart %s renderer failed", element_key)

    # Per-chart fail-open fallback, with independent viewport-aware Y buttons.
    st.warning("动态 Y 轴暂不可用，已切换可同时调整 X/Y 的兼容图表。")
    try:
        fallback = _viewport_scaled_plotly_fallback(base_fig, selected_range)
        # The unified selector above already handles relayout of X and Y.
        # Hide the second, renderer-specific row of time buttons.
        fallback.update_layout(updatemenus=[])
        st.plotly_chart(
            fallback,
            key=f"{element_key}_plotly_fallback_{mode or 'default'}_{selected_range}",
            use_container_width=True,
            config=PLOTLY_CONFIG,
        )
    except Exception:
        logging.exception("Plotly fallback for chart %s failed", element_key)
        st.error("该图表暂时无法显示，其余图表及页面可继续使用。")


def _render_standard_macro_chart(title, description, range_key, builder, sources, desc_index, prebuilt_fig=None):
    st.markdown(title, unsafe_allow_html=True)
    st.markdown(description, unsafe_allow_html=True)
    # Visible deployment fingerprint: distinguishes deployed code from an old instance.
    st.caption(f"图表版本 {CHART_BUILD} · X/Y 自适应缩放")
    base_fig = prebuilt_fig if prebuilt_fig is not None else builder("5Y")
    # All four standard US charts now share one client-side viewport engine.
    selected_range = st.segmented_control(
        "时间范围", options=["5Y", "1Y", "6M", "3M", "1M"],
        default=DEFAULT_CHART_RANGE, key=f"{range_key}_time_window",
        label_visibility="collapsed",
    ) or DEFAULT_CHART_RANGE
    # Native ECharts filters samples outside the active X window and sets
    # each Y axis to an independent nonzero-based visible-data extent.
    # All standard US macro charts (1–4), not just chart 1, must use the
    # same viewport-filtered engine. A Plotly fallback silently reintroduces
    # the fixed five-year zero-based axes, so never render it here.
    if not callable(getattr(st, "echarts_chart", None)):
        # Fail open: even a stale/missing optional chart adapter cannot prevent
        # the market overview, charts and news from loading.
        st.warning("ECharts 模块尚未同步，临时显示可缩放的 Plotly 图表。")
        fallback = _viewport_scaled_plotly_fallback(base_fig, selected_range)
        st.plotly_chart(
            fallback, key=f"{range_key}_plotly_fallback_{selected_range}",
            use_container_width=True, config=PLOTLY_CONFIG,
        )
        show_parameter_description(desc_index)
        add_sources(sources)
        st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)
        return
    native_option, reused = _recoverable_echarts_option(
        base_fig, range_key, selected_range
    )
    if native_option is None:
        st.warning("动态图表与缓存均不可用，已使用可同时调整 X/Y 的兼容图表。")
        fallback = _viewport_scaled_plotly_fallback(base_fig, selected_range)
        try:
            st.plotly_chart(
                fallback, key=f"{range_key}_plotly_recovery_{selected_range}",
                use_container_width=True, config=PLOTLY_CONFIG,
            )
        except Exception:
            logging.exception("Recovery chart failed for %s", range_key)
            st.error("该图表暂时无法显示，其余页面仍可使用。")
        show_parameter_description(desc_index)
        add_sources(sources)
        st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)
        return
    st.caption("动态Y轴：时间切换、底部滑块及框选时按可见样本自适应（左右轴分别计算）。")
    missing_series = list((base_fig.layout.meta or {}).get("missing_series", [])) if isinstance(base_fig.layout.meta, dict) else []
    if missing_series:
        st.warning("以下序列缺少观测数据：" + " · ".join(missing_series))
    if reused:
        st.caption("当前沿用上次正常加载的动态曲线，数据可能未更新；Y 轴缩放仍可使用。")
    # Extra diagnostics are optional: version skew must not break the charts.
    if st.query_params.get("debug_chart") == "1":
        bounds_helper = getattr(_echarts_axes, "expected_viewport_y_bounds", None)
        if callable(bounds_helper):
            bounds = bounds_helper(base_fig, selected_range)
            st.caption("服务端校验区间：" + (
                " · ".join(f"{axis}: {values[0]:.3f}～{values[1]:.3f}"
                         for axis, values in sorted(bounds.items()))
                if bounds else "无可用数据"
            ))
        else:
            st.caption("Y 轴诊断辅助函数未加载；图表显示不受影响。")
    health_helper = getattr(_echarts_axes, "summarize_series_dates", None)
    if callable(health_helper):
        health = health_helper(
            base_fig, maximum_age_days=15 if range_key == "us_liquidity_range" else 10,
        )
        if health.get("latest_by_name"):
            st.caption("数据观测日：" + " · ".join(
                f"{name} {obs}" for name, obs in health["latest_by_name"].items()
            ))
        if health.get("stale_names"):
            st.warning("以下序列可能尚未更新：" + "、".join(health["stale_names"]))
        if health.get("future_names"):
            st.warning("以下序列的观测日期超前，请检查源数据：" + "、".join(health["future_names"]))
    try:
        st.echarts_chart(
            native_option,
            height=465,
            width="stretch",
            key=f"{range_key}_echarts_{selected_range}",
            theme=None,
        )
    except Exception:
        logging.exception("ECharts renderer failed for %s", range_key)
        st.warning("图表渲染异常，已改用兼容显示。")
        fallback = _viewport_scaled_plotly_fallback(base_fig, selected_range)
        try:
            st.plotly_chart(
                fallback, key=f"{range_key}_renderer_recovery_{selected_range}",
                use_container_width=True, config=PLOTLY_CONFIG,
            )
        except Exception:
            logging.exception("Recovery chart failed for %s", range_key)
            st.error("该图表暂时无法显示，其余页面仍可使用。")
    _show_data_quality_notes(base_fig)
    show_parameter_description(desc_index)
    add_sources(sources)
    st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)
    return


@st.fragment(key="us_macro_chart_1")
def render_macro_chart_1(prebuilt_fig=None):
    _render_standard_macro_chart(
        '<div class="section-title">1. Fed Policy Rate & Money Market</div>',
        '<div class="section-description">IORB / ON RRP Rate / EFFR / SOFR</div>',
        "normal_corridor_range",
        build_fig1,
        [
            ("IORB (IORB)", "https://fred.stlouisfed.org/series/IORB"),
            ("ON RRP Rate (RRPONTSYAWARD)", "https://fred.stlouisfed.org/series/RRPONTSYAWARD"),
            ("EFFR (EFFR)", "https://fred.stlouisfed.org/series/EFFR"),
            ("SOFR (SOFR)", "https://fred.stlouisfed.org/series/SOFR"),
        ],
        0,
        prebuilt_fig=prebuilt_fig,
    )


@st.fragment(key="us_macro_chart_2")
def render_macro_chart_2(prebuilt_fig=None):
    _render_standard_macro_chart(
        '<div class="section-title">2. US Treasury Yield Structure · 5Y / 10Y</div>',
        '<div class="section-description">10Y Nominal / 10Y Real (R1) / 5Y Real TIPS (R1) / 10Y Breakeven (R1)</div>',
        "normal_yield10_range",
        build_fig2,
        [
            ("10Y Nominal (DGS10)", "https://fred.stlouisfed.org/series/DGS10"),
            ("10Y Real (DFII10)", "https://fred.stlouisfed.org/series/DFII10"),
            ("5Y Real TIPS (DFII5)", "https://fred.stlouisfed.org/series/DFII5"),
            ("10Y Breakeven (T10YIE)", "https://fred.stlouisfed.org/series/T10YIE"),
        ],
        1,
        prebuilt_fig=prebuilt_fig,
    )


@st.fragment(key="us_macro_chart_3")
def render_macro_chart_3(prebuilt_fig=None):
    _render_standard_macro_chart(
        '<div class="section-title">3. Treasury Yield & Curve Spread</div>',
        '<div class="section-description">3M / 2Y / 10Y / 10Y−2Y (R1) / 10Y−3M (R1)</div>',
        "normal_treasury_range",
        build_fig3,
        [
            ("3M Treasury (DGS3MO)", "https://fred.stlouisfed.org/series/DGS3MO"),
            ("2Y Treasury (DGS2)", "https://fred.stlouisfed.org/series/DGS2"),
            ("10Y Nominal (DGS10)", "https://fred.stlouisfed.org/series/DGS10"),
            ("10Y−2Y Spread (T10Y2Y)", "https://fred.stlouisfed.org/series/T10Y2Y"),
            ("10Y−3M Spread (T10Y3M)", "https://fred.stlouisfed.org/series/T10Y3M"),
        ],
        2,
        prebuilt_fig=prebuilt_fig,
    )


@st.fragment(key="us_macro_chart_4")
def render_macro_chart_4(prebuilt_fig=None):
    _render_standard_macro_chart(
        '<div class="section-title">4. US Liquidity</div>',
        '<div class="section-description">Net Liquidity (L) · Reserve Balances / TGA (R1) · ON RRP (R2)</div>',
        "normal_liquidity_range",
        build_fig4,
        [
            ("Fed Total Assets (WALCL)", "https://fred.stlouisfed.org/series/WALCL"),
            ("Reserve Balances (WRESBAL)", "https://fred.stlouisfed.org/series/WRESBAL"),
            ("TGA · Daily Treasury Statement", "https://fiscaldata.treasury.gov/datasets/daily-treasury-statement/operating-cash-balance"),
            ("TGA fallback (WTREGEN)", "https://fred.stlouisfed.org/series/WTREGEN"),
            ("ON RRP Balance (RRPONTSYD)", "https://fred.stlouisfed.org/series/RRPONTSYD"),
        ],
        3,
        prebuilt_fig=prebuilt_fig,
    )


HK_CHART_CONFIGS = [
    (
        '<div class="section-title">5. HK Money Supply & Market Pulse</div>',
        '<div class="section-description">M2 YoY / M2 MoM / Monetary Base YoY · Tencent / HKEX (R1) · HSTECH / HSI (R2)</div>',
        "hk_5_range",
        [
            ("HKMA Monetary Statistics", "https://apidocs.hkma.gov.hk/documentation/market-data-and-statistics/monthly-statistical-bulletin/financial/monetary-statistics/"),
            ("Hang Seng Indexes · HSTECH", "https://www.hsi.com.hk/eng/indexes/all-indexes/hstech"),
            ("Hang Seng Indexes · HSI", "https://www.hsi.com.hk/eng/indexes/all-indexes/hsi"),
            ("Yahoo Finance Market History", "https://finance.yahoo.com/"),
        ],
    ),
    (
        '<div class="section-title">6. Banking-system Liquidity</div>',
        '<div class="section-description">Aggregate Balance · Outstanding EFBN (R1) · EFBN Held by Licensed Banks (R1)</div>',
        "hk_6_range",
        [
            ("HKMA Monetary Base", "https://apidocs.hkma.gov.hk/documentation/market-data-and-statistics/monthly-statistical-bulletin/monetary-operation/monetary-base-endperiod/"),
            ("HKMA Daily Interbank Liquidity", "https://apidocs.hkma.gov.hk/documentation/market-data-and-statistics/daily-monetary-statistics/daily-figures-interbank-liquidity/"),
        ],
    ),
    (
        '<div class="section-title">7. HKD Funding</div>',
        '<div class="section-description">O/N HIBOR · 3M HIBOR · HKMA Base Rate · O/N−3M Spread (R1)</div>',
        "hk_7_range",
        [
            ("HKMA Open API", "https://apidocs.hkma.gov.hk/"),
            ("HKMA Base Rate", "https://apidocs.hkma.gov.hk/documentation/market-data-and-statistics/monthly-statistical-bulletin/monetary-operation/disc-win-liquid-adj-win-rates-endperiod/"),
        ],
    ),
    (
        '<div class="section-title">8. USD/HKD Convertibility Band & Market</div>',
        '<div class="section-description">USD/HKD · Strong-side 7.75 · Center 7.80 · Weak-side 7.85 · Tencent / HKEX (R1) · HSTECH / HSI (R2)</div>',
        "hk_8_range",
        [
            ("HKMA Linked Exchange Rate System", "https://www.hkma.gov.hk/eng/key-functions/money/linked-exchange-rate-system/"),
            ("Yahoo Finance Market History", "https://finance.yahoo.com/"),
            ("Hang Seng Indexes · HSTECH", "https://www.hsi.com.hk/eng/indexes/all-indexes/hstech"),
            ("Hang Seng Indexes · HSI", "https://www.hsi.com.hk/eng/indexes/all-indexes/hsi"),
        ],
    ),
]


def _render_hk_macro_chart(hk_index, prebuilt_fig=None, prebuilt_mode=None):
    title, description, range_key, sources = HK_CHART_CONFIGS[hk_index]
    st.markdown(title, unsafe_allow_html=True)
    st.markdown(description, unsafe_allow_html=True)
    market_mode = "Raw"
    if hk_index in (0, 3):
        market_mode = st.radio(
            "市场显示",
            ["Raw", "Rebased 100"],
            horizontal=True,
            index=0,
            key=f"{range_key}_market_mode",
            label_visibility="collapsed",
        )
    # The parent already loaded a figure for this exact market mode.
    # On fragment-only radio changes, rebuild ONLY this chart's mode; do
    # not cause a full dashboard rerun or display the old prebuilt mode.
    fig = (
        prebuilt_fig
        if prebuilt_fig is not None and prebuilt_mode == market_mode
        else _safe_hk_bundle(market_mode, _macro_snapshot_revision())[hk_index]
    )
    _render_adaptive_macro_figure(fig, range_key, market_mode)
    show_hk_parameter_description(hk_index)
    add_sources(sources)
    st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)


@st.fragment(key="hk_money_chart")
def render_macro_chart_5(prebuilt_fig=None, prebuilt_mode=None):
    _render_hk_macro_chart(0, prebuilt_fig=prebuilt_fig, prebuilt_mode=prebuilt_mode)


@st.fragment(key="macro_chart_6_viewport")
def render_macro_chart_6(prebuilt_fig=None):
    _render_hk_macro_chart(1, prebuilt_fig=prebuilt_fig)


@st.fragment(key="macro_chart_7_viewport")
def render_macro_chart_7(prebuilt_fig=None):
    _render_hk_macro_chart(2, prebuilt_fig=prebuilt_fig)


@st.fragment(key="hk_fx_chart")
def render_macro_chart_8(prebuilt_fig=None, prebuilt_mode=None):
    _render_hk_macro_chart(3, prebuilt_fig=prebuilt_fig, prebuilt_mode=prebuilt_mode)


@st.fragment(key="macro_chart_9_viewport")
def render_macro_chart_9(prebuilt_fig=None):
    st.markdown(
        '<div class="section-title">9. US Equity Risk & Volatility Structure</div>'
        '<div class="section-description">VIX · VIXEQ · S&P 500 (R1) · VIX3M−VIX (R2)</div>',
        unsafe_allow_html=True,
    )
    base_fig = prebuilt_fig if prebuilt_fig is not None else build_fig9("5Y")
    _render_adaptive_macro_figure(base_fig, "us_equity_risk")
    st.markdown(f'<div class="mini-description">{US_EQUITY_RISK_DESCRIPTION}</div>', unsafe_allow_html=True)
    add_sources([
        ("Cboe VIX", "https://www.cboe.com/tradable-products/vix/"),
        ("Cboe VIXEQ / Dispersion", "https://www.cboe.com/us/indices/dispersion/"),
        ("FRED VIX3M (VXVCLS)", "https://fred.stlouisfed.org/series/VXVCLS"),
        ("FRED S&P 500 (SP500)", "https://fred.stlouisfed.org/series/SP500"),
    ])
    st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)


@st.fragment(key="precious_metals_chart")
def render_macro_chart_10(prebuilt_fig=None, prebuilt_mode=None):
    st.markdown(
        '<div class="section-title">10. Precious Metals</div>'
        '<div class="section-description">Gold · Silver · Gold/Silver Ratio · Gold Volatility GVZ</div>',
        unsafe_allow_html=True,
    )
    market_mode = st.radio(
        "市场显示", ["Rebased 100", "Raw"], horizontal=True, index=0,
        key="precious_metals_mode", label_visibility="collapsed",
    )
    base_fig = (
        prebuilt_fig
        if prebuilt_fig is not None and prebuilt_mode == market_mode
        else _safe_macro_build(
            "Chart 10",
            lambda: _cached_macro_figure(10, market_mode, _macro_snapshot_revision(), CHART_BUILD),
        )
    )
    _render_adaptive_macro_figure(base_fig, "precious_metals", market_mode)
    st.markdown(f'<div class="mini-description">{PRECIOUS_METALS_DESCRIPTION}</div>', unsafe_allow_html=True)
    add_sources([
        ("Yahoo Finance · Gold Futures GC=F", "https://finance.yahoo.com/quote/GC=F/history/"),
        ("Yahoo Finance · Silver Futures SI=F", "https://finance.yahoo.com/quote/SI=F/history/"),
        ("FRED · Cboe Gold ETF Volatility Index (GVZCLS)", "https://fred.stlouisfed.org/series/GVZCLS"),
        ("Cboe · Gold Volatility", "https://www.cboe.com/tradable_products/vix/vix_historical_data/"),
    ])
    st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)


@st.fragment(key="crypto_chart")
def render_macro_chart_11(prebuilt_fig=None, prebuilt_mode=None):
    st.markdown(
        '<div class="section-title">11. Crypto Market</div>'
        '<div class="section-description">BTC · ETH · ETH/BTC · BTC 30D 实际波动率</div>',
        unsafe_allow_html=True,
    )
    market_mode = st.radio(
        "市场显示", ["Rebased 100", "Raw"], horizontal=True, index=0,
        key="crypto_market_mode", label_visibility="collapsed",
    )
    base_fig = (
        prebuilt_fig
        if prebuilt_fig is not None and prebuilt_mode == market_mode
        else _safe_macro_build(
            "Chart 11",
            lambda: _cached_macro_figure(11, market_mode, _macro_snapshot_revision(), CHART_BUILD),
        )
    )
    _render_adaptive_macro_figure(base_fig, "crypto_market", market_mode)
    st.markdown(f'<div class="mini-description">{CRYPTO_MARKET_DESCRIPTION}</div>', unsafe_allow_html=True)
    add_sources([
        ("Yahoo Finance · Bitcoin BTC-USD", "https://finance.yahoo.com/quote/BTC-USD/history/"),
        ("Yahoo Finance · Ethereum ETH-USD", "https://finance.yahoo.com/quote/ETH-USD/history/"),
    ])
    st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)


@st.fragment(key="macro_chart_12_viewport")
def render_macro_chart_12(prebuilt_fig=None):
    st.markdown(
        '<div class="section-title">12. Copper Flow & COMEX–LME Spread</div>'
        '<div class="section-description">COMEX inventory · LME inventory · LME 3M (R1) · COMEX HG converted (R1) · COMEX−LME 3M spread (R2)</div>',
        unsafe_allow_html=True,
    )
    base_fig = prebuilt_fig if prebuilt_fig is not None else build_fig12("5Y")
    _render_adaptive_macro_figure(base_fig, "copper_flow")
    st.markdown(
        '<div class="mini-description"><b>读取提示：</b>库存单位为千吨，铜价统一为 USD/t；价差＝COMEX−LME 3M。'
        '库存此增彼减且价差走阔可提示交割需求迁移；两者期限不同，价差仅用于压力监测。</div>',
        unsafe_allow_html=True,
    )
    add_sources([
        ("CME · COMEX Warehouse & Depository Stocks", "https://www.cmegroup.com/solutions/clearing/operations-and-deliveries/nymex-delivery-notices.html"),
        ("Yahoo Finance · COMEX Copper HG=F", "https://finance.yahoo.com/quote/HG=F/history/"),
        ("LME Copper", "https://www.lme.com/copper"),
        ("LME Warehouse & Stocks Reports", "https://www.lme.com/Market-data/Reports-and-data/Warehouse-and-stocks-reports"),
        ("Westmetall · LME Copper Daily Table", "https://www.westmetall.com/en/markdaten.php?action=table&field=LME_Cu_cash"),
        ("COCHILCO · Copper Inventories", "https://boletin.cochilco.cl/estadisticas/inventarios.asp"),
    ])
    st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)


@st.fragment(key="macro_chart_13_viewport")
def render_macro_chart_13(prebuilt_fig=None):
    st.markdown(
        '<div class="section-title">13. China & Japan Government Yield Curves</div>'
        '<div class="section-description">China 2Y / 10Y / 10Y−2Y · Japan 2Y / 10Y / 10Y−2Y · all in %</div>',
        unsafe_allow_html=True,
    )
    base_fig = prebuilt_fig if prebuilt_fig is not None else build_asia_rates_figure("5Y")
    _render_adaptive_macro_figure(base_fig, "asia_rates")
    st.markdown(
        '<div class="mini-description"><b>读取方法：</b>'
        '10Y−2Y 上升表示曲线变陡，下降表示趋平，负值表示倒挂。</div>',
        unsafe_allow_html=True,
    )
    add_sources([
        ("Eastmoney · China Treasury Yield History", "https://data.eastmoney.com/cjsj/zmgzsyl.html"),
        ("Japan MOF · JGB Interest Rates", "https://www.mof.go.jp/jgbs/reference/interest_rate/index.htm"),
    ])
    st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)


def _macro_error_figure(label):
    fig = go.Figure()
    fig.add_annotation(
        text=f"{label} 数据暂不可用",
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        showarrow=False,
        font=dict(size=13, color="#6b7280"),
    )
    fig.update_layout(
        height=420,
        template="plotly_white",
        margin=dict(l=40, r=40, t=60, b=40),
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
    )
    return fig


def _safe_macro_build(label, builder):
    try:
        return builder()
    except Exception:
        return _macro_error_figure(label)


def _macro_snapshot_revision():
    """Invalidate constructed figures when a repository snapshot is replaced."""
    folder = Path(__file__).resolve().parent / "data_snapshots"
    revision = []
    for path in sorted(folder.glob("*.json")):
        try:
            stat = path.stat()
        except OSError:
            continue
        revision.append((path.name, stat.st_mtime_ns, stat.st_size))
    return tuple(revision)


@st.cache_data(ttl=300, max_entries=32, show_spinner=False)
def _cached_macro_figure(chart_number, market_mode, snapshot_revision, build_revision):
    """Reuse successful construction; callers receive isolated figure copies."""
    builders = {
        1: build_fig1, 2: build_fig2, 3: build_fig3, 4: build_fig4,
        9: build_fig9, 10: build_fig10, 11: build_fig11,
        12: build_fig12, 13: build_asia_rates_figure,
    }
    builder = builders[chart_number]
    if chart_number in (10, 11):
        return builder("5Y", market_mode)
    return builder("5Y")


@st.cache_data(ttl=300, max_entries=8, show_spinner=False)
def _cached_hk_bundle(market_mode, snapshot_revision, build_revision):
    figures = build_fig5("5Y", market_mode=market_mode)
    if not isinstance(figures, (list, tuple)) or len(figures) < 4:
        raise ValueError("HK figure bundle incomplete")
    return list(figures)


def _safe_hk_bundle(market_mode, snapshot_revision):
    try:
        return _cached_hk_bundle(market_mode, snapshot_revision, CHART_BUILD)
    except Exception:
        return [_macro_error_figure(f"Chart {number}") for number in range(5, 9)]


def _build_macro_figures_parallel():
    """Build all macro figures concurrently, then render them together.

    Only data access and Plotly figure construction run in worker threads.
    Streamlit widgets/rendering stay on the main script thread.
    """
    hk5_mode = st.session_state.get("hk_5_range_market_mode", "Raw")
    hk8_mode = st.session_state.get("hk_8_range_market_mode", "Raw")
    metals_mode = st.session_state.get("precious_metals_mode", "Rebased 100")
    crypto_mode = st.session_state.get("crypto_market_mode", "Rebased 100")
    snapshot_revision = _macro_snapshot_revision()

    def cached_chart(number, mode=""):
        return _safe_macro_build(f"Chart {number}", lambda: _cached_macro_figure(number, mode, snapshot_revision, CHART_BUILD))

    jobs = {
        1: lambda: cached_chart(1),
        2: lambda: cached_chart(2),
        3: lambda: cached_chart(3),
        4: lambda: cached_chart(4),
        "hk5": lambda: _safe_hk_bundle(hk5_mode, snapshot_revision),
        9: lambda: cached_chart(9),
        10: lambda: cached_chart(10, metals_mode),
        11: lambda: cached_chart(11, crypto_mode),
        12: lambda: cached_chart(12),
        13: lambda: cached_chart(13),
    }
    if hk8_mode != hk5_mode:
        jobs["hk8"] = lambda: _safe_hk_bundle(hk8_mode, snapshot_revision)

    # Six workers keeps cold-start I/O parallel without hammering public data
    # endpoints with one thread per chart.
    with ThreadPoolExecutor(max_workers=6, thread_name_prefix="macro-chart") as executor:
        futures = {key: executor.submit(job) for key, job in jobs.items()}
        results = {key: future.result() for key, future in futures.items()}

    hk5_bundle = results["hk5"]
    hk8_bundle = results.get("hk8", hk5_bundle)
    return {
        1: results[1],
        2: results[2],
        3: results[3],
        4: results[4],
        5: hk5_bundle[0],
        6: hk5_bundle[1],
        7: hk5_bundle[2],
        8: hk8_bundle[3],
        9: results[9],
        10: results[10],
        11: results[11],
        12: results[12],
        13: results[13],
    }


st.markdown(
    '<div id="macro-charts" class="section-anchor"></div>'
    '<div class="section-kicker">MACRO CHARTS</div>'
    '<div class="section-title">US monetary policy, Treasury yields and inflation expectations</div>',
    unsafe_allow_html=True,
)

with st.spinner("正在加载图表…"):
    macro_figures = _build_macro_figures_parallel()

render_macro_chart_1(macro_figures[1])
render_macro_chart_2(macro_figures[2])
render_macro_chart_3(macro_figures[3])
render_macro_chart_4(macro_figures[4])

st.markdown('<div class="section-kicker">HONG KONG LIQUIDITY</div>', unsafe_allow_html=True)
render_macro_chart_5(macro_figures[5], prebuilt_mode=st.session_state.get("hk_5_range_market_mode", "Raw"))
render_macro_chart_6(macro_figures[6])
render_macro_chart_7(macro_figures[7])
render_macro_chart_8(macro_figures[8], prebuilt_mode=st.session_state.get("hk_8_range_market_mode", "Raw"))

st.markdown('<div class="section-kicker">US EQUITY RISK</div>', unsafe_allow_html=True)
render_macro_chart_9(macro_figures[9])

st.markdown('<div class="section-kicker">PRECIOUS METALS</div>', unsafe_allow_html=True)
render_macro_chart_10(macro_figures[10], prebuilt_mode=st.session_state.get("precious_metals_mode", "Rebased 100"))

st.markdown('<div class="section-kicker">CRYPTO MARKET</div>', unsafe_allow_html=True)
render_macro_chart_11(macro_figures[11], prebuilt_mode=st.session_state.get("crypto_market_mode", "Rebased 100"))

st.markdown('<div class="section-kicker">INDUSTRIAL METALS · COPPER</div>', unsafe_allow_html=True)
render_macro_chart_12(macro_figures[12])

st.markdown('<div class="section-kicker">ASIA RATES</div>', unsafe_allow_html=True)
render_macro_chart_13(macro_figures[13])

st.markdown('<div id="news" class="section-anchor"></div><div class="section-kicker">NEWS</div>', unsafe_allow_html=True)
st.markdown('<div class="section-title">📰 7×24 重点财经快讯</div>', unsafe_allow_html=True)
st.markdown(f'<div class="source-text"><a href="{EASTMONEY_FOCUS_URL}" target="_blank" rel="noopener noreferrer">东方财富 · 红字精选</a></div>', unsafe_allow_html=True)


def render_news_panel():
    news_component = r"""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
  * { box-sizing: border-box; }
  body { margin: 0; font-family: "Noto Sans TC","Noto Sans CJK TC","Microsoft JhengHei","PingFang TC","Segoe UI",sans-serif; color:#374151; background:#fff; }
  .toolbar { display:flex; align-items:center; justify-content:space-between; gap:12px; margin:0 0 8px; }
  .status { color:#6b7280; font-size:12px; line-height:1.4; }
  button { border:1px solid #d1d5db; background:#fff; color:#374151; border-radius:8px; padding:8px 16px; cursor:pointer; font-size:13px; }
  button:hover { background:#f9fafb; }
  button:disabled { opacity:.55; cursor:default; }
  .news-box { border:1px solid #e5e7eb; border-radius:8px; padding:6px 10px; background:#fff; height:650px; overflow-y:auto; overflow-x:hidden; }
  .news-item { display:flex; align-items:flex-start; padding:8px 3px; border-bottom:1px solid #eee; line-height:1.5; font-size:14px; }
  .news-item:last-child { border-bottom:none; }
  .news-index { flex:0 0 38px; width:38px; color:#9ca3af; font-size:12px; padding-top:2px; }
  .news-time { flex:0 0 88px; width:88px; color:#6b7280; font-size:12px; white-space:nowrap; padding-top:2px; margin-right:8px; }
  .news-content { flex:1; min-width:0; overflow-wrap:anywhere; word-break:break-word; }
  .news-content a { color:#374151; text-decoration:none; display:block; }
  .news-title { color:#1f2937; font-weight:700; margin-bottom:3px; }
  .empty { padding:18px 10px; color:#9ca3af; font-size:13px; }
  .error { color:#b45309; }
</style>
</head>
<body>
<div class="toolbar">
  <div id="status" class="status">正在加载快讯…</div>
  <button id="refresh">🔄 刷新快讯</button>
</div>
<div id="news" class="news-box"><div class="empty">正在取得新闻…</div></div>
<script>
(function () {
  var endpoint = "app/static/news.json";
  var newsEl = document.getElementById("news");
  var statusEl = document.getElementById("status");
  var button = document.getElementById("refresh");
  var lastVersion = "";
  var inFlight = false;
  var pollTimer;

  function makeNode(tag, cls, text) {
    var el = document.createElement(tag);
    if (cls) el.className = cls;
    if (text !== undefined) el.textContent = text;
    return el;
  }

  function render(payload) {
    var items = Array.isArray(payload.items) ? payload.items : [];
    var updated = payload.updated_at ? String(payload.updated_at).replace("T", " ") : "";
    statusEl.className = payload.error ? "status error" : "status";
    statusEl.textContent =
      items.length + " 条" +
      (updated ? " · 更新于 " + updated : "") +
      (payload.error ? " · 更新失败，显示缓存" : "");

    if (!items.length) {
      newsEl.replaceChildren(makeNode("div", "empty", payload.error ? "快讯暂不可用，请稍后刷新。" : "暂无快讯。"));
      return;
    }

    var frag = document.createDocumentFragment();
    items.forEach(function (item, index) {
      var row = makeNode("div", "news-item");
      row.appendChild(makeNode("span", "news-index", String(index + 1) + "."));
      row.appendChild(makeNode("span", "news-time", item.time || ""));

      var content = makeNode("div", "news-content");
      var link = makeNode("a");
      var rawUrl = typeof item.url === "string" ? item.url : "";
      link.href = /^https?:\/\//i.test(rawUrl) ? rawUrl : "https://kuaixun.eastmoney.com/";
      link.target = "_blank";
      link.rel = "noopener noreferrer";

      var title = String(item.title || "");
      var body = String(item.content || "");
      if (title && body && title !== body) {
        link.appendChild(makeNode("div", "news-title", title));
        link.appendChild(makeNode("div", "", body));
      } else {
        link.appendChild(makeNode("div", title ? "news-title" : "", body || title));
      }

      content.appendChild(link);
      row.appendChild(content);
      frag.appendChild(row);
    });
    newsEl.replaceChildren(frag);
  }

  async function refresh(force) {
    force = Boolean(force);
    if (inFlight) return;
    inFlight = true;
    clearTimeout(pollTimer);
    var controller = new AbortController();
    var timeout = setTimeout(function () { controller.abort(); }, 8000);
    if (force) {
      button.disabled = true;
      button.textContent = "刷新中…";
    }
    try {
      var response = await fetch(endpoint + "?t=" + Date.now(), {cache:"no-store", signal:controller.signal});
      if (!response.ok) throw new Error("HTTP " + response.status);
      var payload = await response.json();
      var version = JSON.stringify(payload);
      if (force || version !== lastVersion) {
        render(payload);
        lastVersion = version;
      }
    } catch (err) {
      lastVersion = "";
      statusEl.className = "status error";
      statusEl.textContent = "快讯刷新失败，请稍后重试。";
    } finally {
      clearTimeout(timeout);
      inFlight = false;
      if (force) {
        button.disabled = false;
        button.textContent = "🔄 刷新快讯";
      }
      if (!document.hidden) pollTimer = setTimeout(function () { refresh(false); }, 5000);
    }
  }

  button.addEventListener("click", function () { refresh(true); });
  document.addEventListener("visibilitychange", function () {
    clearTimeout(pollTimer);
    if (!document.hidden) refresh(false);
  });
  refresh(true);
})();
</script>
</body>
</html>
"""
    st.iframe(news_component, width="stretch", height=710)



render_news_panel()
