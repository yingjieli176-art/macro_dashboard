import html
from collections.abc import Mapping
from copy import deepcopy
import json
import logging
import math
import os
import time
import uuid
from macro_platform.request_runtime import http_get, submit_jobs, completed_jobs, PeriodicWorker, observed_cache, IncompleteObservedBundle
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.parse import quote
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from macro_platform.hk_liquidity import build_hk_liquidity_figures, build_hk_core_snapshot_figures
# The renderer is an optional module during rolling Streamlit Cloud deployments.
# Never import individual newly added helpers at startup: mixed revisions of
# app.py and macro_platform/echarts_axes.py must not crash the entire app.
try:
    import macro_platform.echarts_axes as _echarts_axes
except (ImportError, AttributeError) as _echarts_module_error:
    _echarts_axes = None
else:
    _echarts_module_error = None
try:
    from macro_platform import linked_charts as _linked_charts
except ImportError:
    _linked_charts = None
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
import macro_platform.us_equity_risk as _us_equity_risk
try:
    import macro_platform.equity_drawdown as _equity_drawdown
except ImportError:
    _equity_drawdown = None
try:
    import macro_platform.china_equity as _china_equity
except ImportError:
    _china_equity = None

# Keep the page available during a mixed-revision Streamlit Cloud rollout.
load_correlation_snapshot = getattr(
    _us_equity_risk, "load_correlation_snapshot",
    lambda symbol: pd.DataFrame(columns=["observation_date", symbol]),
)
from macro_platform.copper import build_copper_flow_spread_figure
from macro_platform.asia_rates import build_china_rates_figure, build_japan_rates_figure
from macro_platform.yen_index import load_yen_market_index
from macro_platform.security_search import search_securities
from macro_platform.freshness_overview import render_freshness_overview
from macro_platform.watchlist_state import WATCHLIST_KEYS, decode_watchlists, encode_watchlists, merge_default_watchlists, watchlist_needs_default_migration
from macro_platform.market_history import completed_daily_closes
# Keep startup-compatible with older data.py during Streamlit Cloud rolling
# deployments: optional/newer market getters must never crash the whole page.
import data as _market_data_module
from data import (
    fetch_eastmoney_news, get_dgs3mo, get_dgs2, get_dgs10, get_dfii10,
    get_sofr, get_iorb, get_effr, get_rrp_rate, get_walcl, get_wresbal,
    get_wtre_gen, get_tga_daily, get_rrp_daily, _fred_series,
)

get_dfii5 = getattr(_market_data_module, "get_dfii5", None)
if not callable(get_dfii5):
    # The DFII5 series itself predates the feature. Its original FRED loader
    # is present in the earlier data module and maintains the same data source.
    # This is not an estimated/synthetic yield.
    def get_dfii5():
        return _fred_series("DFII5")
    logging.warning("Older data.py lacks get_dfii5; using direct FRED DFII5 loader.")


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
MACRO_DISPLAY_ORDER = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, "us_drawdown", "cn_drawdown", 14, 15, 11, 13, 12)
MACRO_DISPLAY_NUMBER = {key: index for index, key in enumerate(MACRO_DISPLAY_ORDER, 1)}
CHART_BUILD = "2026-10-28-equity-price-guides-r72"
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


@st.cache_resource(show_spinner=False, on_release=lambda worker: worker.close())
def _start_news_background_updater():
    return PeriodicWorker(_write_news_snapshot, NEWS_BACKGROUND_INTERVAL_SECONDS,
                          "eastmoney-news-updater")


_start_news_background_updater()

st.markdown("""
<style>
.block-container { padding-top: 0.70rem; padding-bottom: 2rem; max-width: 1760px; }
html, body, [class*="css"] { font-family: "Noto Sans TC", "Noto Sans CJK TC", "Microsoft JhengHei", "PingFang TC", "Segoe UI", sans-serif; }
.dashboard-title { font-size: 1.9rem; font-weight: 700; letter-spacing: -0.02em; margin-bottom: 0.1rem; }
.section-title { font-size: 1.18rem; font-weight: 680; letter-spacing: -0.012em; margin-top: 0.52rem; margin-bottom: 0.04rem; min-height: 26px; display: flex; align-items: center; color:#1f2937; }
.section-description { color: #7b8493; font-size: 0.80rem; margin-bottom: 0.16rem; min-height: 17px; display: flex; align-items: center; }
.mini-description { color: #4b5563; font-size: 0.78rem; line-height: 1.6; margin: 4px 0 8px; overflow-wrap: anywhere; }
.parameter-note { margin: 3px 0; }
.parameter-note b { color: #374151; font-weight: 600; }
.parameter-context { color: #6b7280; font-size: 0.74rem; margin-top: 5px; }
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
            response = http_get(
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
        response = http_get(
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
        response = http_get(
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
            response = http_get(
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
            response = http_get(
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
        response = http_get(
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
            return "休市", regular_ts
        return _us_clock_state(), regular_ts

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
        jobs = {index: (lambda getter=getter: getter(symbol)) for index, getter in enumerate(direct_getters)}
        futures = submit_jobs(jobs, name="quote-provider", workers=8, budget=4,
                              revision=(symbol, _quote_refresh_key()))
        direct_rows = {}
        for index, future in completed_jobs(futures, budget=4):
            try:
                direct_rows[index] = future.result()
            except Exception:
                continue
        # Deterministic provider precedence for identical quote timestamps.
        for index in sorted(direct_rows):
            row = direct_rows[index]
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


def _apply_watchlist_quote_rows(symbols, rows, requested, manual=False, progress=None):
    previous = st.session_state.get("_watchlist_quotes_snapshot", {})
    snapshot = {symbol: previous[symbol] for symbol in symbols if symbol in previous}
    received = changed = retained = missing = 0
    for completed, symbol in enumerate(requested, 1):
        row = rows.get(symbol, _empty_quote())
        fetched = row.get("price") is not None
        row = _remember_quote(symbol, row)
        snapshot[symbol] = row
        if fetched:
            received += 1
            old = previous.get(symbol)
            if isinstance(old, dict) and _active_quote_values(old, _symbol_market(symbol)) != _active_quote_values(row, _symbol_market(symbol)):
                changed += 1
        elif row.get("price") is not None:
            retained += 1
        else:
            missing += 1
        if progress is not None:
            progress.caption(f"刷新中… {completed}/{len(requested)}")
    st.session_state["_watchlist_quotes_snapshot"] = snapshot
    st.session_state["_watchlist_last_poll"] = time.time()
    if manual:
        st.session_state["_watchlist_refresh_result"] = {
            "completed_at": datetime.now(DASHBOARD_TZ).strftime("%m-%d %H:%M:%S"),
            "total": len(requested), "received": received, "changed": changed,
            "retained": retained, "missing": missing,
        }


def _load_watchlist_quotes(symbols, manual=False, progress=None):
    previous = st.session_state.get("_watchlist_quotes_snapshot", {})
    requested = symbols if manual else [symbol for symbol in symbols if symbol not in previous]
    rows = _fetch_quote_rows(requested, progress=progress) if requested else {}
    _apply_watchlist_quote_rows(symbols, rows, requested, manual)


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

def _fetch_quote_rows(symbols, refresh_key=None, progress=None):
    jobs = {symbol: (lambda symbol=symbol: _fetch_quote(symbol) if refresh_key is None
                     else _get_cached_quote(symbol, refresh_key)) for symbol in symbols}
    futures = submit_jobs(jobs, name="market-quote", workers=6,
                          revision=refresh_key, budget=6)
    rows = {symbol: _empty_quote() for symbol in symbols}
    completed = 0
    for symbol, future in completed_jobs(futures, budget=6):
        try:
            row = future.result()
            if isinstance(row, dict):
                rows[symbol] = row
        except Exception:
            logging.warning("Quote source unavailable: %s", symbol)
        completed += 1
        if progress is not None:
            progress.caption(f"刷新中… {completed}/{len(rows)}")
    return rows


MARKET_SYMBOLS = {
    "nasdaq": "^IXIC", "sp500": "^GSPC", "dow": "^DJI",
    "hsi": "^HSI", "hstech": "HSTECH.HK", "sh": "000001.SS",
    "sz": "399001.SZ", "chinext": "399006.SZ",
}


def _load_market_quotes(refresh_key):
    rows = _fetch_quote_rows(MARKET_SYMBOLS.values(), refresh_key)
    return {key: _remember_quote(symbol, rows[symbol]) for key, symbol in MARKET_SYMBOLS.items()}


def render_market_groups(defer_initial=False):
    now = time.time(); snapshot = st.session_state.get("_market_quotes_snapshot"); snapshot_time = st.session_state.get("_market_quotes_snapshot_time", 0)
    if not defer_initial and (not isinstance(snapshot, dict) or now - snapshot_time >= 60):
        refresh_key = (_quote_refresh_key(), st.session_state.get("_market_refresh_key", 0))
        snapshot = _load_market_quotes(refresh_key)
        st.session_state["_market_quotes_snapshot"] = snapshot; st.session_state["_market_quotes_snapshot_time"] = now
    q = snapshot or {key: _empty_quote() for key in MARKET_SYMBOLS}

    def overview_item(name, row, market):
        price, change = _active_quote_values(row, market)
        return _market_item_html(name, price, change, _quote_meta(row, market))

    groups = [
        ("🇺🇸 美股", [overview_item("纳斯达克", q["nasdaq"], "US"), overview_item("标普500", q["sp500"], "US"), overview_item("道琼斯", q["dow"], "US")], "three"),
        ("🇭🇰 港股", [overview_item("恒生指数", q["hsi"], "HK"), overview_item("恒生科技", q["hstech"], "HK")], "two"),
        ("🇨🇳 A股", [overview_item("上证指数", q["sh"], "CN"), overview_item("深证成指", q["sz"], "CN"), overview_item("创业板指数", q.get("chinext", {}), "CN")], "three"),
    ]
    cards = []
    for title, items, grid_class in groups: cards.append(f'<div class="market-group"><div class="market-group-title">{title}</div><div class="market-group-row {grid_class}">' + "".join(items) + '</div></div>')
    st.markdown('<div class="market-groups">' + "".join(cards) + '</div>', unsafe_allow_html=True)

st.markdown('<div id="market-overview" class="section-anchor"></div><div class="section-kicker">MARKET OVERVIEW</div>', unsafe_allow_html=True)
st.markdown('<div class="section-title">市场概览</div><div class="section-description">美股、港股与 A 股主要指数</div>', unsafe_allow_html=True)

@st.fragment(run_every=60, key="market_overview")
def render_market_overview(defer_initial=False):
    if st.session_state.get("_market_overview_started"):
        defer_initial = False
    st.session_state["_market_overview_started"] = True
    _, refresh_col = st.columns([8.6, 1.4], vertical_alignment="center")
    with refresh_col:
        if st.button("↻ 刷新行情", key="refresh_market_overview", use_container_width=True):
            st.session_state["_market_quotes_snapshot_time"] = 0
            st.session_state["_market_refresh_key"] = st.session_state.get("_market_refresh_key", 0) + 1
            defer_initial = False
    render_market_groups(defer_initial)

market_overview_slot = st.container()

@st.cache_data(ttl=20, show_spinner=False)
def _search_market(market, query):
    return search_securities(market, query)

def _render_quote_block(item):
    row = _get_watchlist_quote(item["symbol"])
    price = row.get("price")
    change = row.get("change_pct")
    symbol_code = str(item["symbol"]).upper()
    is_cn_fund = symbol_code.endswith((".SS", ".SZ")) and symbol_code.startswith(("15", "16", "18", "50", "51", "52", "56", "58"))
    price_text = "--" if price is None else f"{price:,.{3 if is_cn_fund else 2}f}"
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
    st.session_state["_watchlist_added_pending"] = True; st.session_state[f"{key}_confirmed"] = confirmed; st.session_state[key] = ""; st.session_state[f"{key}_open"] = False; st.session_state.pop(f"{key}_select", None); st.session_state.pop(f"{key}_confirm", None); _save_watchlists()

def _delete_confirmed(key, symbol):
    confirmed = st.session_state.get(f"{key}_confirmed", []); confirmed = [confirmed] if isinstance(confirmed, dict) else (confirmed if isinstance(confirmed, list) else [])
    st.session_state[f"{key}_confirmed"] = [item for item in confirmed if not (isinstance(item, dict) and item.get("symbol") == symbol)]; st.session_state[f"{key}_open"] = False; _save_watchlists()

def _open_search(key): st.session_state[f"{key}_open"] = True

def _run_search(key, market):
    query = str(st.session_state.get(key, "")).strip()
    st.session_state.pop(f"{key}_result_select", None)
    if not query:
        st.session_state.pop(f"{key}_results", None)
        st.session_state.pop(f"{key}_search_unavailable", None)
        return
    result = _search_market(market, query)
    st.session_state[f"{key}_results"] = [{**item, "market": market} for item in result["items"]]
    st.session_state[f"{key}_search_unavailable"] = result["unavailable"]

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

@st.fragment(run_every=60, key="watchlists")
def render_watchlists(defer_initial=False):
    pending = st.session_state.get("_watchlist_refresh_pending", False)
    info_col, refresh_col = st.columns([8.6, 1.4], vertical_alignment="center")
    with info_col:
        st.markdown('<div class="watch-toolbar">自选股票与指数 · 可添加或删除 · 每 60 秒检查报价</div>', unsafe_allow_html=True)
    with refresh_col:
        refresh_slot = st.empty()
        if pending:
            refresh_slot.button("刷新中…", key="refresh_watchlist_quotes_busy", disabled=True)
        else:
            refresh_slot.button("↻ 刷新", key="refresh_watchlist_quotes", on_click=_request_watchlist_refresh, help="只刷新下方自选模块报价，不刷新市场概览")

    status_slot = st.empty()
    symbols = _watchlist_symbols()
    snapshot = st.session_state.get("_watchlist_quotes_snapshot", {})
    now = time.time()
    last_poll = st.session_state.setdefault("_watchlist_last_poll", now)
    if not pending and now - last_poll >= 60:
        # Refresh only this fragment's symbols; preserve user controls and
        # manual refresh results, even when a quote provider is unavailable.
        _apply_watchlist_quote_rows(symbols, _fetch_quote_rows(symbols), symbols)
        snapshot = st.session_state.get("_watchlist_quotes_snapshot", {})
    if pending or ((not defer_initial or st.session_state.pop("_watchlist_added_pending", False)) and any(symbol not in snapshot for symbol in symbols)):
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
                    st.text_input("搜索", placeholder=placeholder, key=key, label_visibility="collapsed", on_change=_run_search, args=(key, market))
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
                elif st.session_state.get(f"{key}_search_unavailable"):
                    st.caption("搜索服务暂时不可用，请稍后重试，或直接输入完整代码。")
                elif st.session_state.get(key, "").strip() and f"{key}_results" in st.session_state:
                    st.caption("没有找到匹配标的，请检查名称或代码。")

watchlists_slot = st.container()

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

def get_fred_series(series_id): return _fred_series(series_id)


# === HK LIQUIDITY CHART 5 ===


def build_fig5(date_range):
    return build_hk_liquidity_figures(date_range, compact_mode=False)


def build_fig1(date_range):
    sources = {}
    for getter, column in ((get_iorb, "IORB"), (get_rrp_rate, "RRPONTSYAWARD"),
                           (get_effr, "EFFR"), (get_sofr, "SOFR")):
        try:
            sources[column] = getter()
        except Exception:
            sources[column] = pd.DataFrame(columns=["observation_date", column])
    dates = filter_range(pd.concat(list(sources.values()), ignore_index=True), date_range)["observation_date"]
    fig = go.Figure()
    # IORB includes weekends; the other rates use business-day calendars.
    # Keep each source's actual rows, including any explicit missing reading.
    for column, name, width in [("IORB", "IORB", 2.6), ("RRPONTSYAWARD", "ON RRP", 2.6), ("EFFR", "EFFR", 2.6), ("SOFR", "SOFR", 2.2)]:
        frame = sources[column]
        add_line(fig, frame.loc[frame["observation_date"].isin(dates)], column, name, width)
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

    # Mixed-frequency proxy: only use RECENT observations, never carry
    # an obsolete TGA fixing (e.g. 2022-04-15) into 2026 calculations.
    # Observed source traces remain at their original dates. The proxy
    # is unavailable whenever any constituent is older than its tolerance.
    calc = None
    for column in ("WALCL", "TGA_DAILY", "RRPONTSYD"):
        frame = raw_series.get(column)
        if frame is None:
            continue
        calc = frame.copy() if calc is None else calc.merge(frame, on="observation_date", how="outer")
    calc = pd.DataFrame(columns=["observation_date"]) if calc is None else calc.sort_values("observation_date")
    component_cols = [c for c in ("WALCL", "TGA_DAILY", "RRPONTSYD") if c in calc.columns]
    if component_cols:
        freshness_days = {"WALCL": 10, "TGA_DAILY": 8, "RRPONTSYD": 7}
        for column in component_cols:
            last_observed = calc["observation_date"].where(calc[column].notna()).ffill()
            age = calc["observation_date"] - last_observed
            calc[column] = calc[column].ffill().where(
                age <= pd.Timedelta(days=freshness_days[column])
            )
    if all(c in calc.columns for c in ("WALCL", "TGA_DAILY", "RRPONTSYD")):
        calc["NetLiquidity"] = calc["WALCL"] - calc["TGA_DAILY"] - calc["RRPONTSYD"] / 1000.0
    calc = filter_range(calc, date_range)
    if ("NetLiquidity" not in calc or
            pd.to_numeric(calc["NetLiquidity"], errors="coerce").notna().sum() == 0):
        _mark_missing_series(fig, "Net Liquidity (components too old or unavailable)")
    else:
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
    """US equity risk with implied correlation and same-date vol spreads."""
    frames = []
    sources = {}
    for series_id in ("VIXCLS", "SP500"):
        try:
            frame = get_fred_series(series_id).copy()
            frame["observation_date"] = pd.to_datetime(frame["observation_date"], errors="coerce")
            frame[series_id] = pd.to_numeric(frame[series_id], errors="coerce")
            frame = frame.dropna(subset=["observation_date"])[["observation_date", series_id]]
            if frame[series_id].notna().any():
                frames.append(frame)
                sources[series_id] = frame
        except Exception:
            continue

    try:
        vixeq = load_vixeq_snapshot()
        if not vixeq.empty:
            frames.append(vixeq)
            sources["VIXEQ"] = vixeq
    except Exception:
        pass

    for symbol in ("COR1M", "COR3M"):
        try:
            correlation = load_correlation_snapshot(symbol)
            if not correlation.empty:
                frames.append(correlation)
                sources[symbol] = correlation
        except Exception:
            continue

    if not frames:
        fig = go.Figure()
        for name in ("VIX", "VIXEQ", "S&P 500 (R1)",
                     "VIXEQ−VIX (R2)", "VIXEQ/VIX (R3)", "COR1M (R4)", "COR3M (R4)"):
            _mark_missing_series(fig, name)
        return apply_chart_style(fig, chart_height(320, 440), date_range)

    data = frames[0]
    for frame in frames[1:]:
        data = data.merge(frame, on="observation_date", how="outer")
    data = data.sort_values("observation_date")
    if "VIXEQ" in data.columns and "VIXCLS" in data.columns:
        # Only divide valid observations from the same date; never carry a
        # stale leg forward or turn a zero/invalid denominator into a ratio.
        vix = data["VIXCLS"].where(data["VIXCLS"].gt(0) & data["VIXCLS"].lt(float("inf")))
        vixeq = data["VIXEQ"].where(data["VIXEQ"].ge(0) & data["VIXEQ"].lt(float("inf")))
        data["VIXEQ/VIX"] = (vixeq / vix).replace([float("inf"), -float("inf")], float("nan"))
        data["VIXEQ-VIX"] = vixeq - vix
    data = filter_range(data, date_range)

    fig = go.Figure()
    for column, name, width, dash, axis, unit in (
        ("VIXCLS", "VIX", 2.7, None, None, ""),
        ("VIXEQ", "VIXEQ", 2.4, "dash", None, ""),
        ("SP500", "S&P 500 (R1)", 2.4, None, "y2", " pts"),
    ):
        source = sources.get(column, pd.DataFrame(columns=["observation_date"]))
        add_line(fig, data.loc[data["observation_date"].isin(source["observation_date"])],
                 column, name, width, dash, axis, unit)
    ratio_dates = [date for column in ("VIXEQ", "VIXCLS") if column in sources
                   for date in sources[column]["observation_date"]]
    add_line(fig, data.loc[data["observation_date"].isin(ratio_dates)],
             "VIXEQ-VIX", "VIXEQ−VIX (R2)", 2.2, "dash", "y3", unit=" pts")
    add_line(fig, data.loc[data["observation_date"].isin(ratio_dates)],
             "VIXEQ/VIX", "VIXEQ/VIX (R3)", 2.2, "dot", "y4", unit="x")
    for symbol, dash in (("COR1M", None), ("COR3M", "dot")):
        source = sources.get(symbol, pd.DataFrame(columns=["observation_date"]))
        add_line(fig, data.loc[data["observation_date"].isin(source["observation_date"])],
                 symbol, f"{symbol} (R4)", 2.0, dash, "y5", unit=" pts")

    # Fixed contrasting colors remain readable where these two lines overlap.
    risk_colors = {
        "VIX": "#5070dd", "VIXEQ": "#15803d", "S&P 500 (R1)": "#505372",
        "VIXEQ−VIX (R2)": "#0ca8df",
        "VIXEQ/VIX (R3)": "#92400e", "COR1M (R4)": "#fb628b", "COR3M (R4)": "#785db0",
    }
    for name, color in risk_colors.items():
        fig.update_traces(line_color=color, selector=dict(name=name))

    fig.update_layout(
        yaxis2=dict(overlaying="y", side="right", anchor="free", position=0.78),
        yaxis3=dict(overlaying="y", side="right", anchor="free", position=0.85),
        yaxis4=dict(overlaying="y", side="right", anchor="free", position=0.92),
        yaxis5=dict(overlaying="y", side="right", anchor="free", position=0.99),
    )
    fig = apply_chart_style(fig, chart_height(320, 440), date_range)
    fig.update_layout(
        margin=dict(l=62, r=180, t=100, b=36, pad=2),
        legend=dict(y=1.095),
        xaxis=dict(domain=[0.0, 0.76]),
        yaxis=dict(
            title="VIX / VIXEQ",
            showgrid=True, gridcolor="#e5e7eb", griddash="dot",
            zeroline=False, fixedrange=True,
        ),
        yaxis2=dict(
            title="",
            overlaying="y", side="right", anchor="free", position=0.78,
            showgrid=False, zeroline=False, fixedrange=True, tickfont=dict(size=9), ticks="outside", ticklen=3,
        ),
        yaxis3=dict(
            title="",
            overlaying="y", side="right", anchor="free", position=0.85,
            showgrid=False, zeroline=True, zerolinecolor="#94a3b8",
            zerolinewidth=1, fixedrange=True, tickfont=dict(size=9), ticks="outside", ticklen=3,
        ),
        yaxis4=dict(
            title="R3 · VIXEQ/VIX (倍)",
            overlaying="y", side="right", anchor="free", position=0.92,
            showgrid=False, zeroline=False, fixedrange=True, tickformat=".2f",
            tickfont=dict(size=9), ticks="outside", ticklen=3,
        ),
        yaxis5=dict(
            title="R4 · COR (pts)",
            overlaying="y", side="right", anchor="free", position=0.99,
            showgrid=False, zeroline=False, fixedrange=True, tickformat=".1f",
            tickfont=dict(size=9), ticks="outside", ticklen=3,
        ),
    )
    return fig


def build_fig10(date_range):
    """One/three-month index volatility and their observed same-date spread."""
    sources = {}
    for column in ("VIXCLS", "VXVCLS"):
        try:
            frame = get_fred_series(column).copy()
            frame["observation_date"] = pd.to_datetime(frame["observation_date"], errors="coerce")
            values = pd.to_numeric(frame[column], errors="coerce")
            frame[column] = values.where(values.ge(0) & values.lt(float("inf")))
            sources[column] = frame.dropna(subset=["observation_date"])[["observation_date", column]]
        except Exception:
            sources[column] = pd.DataFrame(columns=["observation_date", column])
    data = sources["VIXCLS"].merge(sources["VXVCLS"], on="observation_date", how="outer").sort_values("observation_date")
    # A missing or unpublished leg must leave a gap, including explicit nulls.
    data["VIX3M-VIX"] = data["VXVCLS"] - data["VIXCLS"]
    data = filter_range(data, date_range)
    fig = go.Figure()
    for column, name in (("VIXCLS", "VIX"), ("VXVCLS", "VIX3M")):
        add_line(fig, data.loc[data["observation_date"].isin(sources[column]["observation_date"])],
                 column, name, 2.6, unit=" pts")
    add_line(fig, data, "VIX3M-VIX", "VIX3M−VIX (R1)", 2.3, "dash", "y2", " pts")
    for name, color in (("VIX", "#5070dd"), ("VIX3M", "#785db0"), ("VIX3M−VIX (R1)", "#ff994d")):
        fig.update_traces(line_color=color, selector=dict(name=name))
    fig.update_layout(
        yaxis_title="VIX / VIX3M · pts",
        yaxis2=dict(title="R1 · VIX3M−VIX · pts", overlaying="y", side="right",
                    anchor="free", position=0.99, showgrid=False, zeroline=True,
                    zerolinecolor="#94a3b8", fixedrange=True),
    )
    return apply_chart_style(fig, chart_height(310, 420), date_range)


@observed_cache()
def get_yahoo_daily_history(symbol):
    """Fetch five years of completed daily closes from Yahoo chart API."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol, safe='')}"
    response = http_get(
        url,
        params={"range": "5y", "interval": "1d", "includePrePost": "false", "events": "div,splits"},
        headers={"User-Agent": "Mozilla/5.0 (compatible; MacroDashboard/1.0)"},
        timeout=(3.0, 8.0),
    )
    response.raise_for_status()
    result = ((response.json() or {}).get("chart") or {}).get("result") or []
    if not result:
        return pd.DataFrame(columns=["observation_date", "close"])
    return completed_daily_closes(result[0])


def _load_yahoo_histories(symbols):
    jobs = {symbol: (lambda symbol=symbol: get_yahoo_daily_history(symbol)) for symbol in symbols}
    futures = submit_jobs(jobs, name="market-history", workers=2, budget=8,
                          revision=_quote_refresh_key())
    results = {symbol: pd.DataFrame(columns=["observation_date", "close"]) for symbol in symbols}
    for symbol, future in completed_jobs(futures, budget=8):
        try:
            results[symbol] = future.result()
        except Exception:
            logging.warning("Market history unavailable: %s", symbol)
    return results


def build_fig11(date_range):
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

    for column, name, width, dash, axis, unit in (
        ("Gold", "Gold", 2.8, None, None, " USD/oz"),
        ("Silver", "Silver (R1)", 2.5, None, "y2", " USD/oz"),
        ("GoldSilverRatio", "Gold/Silver Ratio (R2)", 2.2, "dash", "y3", "x"),
        ("GVZCLS", "Gold Volatility · GVZ (R3)", 2.2, "dot", "y4", ""),
    ):
        source_dates = [date for frame in frames if column in frame or (
                            column == "GoldSilverRatio" and ("Gold" in frame or "Silver" in frame))
                        for date in frame["observation_date"]]
        add_line(fig, data.loc[data["observation_date"].isin(source_dates)],
                 column, name, width, dash, axis, unit)
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


def build_fig12(date_range):
    """Crypto market: BTC, ETH, ETH/BTC and 30-day BTC realized volatility."""
    frames = []
    histories = _load_yahoo_histories(("BTC-USD", "ETH-USD"))
    for symbol, column in (("BTC-USD", "BTC"), ("ETH-USD", "ETH")):
        try:
            frame = histories[symbol].rename(columns={"close": column})
            if not frame.empty:
                if column == "BTC":
                    # ETH-only rows must not change BTC returns or the number
                    # of BTC observations in a thirty-observation window.
                    btc_returns = pd.to_numeric(frame["BTC"], errors="coerce").pct_change(fill_method=None)
                    frame["BTC_VOL_30D"] = btc_returns.rolling(30, min_periods=20).std() * (365.0 ** 0.5) * 100.0
                    frames.append(frame[["observation_date", "BTC", "BTC_VOL_30D"]])
                    continue
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
    data = filter_range(data, date_range)
    fig = go.Figure()


    for column, name, width, dash, axis, unit in (
        ("BTC", "BTC · USD", 2.9, None, None, " USD"),
        ("ETH", "ETH · USD · R1", 2.6, None, "y2", " USD"),
        ("ETHBTC", "ETH/BTC 强弱 · R2", 2.2, "dash", "y3", ""),
        ("BTC_VOL_30D", "BTC 30D 实际波动率 · R3", 2.2, "dot", "y4", "%"),
    ):
        source_dates = [date for frame in frames if column in frame or column == "ETHBTC"
                        for date in frame["observation_date"]]
        add_line(fig, data.loc[data["observation_date"].isin(source_dates)],
                 column, name, width, dash, axis, unit)
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


def build_fig13(date_range):
    return build_copper_flow_spread_figure(date_range)


def build_fig14(date_range):
    try:
        real = get_dfii5()
    except Exception:
        real = pd.DataFrame(columns=["observation_date", "DFII5"])
    return build_china_rates_figure(date_range, us_real_yield=real)


def build_fig15(date_range):
    try:
        nikkei = _load_yahoo_histories(("^N225",))["^N225"]
    except Exception:
        nikkei = pd.DataFrame(columns=["observation_date", "close"])
    try:
        yen = load_yen_market_index()
    except Exception:
        yen = pd.DataFrame(columns=["observation_date", "usd_jpy_close"])
    return build_japan_rates_figure(date_range, nikkei=nikkei, yen_index=yen)


CRYPTO_MARKET_DESCRIPTION = (
    '<div class="parameter-note"><b>BTC · USD：</b>比特币美元日线价格，代表比特币的市场价格表现；单位为美元。</div><div class="parameter-note"><b>ETH · USD · R1：</b>以太币美元日线价格，代表以太币的市场价格表现；单位为美元。</div><div class="parameter-note"><b>ETH/BTC 强弱 · R2：</b>同日以太币价格除以比特币价格，代表两者相对强弱；上升表示ETH相对BTC走强，不等于资金净流入。</div><div class="parameter-note"><b>BTC 30D 实际波动率 · R3：</b>比特币过去30日日收益率波动的年化估计，代表已经发生的价格波动程度；单位为%，与期权隐含的未来波动率不同。</div><div class="parameter-context">口径说明：30D实际波动率按日收益率估计并以365天年化；不足完整窗口时，至少使用20个有效样本。</div>'
)


PARAM_DESCRIPTIONS = [
    '<div class="parameter-note"><b>IORB：</b>准备金余额利率，代表美联储支付给合资格银行的准备金利息，是美元短期利率的重要政策锚；单位为年化%。</div><div class="parameter-note"><b>ON RRP Rate：</b>隔夜逆回购工具利率，代表合资格机构把资金隔夜放入美联储该工具可获得的年化利率，为货币市场利率提供支撑。</div><div class="parameter-note"><b>EFFR：</b>有效联邦基金利率，代表银行等机构之间无抵押隔夜美元交易的实际融资价格；单位为年化%。</div><div class="parameter-note"><b>SOFR：</b>有担保隔夜融资利率，代表以美国国债作抵押借入隔夜美元的市场成本；单位为年化%，相对政策锚上升可提示回购融资压力。</div>',
    '<div class="parameter-note"><b>10Y Nominal：</b>美国10年期名义国债收益率，代表美元长期无风险名义利率基准，综合反映实际利率、通胀补偿等定价；单位为年化%。</div><div class="parameter-note"><b>10Y Real (R1)：</b>美国10年期TIPS实际收益率，代表通胀保值国债的实际利率定价，上升表示实际贴现率抬高；单位为年化%。</div><div class="parameter-note"><b>5Y Real · TIPS (R1)：</b>美国5年期TIPS实际收益率，代表中期实际利率水平，可与10年期比较期限差异；单位为年化%。</div><div class="parameter-note"><b>10Y Breakeven (R1)：</b>10年期盈亏平衡通胀率，等于同期限名义收益率减实际收益率，代表未来十年的平均通胀补偿，含风险和流动性溢价；并非当期CPI。</div><div class="parameter-context">口径说明：R1为独立右轴；收益率及通胀补偿均以年化%显示。</div>',
    '<div class="parameter-note"><b>3M：</b>美国3个月期国债收益率，代表短期美元国债的年化收益水平，对当前政策利率及近期政策预期较敏感。</div><div class="parameter-note"><b>2Y：</b>美国2年期国债收益率，代表未来两年利率路径的市场定价之一，同时包含期限溢价；不是两年期通胀率。</div><div class="parameter-note"><b>10Y：</b>美国10年期国债收益率，代表长期美元利率基准，反映长期实际利率、通胀补偿等因素；单位为年化%。</div><div class="parameter-note"><b>10Y−2Y (R1)：</b>10年减2年国债收益率之差，代表中长端收益率曲线斜率；负值为倒挂，上升为曲线变陡；单位为百分点。</div><div class="parameter-note"><b>10Y−3M (R1)：</b>10年减3个月国债收益率之差，代表长端与政策敏感短端之间的利差；负值为倒挂，不是衰退发生时间的直接预测。</div><div class="parameter-context">口径说明：国债收益率为年化%；两条期限利差为百分点。</div>',
    '<div class="parameter-note"><b>Net Liquidity：</b>美元净流动性代理＝美联储总资产−TGA−ON RRP余额，辅助观察央行资产负债表的流动性变化；单位为万亿美元，不等于流入股市的资金。</div><div class="parameter-note"><b>Reserve Balances (R1)：</b>银行准备金余额，代表存款机构在美联储持有的准备金存量；单位为万亿美元，使用周频观测。</div><div class="parameter-note"><b>TGA (R1)：</b>美国财政部在美联储的账户余额，代表财政现金存量；在其他因素不变时，余额增加通常会抽走银行准备金；单位为万亿美元。</div><div class="parameter-note"><b>ON RRP (R2)：</b>美联储隔夜逆回购余额，代表合资格机构使用该工具存放的隔夜资金规模；单位为十亿美元，与第1图的ON RRP利率不同。</div><div class="parameter-context">口径说明：该代理不包含所有美元资金流动。TGA优先使用日频，不可用时回退到周频；各系列保留实际观测日。</div>',
    '<div class="parameter-note"><b>M2 YoY：</b>港元广义货币M2同比增速，代表现金及相关存款规模相对上年同期的增长情况；单位为%，不等于股市资金净流入。</div><div class="parameter-note"><b>M2 MoM：</b>港元广义货币M2环比增速，代表货币存量相对上个月的边际变化；单位为%，会受到季节性等因素影响。</div><div class="parameter-note"><b>Monetary Base YoY：</b>香港货币基础同比增速，代表负债证明书、政府流通纸币硬币、总结余及外汇基金票据债券合计规模的变化。</div><div class="parameter-note"><b>Tencent Price (R1)：</b>腾讯控股股价，代表该股票的市场定价及表现；单位为港元，价格变化本身不等于资金净流入量。</div><div class="parameter-note"><b>HKEX Price (R1)：</b>香港交易所股价，代表交易所公司的股票市场表现；单位为港元，不是港股市场成交额。</div><div class="parameter-note"><b>HSTECH Index (R2)：</b>恒生科技指数，代表其科技主题成分股的综合表现；单位为指数点。</div><div class="parameter-note"><b>HSI Index (R2)：</b>恒生指数，代表香港主要上市公司构成的指数表现；单位为指数点。</div><div class="parameter-context">口径说明：月度货币数据有公布时滞；股票和指数使用各自实际观测日。</div>',
]


def show_parameter_description(index): st.markdown(f'<div class="mini-description">{PARAM_DESCRIPTIONS[index]}</div>', unsafe_allow_html=True)

HK_PARAMETER_DESCRIPTIONS = [
    '<div class="parameter-note"><b>M2 YoY：</b>港元广义货币M2同比增速，代表现金及相关存款规模相对上年同期的增长情况；单位为%，不等于股市资金净流入。</div><div class="parameter-note"><b>M2 MoM：</b>港元广义货币M2环比增速，代表货币存量相对上个月的边际变化；单位为%，会受到季节性等因素影响。</div><div class="parameter-note"><b>Monetary Base YoY：</b>香港货币基础同比增速，代表负债证明书、政府流通纸币硬币、总结余及外汇基金票据债券合计规模的变化。</div><div class="parameter-note"><b>Tencent Price (R1)：</b>腾讯控股股价，代表该股票的市场定价及表现；单位为港元，价格变化本身不等于资金净流入量。</div><div class="parameter-note"><b>HKEX Price (R1)：</b>香港交易所股价，代表交易所公司的股票市场表现；单位为港元，不是港股市场成交额。</div><div class="parameter-note"><b>HSTECH Index (R2)：</b>恒生科技指数，代表其科技主题成分股的综合表现；单位为指数点。</div><div class="parameter-note"><b>HSI Index (R2)：</b>恒生指数，代表香港主要上市公司构成的指数表现；单位为指数点。</div><div class="parameter-context">口径说明：月度货币数据有公布时滞；股票和指数使用各自实际观测日。</div>',
    '<div class="parameter-note"><b>Closing Aggregate Balance：</b>银行体系收市总结余，代表银行在金管局结算账户里的港元余额合计，观察银行间结算资金供应；单位为十亿港元，54.125即541.25亿港元。</div><div class="parameter-note"><b>Outstanding EFBN (R1)：</b>未偿还外汇基金票据及债券，代表该类港元证券的存量；本图按官方市值口径、以十亿港元显示，不是现金余额。</div><div class="parameter-note"><b>EFBN Held by Licensed Banks (R1)：</b>持牌银行持有的外汇基金票据及债券，代表银行持有的这一类证券资产规模，可配合总结余观察流动资产构成；单位为十亿港元。</div><div class="parameter-context">口径说明：总结余是结算资金存量，不等于客户存款或股市资金流量；变化需结合外汇交收、票据及贴现窗记录判断。各点以实际观测日为准。</div>',
    '<div class="parameter-note"><b>O/N HIBOR：</b>隔夜香港银行同业拆息，代表银行借用一天港元的年化融资成本；上升可反映短端资金需求增加或供给收紧，不直接等于资金外流。</div><div class="parameter-note"><b>3M HIBOR：</b>3个月期香港银行同业拆息，代表锁定三个月港元融资的年化成本，可观察较持续的融资压力；单位为%。</div><div class="parameter-note"><b>HKMA Base Rate：</b>金管局基本利率，代表贴现窗融资的基准利率，反映政策及流动性工具的定价；不是商业银行客户实际贷款利率。</div><div class="parameter-note"><b>O/N−3M Spread (R1)：</b>隔夜减3个月HIBOR之差，代表即时融资与较长期融资的价格差；转正可提示短端需求集中，不能单独确认资金危机；单位为百分点。</div><div class="parameter-context">口径说明：HIBOR为银行公会定盘；长期历史以官方月末值补充，单位均为年化%。缺失日期留空。</div>',
    '<div class="parameter-note"><b>USD/HKD：</b>美元兑港元汇率，代表1美元可兑换多少港元；数值上升为港元走弱，下降为港元走强。本图左轴反向，曲线向上表示港元走强。</div><div class="parameter-note"><b>Tencent Price (R1)：</b>腾讯控股股价，代表该股票的港元价格表现，用于对照汇率与股票走势。</div><div class="parameter-note"><b>HKEX Price (R1)：</b>香港交易所股价，代表交易所公司的港元价格表现，不能直接推算资金流向。</div><div class="parameter-note"><b>HSTECH Index (R2)：</b>恒生科技指数，代表科技主题成分股的综合表现；单位为指数点。</div><div class="parameter-note"><b>HSI Index (R2)：</b>恒生指数，代表香港主要上市公司的综合表现；单位为指数点。</div><div class="parameter-context">口径说明：7.75为强方兑换保证、7.80为区间中点、7.85为弱方兑换保证；红区7.84–7.85提示接近弱方，不代表已发生金管局兑换保证交易。</div>',
]


def show_hk_parameter_description(index):
    st.markdown(f'<div class="mini-description">{HK_PARAMETER_DESCRIPTIONS[index]}</div>', unsafe_allow_html=True)


US_EQUITY_RISK_DESCRIPTION = (
    '<div class="parameter-note"><b>VIX：</b>标普500指数未来30个日历天（约1M）的年化隐含波动率指标，代表指数期权对未来波动幅度的定价，不代表涨跌方向。</div><div class="parameter-note"><b>VIXEQ：</b>标普500成分股篮子的市值加权30天隐含波动率指标，代表个股层面的预期波动水平。</div><div class="parameter-note"><b>S&amp;P 500 (R1)：</b>标普500指数，代表美国大盘股的综合价格表现；单位为指数点。</div><div class="parameter-note"><b>VIXEQ−VIX (R2)：</b>同日个股篮子与指数隐含波动率之差，代表两种波动定价的差距，可辅助观察个股分化；单位为波动率点。</div><div class="parameter-note"><b>VIXEQ/VIX (R3)：</b>同日个股篮子与指数隐含波动率之比，代表个股预期波动相对指数的倍数差异；不是资金杠杆倍数。</div><div class="parameter-note"><b>COR1M (R4)：</b>1个月期隐含相关性指数，代表期权市场定价的成分股未来共同波动程度；上升表示预期相关性增强、分散化收益减弱。</div><div class="parameter-note"><b>COR3M (R4)：</b>3个月期隐含相关性指数，代表较长观察期内成分股的预期共同波动程度；与COR1M对照可观察相关性期限结构。</div><div class="parameter-context">口径说明：差值和比值只使用同日有效观测；COR为指数刻度。VIXEQ和COR早期数据包含官方回溯序列。</div>'
)


PRECIOUS_METALS_DESCRIPTION = (
    '<div class="parameter-note"><b>Gold：</b>COMEX黄金期货连续合约日线价格，代表该期货市场的黄金定价；单位为美元/金衡盎司，与现货报价口径不同。</div><div class="parameter-note"><b>Silver (R1)：</b>COMEX白银期货连续合约日线价格，代表该期货市场的白银定价；单位为美元/金衡盎司。</div><div class="parameter-note"><b>Gold/Silver Ratio (R2)：</b>同日黄金价格除以白银价格，代表一盎司黄金相当于多少盎司白银；上升表示黄金相对白银走强。</div><div class="parameter-note"><b>Gold Volatility · GVZ (R3)：</b>黄金ETF波动率指数，代表GLD期权隐含的约未来30天年化波动水平，衡量预期波动幅度，不直接预测金价方向。</div><div class="parameter-context">口径说明：连续期货价格可能受换月影响；金银比仅使用同日有效价格。</div>'
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
        result = apply_client_time_controls(copy, default_range=date_range)
    elif callable(apply_server_time_window):
        result = apply_server_time_window(copy, date_range)
    else:
        result = apply_time_axis(copy, date_range)
    # Align Plotly's degraded-mode time labels with the ECharts calendar:
    # dates for 1M, year-month for medium and long windows.
    result.update_xaxes(
        tickformat="%m-%d" if date_range == "1M" else "%Y-%m",
        hoverformat="%Y-%m-%d", nticks=7,
    )
    return result


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
        if report.get("future_names"):
            st.warning("发现超前观测日期，请检查数据源：" +
                       " · ".join(report["future_names"]))
    except Exception:
        logging.exception("Unable to describe observation health for %s", element_key)


def _figure_has_real_observations(fig):
    """Only allow a viewport renderer when there are finite source samples."""
    for trace in getattr(fig, "data", ()):
        if getattr(trace, "visible", True) in (False, "legendonly"):
            continue
        values = getattr(trace, "y", None)
        if values is None:
            continue
        for value in values:
            try:
                if math.isfinite(float(value)):
                    return True
            except (TypeError, ValueError, OverflowError):
                pass
    return False


def _chart_has_recoverable_data(fig, element_key, mode=None):
    if _figure_has_real_observations(fig):
        return True
    key = f"_echarts_last_good_{element_key}_{mode or 'default'}"
    state = getattr(st, "session_state", None)
    return bool(state is not None and
                isinstance(state.get(key), dict) and state[key].get("series"))


def _explain_missing_chart_data(fig, element_key):
    meta = fig.layout.meta if isinstance(fig.layout.meta, dict) else {}
    st.error("该图表目前没有可验证的有效观测数据，无法进行 X/Y 动态缩放。"
             "程序不会通过插值或虚构数值补齐行情。")
    if (meta or {}).get("build_error_type"):
        st.caption("图表构建错误类别：" + str(meta["build_error_type"])
                   + "；完整异常见服务器日志。")
    st.caption("数据或原生图表恢复后会重新启用动态 X/Y。"
               "FRED 官方历史缓存可用于网络故障时展示真实但可能过期的数据。")
    logging.warning("No valid chart samples for %s", element_key)


def _get_echarts_renderer():
    linked = getattr(globals().get("_linked_charts"), "render_echarts_chart", None)
    return linked if callable(linked) else getattr(st, "echarts_chart", None)


def _try_minimal_adaptive_chart(base_fig, element_key, selected_range, mode=None):
    """Retry a *native* adaptive renderer before degrading to Plotly.

    The rich option can be incompatible with a partially upgraded Cloud
    runtime. The minimal spec omits optional toolbox/formatting/shading but
    retains dataZoom(filter) and independent per-axis Y autoscaling.
    """
    builder = getattr(_echarts_axes, "build_safe_echarts_option", None)
    renderer = _get_echarts_renderer()
    if not callable(builder) or not callable(renderer):
        return False
    try:
        option = builder(base_fig, selected_range)
        if not isinstance(option, dict) or not option.get("series"):
            return False
        renderer(
            option,
            height=465,
            width="stretch",
            key=f"{element_key}_native_safe_{mode or 'default'}_{selected_range}",
            theme=None,
        )
        st.caption("已启用轻量动态 X/Y 视图：时间切换及滑块仍按可见样本自适应。")
        _show_macro_plot_health(base_fig, option, element_key)
        return True
    except Exception:
        logging.exception("Minimal native ECharts also failed for %s (%s)",
                          element_key, selected_range)
        return False


def _render_adaptive_macro_figure(base_fig, element_key, mode=None, standard=False):
    """Use viewport-filtered ECharts for every macro chart, not only US 1-4.

    Plotly's native time selector changes X without recalculating Y after
    arbitrary drag/slider zoom. ECharts filters visible data client-side and
    rescales every independent Y axis when the X viewport changes.
    """
    # Uniform Streamlit buttons work for all 15 charts, regardless of
    # whether ECharts or Plotly is currently the available renderer.
    # Their parent fragments prevent an X/Y viewport change from rerunning
    # the entire dashboard and refetching unrelated market data.
    selected_range = st.segmented_control(
        "时间范围", options=RANGES, default=DEFAULT_CHART_RANGE,
        key=f"{element_key}_time_window", label_visibility="collapsed",
    ) or DEFAULT_CHART_RANGE
    if not _chart_has_recoverable_data(base_fig, element_key, mode):
        _explain_missing_chart_data(base_fig, element_key)
        return
    renderer = _get_echarts_renderer()
    failure_kind = "原生图表组件缺失" if not callable(renderer) else "数据转换无有效图表"
    if callable(renderer):
        option, reused = _recoverable_echarts_option(
            base_fig, element_key, selected_range, mode
        )
        if option is not None:
            if standard:
                _show_standard_chart_health(base_fig, element_key, selected_range, reused)
            try:
                renderer(
                    option,
                    height=465,
                    width="stretch",
                    key=(f"{element_key}_echarts_{selected_range}" if standard else
                         f"{element_key}_adaptive_{mode or 'default'}_{selected_range}"),
                    theme=None,
                )
                if not standard:
                    if reused:
                        st.caption("动态 Y 轴已保留上次有效数据；数据更新暂不可用。")
                    _show_macro_plot_health(base_fig, option, element_key)
                return
            except Exception as exc:
                failure_kind = type(exc).__name__
                logging.exception("Adaptive chart %s renderer failed", element_key)

    # Retain genuine browser-side X/Y scaling even when a rich ECharts option
    # fails due to unsupported decorations or rolling Cloud version skew.
    if _try_minimal_adaptive_chart(base_fig, element_key, selected_range, mode):
        return

    # Only fall back to Plotly if BOTH ECharts rendering strategies fail.
    st.warning(f"原生动态图表暂不可用（{failure_kind}），显示可切换时间范围的兼容图表。")
    try:
        fallback = _viewport_scaled_plotly_fallback(base_fig, selected_range)
        # The unified selector above already handles relayout of X and Y.
        # Hide the second, renderer-specific row of time buttons.
        # Plotly update_layout(updatemenus=[]) merges with existing menus,
        # so set the tuple directly to actually remove duplicate buttons.
        fallback.layout.updatemenus = ()
        st.plotly_chart(
            fallback,
            key=f"{element_key}_plotly_fallback_{mode or 'default'}_{selected_range}",
            use_container_width=True,
            config=PLOTLY_CONFIG,
        )
    except Exception:
        logging.exception("Plotly fallback for chart %s failed", element_key)
        st.error("该图表暂时无法显示，其余图表及页面可继续使用。")


def _show_standard_chart_health(base_fig, element_key, selected_range, reused):
    st.caption("动态Y轴：切换时间范围或拖动底部滑块时，按可见样本自适应（左右轴分别计算）。")
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
            base_fig, maximum_age_days=15 if element_key == "us_liquidity_range" else 10,
        )
        if health.get("latest_by_name"):
            st.caption("数据观测日：" + " · ".join(
                f"{name} {obs}" for name, obs in health["latest_by_name"].items()
            ))
        if health.get("stale_names"):
            st.warning("以下序列可能尚未更新：" + "、".join(health["stale_names"]))
        if health.get("future_names"):
            st.warning("以下序列的观测日期超前，请检查源数据：" + "、".join(health["future_names"]))


def _render_standard_macro_chart(title, description, range_key, builder, sources, desc_index, prebuilt_fig=None):
    st.markdown(title, unsafe_allow_html=True)
    st.markdown(description, unsafe_allow_html=True)
    st.caption(f"图表版本 {CHART_BUILD} · X/Y 自适应缩放")
    base_fig = prebuilt_fig if prebuilt_fig is not None else builder("5Y")
    _render_adaptive_macro_figure(base_fig, range_key, standard=True)
    _show_data_quality_notes(base_fig)
    show_parameter_description(desc_index)
    add_sources(sources)
    st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)


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
            ("HKAB 当日 HIBOR 定盘", "https://www.hkab.org.hk/en/rates/hibor"),
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


def _render_hk_macro_chart(hk_index, prebuilt_fig=None):
    title, description, range_key, sources = HK_CHART_CONFIGS[hk_index]
    st.markdown(title, unsafe_allow_html=True)
    st.markdown(description, unsafe_allow_html=True)
    fig = prebuilt_fig if prebuilt_fig is not None else _safe_hk_bundle(_macro_snapshot_revision())[hk_index]
    _render_adaptive_macro_figure(fig, range_key)
    show_hk_parameter_description(hk_index)
    add_sources(sources)
    st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)


@st.fragment(key="hk_money_chart")
def render_macro_chart_5(prebuilt_fig=None):
    _render_hk_macro_chart(0, prebuilt_fig=prebuilt_fig)


@st.fragment(key="macro_chart_6_viewport")
def render_macro_chart_6(prebuilt_fig=None):
    _render_hk_macro_chart(1, prebuilt_fig=prebuilt_fig)


@st.fragment(key="macro_chart_7_viewport")
def render_macro_chart_7(prebuilt_fig=None):
    _render_hk_macro_chart(2, prebuilt_fig=prebuilt_fig)


@st.fragment(key="hk_fx_chart")
def render_macro_chart_8(prebuilt_fig=None):
    _render_hk_macro_chart(3, prebuilt_fig=prebuilt_fig)


def _build_equity_drawdown():
    if _equity_drawdown is None:
        fig = go.Figure()
        _mark_missing_series(fig, "SPX / RSP")
    else:
        histories = {}
        for symbol in _equity_drawdown.SERIES:
            try:
                histories[symbol] = _equity_drawdown.load_equity_history(symbol)
            except Exception:
                logging.exception("Equity drawdown history unavailable: %s", symbol)
        price_builder = getattr(_equity_drawdown, "build_price_figure", None)
        if price_builder is None:
            fig = go.Figure()
            _mark_missing_series(fig, "SPX / RSP")
        else:
            fig = price_builder(histories, split_axes=True)
    return apply_chart_style(fig, chart_height(310, 420), "5Y")


@st.fragment(key="equity_drawdown_viewport")
def _render_equity_drawdown():
    st.markdown('<div class="section-title">11. SPX / RSP · 价格走势与区间高点</div>', unsafe_allow_html=True)
    st.caption("实线为实际收盘走势；点线“高”标记当前坐标时间内的最高收盘价和日期，虚线“现”为最新收盘价。切换时间或拖动滑块会自动重算区间高点。SPX左轴（点），RSP右轴（美元）。")
    figure = _build_equity_drawdown()
    _render_adaptive_macro_figure(figure, "us_equity_drawdown", standard=True)
    summaries = (figure.layout.meta or {}).get("price_summary", [])
    for row in summaries:
        st.caption(f'{row["symbol"]} 最新收盘：{row["close"]:,.2f}（{row["date"]}）')
    st.caption("SPX为自由流通市值加权价格指数，单位为点；RSP为跟踪标普500等权指数的ETF，单位为美元。RSP价格已处理拆股，不含股息再投资，并存在费用及跟踪误差；两者使用独立坐标轴。数据为已完成交易日收盘，非实时行情。")
    add_sources([
        ("SPX 日线价格", "https://finance.yahoo.com/quote/%5EGSPC/history/"),
        ("RSP 日线价格", "https://finance.yahoo.com/quote/RSP/history/"),
        ("Invesco RSP", "https://www.invesco.com/us/financial-products/etfs/product-detail?productId=RSP"),
    ])
    st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)


def _build_china_drawdown():
    if _china_equity is None:
        figure = go.Figure()
        _mark_missing_series(figure, "沪深300 / 中证1000 / 中证2000")
    else:
        try:
            figure = _china_equity.build_china_price_figure()
        except Exception:
            logging.exception("China index drawdown history unavailable")
            figure = go.Figure()
            _mark_missing_series(figure, "沪深300 / 中证1000 / 中证2000")
    return apply_chart_style(figure, chart_height(310, 420), "5Y")


@st.fragment(key="china_equity_drawdown_viewport")
def _render_china_drawdown():
    st.markdown('<div class="section-title">12. A股宽基 · 沪深300 / 中证1000 / 中证2000 价格走势</div>', unsafe_allow_html=True)
    st.caption("三只指数显示实际收盘点位，不做归一化。点线“高”为当前坐标时间内的最高收盘价和日期，随时间切换、滑块缩放自动更新；虚线“现”保持最新收盘价。")
    figure = _build_china_drawdown()
    _render_adaptive_macro_figure(figure, "china_equity_drawdown", standard=True)
    for row in (figure.layout.meta or {}).get("price_summary", []):
        st.caption(f'{row["name"]}（{row["symbol"]}）最新收盘：{row["close"]:,.2f}（{row["date"]}）')
    st.caption("中证指数官网已完成交易日收盘，价格指数，不含股息再投资。发布前数据为中证官方回溯数据；区间高点只按当前可见时间内的有效收盘价计算。最新日期以图中观测日为准。")
    add_sources([(name, f"https://www.csindex.com.cn/zh-CN/indices/index-detail/{code}")
                 for code, name in (("000300", "沪深300"), ("000852", "中证1000"), ("932000", "中证2000"))])
    st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)


@st.fragment(key="macro_chart_9_viewport")
def render_macro_chart_9(prebuilt_fig=None):
    st.markdown(
        '<div class="section-title">9. US Equity Risk & Volatility Structure</div>'
        '<div class="section-description">VIX · VIXEQ · S&P 500 (R1) · VIXEQ−VIX (R2) · VIXEQ/VIX (R3) · COR1M / COR3M (R4)</div>',
        unsafe_allow_html=True,
    )
    base_fig = prebuilt_fig if prebuilt_fig is not None else build_fig9("5Y")
    _render_adaptive_macro_figure(base_fig, "us_equity_risk")
    st.markdown(f'<div class="mini-description">{US_EQUITY_RISK_DESCRIPTION}</div>', unsafe_allow_html=True)
    add_sources([
        ("Cboe VIX", "https://www.cboe.com/tradable-products/vix/"),
        ("Cboe VIXEQ / Dispersion", "https://www.cboe.com/us/indices/dispersion/"),
        ("Cboe COR1M / COR3M", "https://www.cboe.com/us/indices/implied/"),
        ("FRED S&P 500 (SP500)", "https://fred.stlouisfed.org/series/SP500"),
    ])
    st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)


@st.fragment(key="vix_term_structure_chart")
def render_macro_chart_10(prebuilt_fig=None):
    st.markdown(
        '<div class="section-title">10. VIX & VIX3M Term Structure</div>'
        '<div class="section-description">VIX（30天≈1M） · VIX3M（约3M） · VIX3M−VIX (R1)</div>',
        unsafe_allow_html=True,
    )
    st.caption("VIX反映未来30个日历天（约1个月）的年化隐含波动率，正式代码仍是VIX；VIX3M约为3个月。上方1M、3M等按钮只控制历史显示范围，不改变指数期限。")
    base_fig = prebuilt_fig if prebuilt_fig is not None else _safe_macro_build(
        "Chart 10", lambda: _cached_macro_figure(10, _macro_snapshot_revision(), CHART_BUILD),
    )
    _render_adaptive_macro_figure(base_fig, "vix_term_structure")
    st.markdown('<div class="mini-description"><div class="parameter-note"><b>VIX：</b>标普500指数未来30个日历天（约1M）的年化隐含波动率指标，代表近期波动风险的期权定价。</div><div class="parameter-note"><b>VIX3M：</b>标普500指数约未来3个月的年化隐含波动率指标，代表较长期波动风险的期权定价。</div><div class="parameter-note"><b>VIX3M−VIX (R1)：</b>同日3个月减1个月隐含波动率之差，代表近远期波动风险的相对定价；收窄或转负表示近端波动更贵，单位为波动率点。</div><div class="parameter-context">口径说明：差值只使用同日有效观测；两条波动率在左轴，差值在右轴R1。</div></div>', unsafe_allow_html=True)
    add_sources([
        ("FRED · VIX (VIXCLS)", "https://fred.stlouisfed.org/series/VIXCLS"),
        ("FRED · VIX3M (VXVCLS)", "https://fred.stlouisfed.org/series/VXVCLS"),
    ])
    st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)


@st.fragment(key="precious_metals_chart")
def render_macro_chart_11(prebuilt_fig=None):
    st.markdown(
        '<div class="section-title">15. Precious Metals</div>'
        '<div class="section-description">Gold · Silver · Gold/Silver Ratio · Gold Volatility GVZ</div>',
        unsafe_allow_html=True,
    )
    base_fig = prebuilt_fig if prebuilt_fig is not None else _safe_macro_build(
        "Chart 11", lambda: _cached_macro_figure(11, _macro_snapshot_revision(), CHART_BUILD),
    )
    _render_adaptive_macro_figure(base_fig, "precious_metals")
    st.markdown(f'<div class="mini-description">{PRECIOUS_METALS_DESCRIPTION}</div>', unsafe_allow_html=True)
    add_sources([
        ("Yahoo Finance · Gold Futures GC=F", "https://finance.yahoo.com/quote/GC=F/history/"),
        ("Yahoo Finance · Silver Futures SI=F", "https://finance.yahoo.com/quote/SI=F/history/"),
        ("FRED · Cboe Gold ETF Volatility Index (GVZCLS)", "https://fred.stlouisfed.org/series/GVZCLS"),
        ("Cboe · Gold Volatility", "https://www.cboe.com/tradable_products/vix/vix_historical_data/"),
    ])
    st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)


@st.fragment(key="crypto_chart")
def render_macro_chart_12(prebuilt_fig=None):
    st.markdown(
        '<div class="section-title">17. Crypto Market</div>'
        '<div class="section-description">BTC · ETH · ETH/BTC · BTC 30D 实际波动率</div>',
        unsafe_allow_html=True,
    )
    base_fig = prebuilt_fig if prebuilt_fig is not None else _safe_macro_build(
        "Chart 12", lambda: _cached_macro_figure(12, _macro_snapshot_revision(), CHART_BUILD),
    )
    _render_adaptive_macro_figure(base_fig, "crypto_market")
    st.markdown(f'<div class="mini-description">{CRYPTO_MARKET_DESCRIPTION}</div>', unsafe_allow_html=True)
    add_sources([
        ("Yahoo Finance · Bitcoin BTC-USD", "https://finance.yahoo.com/quote/BTC-USD/history/"),
        ("Yahoo Finance · Ethereum ETH-USD", "https://finance.yahoo.com/quote/ETH-USD/history/"),
    ])
    st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)


@st.fragment(key="macro_chart_13_viewport")
def render_macro_chart_13(prebuilt_fig=None):
    st.markdown(
        '<div class="section-title">16. Copper Flow & COMEX–LME Spread</div>'
        '<div class="section-description">COMEX inventory · LME inventory · LME 3M (R1) · COMEX HG converted (R1) · COMEX−LME 3M spread (R2)</div>',
        unsafe_allow_html=True,
    )
    base_fig = prebuilt_fig if prebuilt_fig is not None else build_fig13("5Y")
    _render_adaptive_macro_figure(base_fig, "copper_flow")
    st.markdown('<div class="mini-description"><div class="parameter-note"><b>COMEX 库存：</b>COMEX仓库铜库存，代表美国该交割体系内报告的铜存量；单位为千公吨，不是全球铜总库存。</div><div class="parameter-note"><b>LME 库存：</b>LME仓库铜库存，代表该交易所仓库体系内报告的铜存量；单位为千公吨，可与COMEX对照观察库存地域分布。</div><div class="parameter-note"><b>LME 3M 铜价 (R1)：</b>LME三个月期铜价，代表该市场三个月期限的铜定价；单位为美元/公吨。</div><div class="parameter-note"><b>COMEX HG 换算价 (R1)：</b>COMEX铜期货价格换算为美元/公吨，代表统一重量单位后的美国期货价格，便于与LME对照。</div><div class="parameter-note"><b>COMEX−LME 3M 价差 (R2)：</b>同日COMEX换算价减LME三个月铜价，代表两地铜价差；为正表示COMEX较贵。期限、交割及费用不同，不能直接视为无风险套利利润。</div><div class="parameter-context">口径说明：库存单位为千公吨，价格与价差为美元/公吨；库存一增一减需结合交割、运输及需求判断。</div></div>', unsafe_allow_html=True)
    add_sources([
        ("CME · COMEX Warehouse & Depository Stocks", "https://www.cmegroup.com/solutions/clearing/operations-and-deliveries/nymex-delivery-notices.html"),
        ("CME · Copper Stocks 原始日报", "https://www.cmegroup.com/delivery_reports/Copper_Stocks.xls"),
        ("Yahoo Finance · COMEX Copper HG=F", "https://finance.yahoo.com/quote/HG=F/history/"),
        ("LME Copper", "https://www.lme.com/copper"),
        ("LME Warehouse & Stocks Reports", "https://www.lme.com/Market-data/Reports-and-data/Warehouse-and-stocks-reports"),
        ("Westmetall · LME Copper Daily Table", "https://www.westmetall.com/en/markdaten.php?action=table&field=LME_Cu_cash"),
        ("COCHILCO · Copper Inventories", "https://boletin.cochilco.cl/estadisticas/inventarios.asp"),
    ])
    st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)


@st.fragment(key="macro_chart_14_viewport")
def render_macro_chart_14(prebuilt_fig=None):
    st.markdown(
        '<div class="section-title">13. China Government Yields & US 5Y Real Yield</div>'
        '<div class="section-description">China 2Y / 10Y · US 5Y Real · TIPS · China 10Y−2Y (R1)</div>',
        unsafe_allow_html=True,
    )
    base_fig = prebuilt_fig if prebuilt_fig is not None else _safe_macro_build(
        "Chart 14", lambda: _cached_macro_figure(14, _macro_snapshot_revision(), CHART_BUILD))
    _render_adaptive_macro_figure(base_fig, "china_rates")
    st.markdown('<div class="mini-description"><div class="parameter-note"><b>China 2Y：</b>中国2年期国债收益率，代表人民币较短期限国债的市场利率水平；单位为年化%。</div><div class="parameter-note"><b>China 10Y：</b>中国10年期国债收益率，代表人民币长期国债利率基准；单位为年化%。</div><div class="parameter-note"><b>US 5Y Real · TIPS：</b>美国5年期TIPS实际收益率，代表美元中期实际利率，用于跨市场对照；与中国名义国债收益率的差不能直接当作可交易套息收益。</div><div class="parameter-note"><b>China 10Y−2Y (R1)：</b>中国10年减2年国债收益率之差，代表中国国债曲线斜率；上升为变陡，负值为倒挂；单位为百分点。</div><div class="parameter-context">口径说明：收益率单位为年化%，曲线利差单位为百分点；各曲线保留实际观测日。</div></div>', unsafe_allow_html=True)
    add_sources([
        ("Eastmoney · China Treasury Yield History", "https://data.eastmoney.com/cjsj/zmgzsyl.html"),
        ("FRED · US 5Y TIPS Real Yield (DFII5)", "https://fred.stlouisfed.org/series/DFII5"),
    ])
    st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)


@st.fragment(key="macro_chart_15_viewport")
def render_macro_chart_15(prebuilt_fig=None):
    st.markdown(
        '<div class="section-title">14. Japan Government Yields & Nikkei 225 & USD/JPY</div>'
        '<div class="section-description">Japan 2Y / 10Y · Japan 10Y−2Y (R1) · Nikkei 225 (R2) · USD/JPY (R3)</div>',
        unsafe_allow_html=True,
    )
    base_fig = prebuilt_fig if prebuilt_fig is not None else _safe_macro_build(
        "Chart 15", lambda: _cached_macro_figure(15, _macro_snapshot_revision(), CHART_BUILD))
    _render_adaptive_macro_figure(base_fig, "japan_rates")
    st.markdown('<div class="mini-description"><div class="parameter-note"><b>Japan 2Y：</b>日本2年期国债收益率，代表日元较短期限国债的市场利率水平；单位为年化%。</div><div class="parameter-note"><b>Japan 10Y：</b>日本10年期国债收益率，代表日元长期国债利率基准；单位为年化%。</div><div class="parameter-note"><b>Japan 10Y−2Y (R1)：</b>日本10年减2年国债收益率之差，代表日本国债曲线斜率；上升为变陡，负值为倒挂；单位为百分点。</div><div class="parameter-note"><b>Nikkei 225 (R2)：</b>日经225指数，代表其日本上市公司成分股的综合表现；单位为指数点，使用已完成交易日的收盘值。</div><div class="parameter-note"><b>USD/JPY (R3)：</b>美元兑日元汇率，代表1美元可兑换多少日元；数值上升为日元走弱，下降为日元走强，不是日元综合指数。</div><div class="parameter-context">口径说明：USD/JPY使用已完成交易日的日线价格；盘中报价不作为完成日线。R1为百分点，R2为指数点，R3为日元/美元。</div></div>', unsafe_allow_html=True)
    add_sources([
        ("Japan MOF · JGB Interest Rates", "https://www.mof.go.jp/jgbs/reference/interest_rate/index.htm"),
        ("Yahoo Finance · Nikkei 225", "https://finance.yahoo.com/quote/%5EN225/history/"),
        ("Yahoo · USD/JPY daily closes", "https://finance.yahoo.com/quote/JPY%3DX/history/"),
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
    except Exception as exc:
        logging.exception("Chart builder failed: %s", label)
        fig = _macro_error_figure(label)
        fig.update_layout(meta={"data_unavailable": True,
                                "build_error_type": type(exc).__name__})
        return fig


def _macro_snapshot_revision():
    """Invalidate constructed figures when a repository snapshot is replaced."""
    folder = Path(__file__).resolve().parent / "data_snapshots"
    # Live-only daily feeds must refresh even without a snapshot commit.
    revision = [("live_refresh", int(time.time() // 300))]
    # Include FRED's verified nested last-good cache when a scheduled
    # GitHub sync replaces observations, not only top-level market JSONs.
    for path in sorted(folder.rglob("*.json")):
        try:
            stat = path.stat()
        except OSError:
            continue
        revision.append((path.name, stat.st_mtime_ns, stat.st_size))
    return tuple(revision)


def _cache_safe_figure(figure):
    """Preserve exact samples through Plotly 6/Streamlit pickle caching.

    Plotly pickles NumPy vectors as dtype/bdata dictionaries. New sessions
    have no last-good ECharts option to rescue unreadable cached vectors.
    Store ordinary sequences, preserving dates, null gaps and values.
    """
    for trace in figure.data:
        for field in ("x", "y"):
            values = getattr(trace, field, None)
            if values is None or not callable(getattr(values, "tolist", None)):
                continue
            if field == "x" and getattr(getattr(values, "dtype", None), "kind", None) == "M":
                # datetime64[ns].tolist() returns epoch integers, not dates.
                converted = [pd.Timestamp(value) for value in values]
            else:
                converted = values.tolist()
            # Plotly ignores assignments whose values compare equal. Clear
            # first so an equivalent list really replaces the binary vector.
            setattr(trace, field, None)
            setattr(trace, field, converted)
    return figure


@st.cache_data(ttl=300, max_entries=32, show_spinner=False)
def _cached_macro_figure(chart_number, snapshot_revision, build_revision):
    """Reuse successful construction; callers receive isolated figure copies."""
    builders = {
        1: build_fig1, 2: build_fig2, 3: build_fig3, 4: build_fig4,
        9: build_fig9, 10: build_fig10, 11: build_fig11, 12: build_fig12,
        13: build_fig13, 14: build_fig14, 15: build_fig15,
    }
    builder = builders[chart_number]
    figure = builder("5Y")
    if not _figure_has_real_observations(figure):
        raise ValueError("Source has no observed chart samples")
    return _cache_safe_figure(figure)


@st.cache_data(ttl=300, max_entries=8, show_spinner=False)
def _cached_hk_bundle(snapshot_revision, build_revision):
    figures = build_fig5("5Y")
    if not isinstance(figures, (list, tuple)) or len(figures) < 4 or not any(_figure_has_real_observations(f) for f in figures):
        raise ValueError("HK figure bundle unavailable")
    if not all(_figure_has_real_observations(figure) for figure in figures):
        raise IncompleteObservedBundle(figures)
    return [_cache_safe_figure(figure) for figure in figures]


def _safe_hk_bundle(snapshot_revision):
    try:
        figures = _cached_hk_bundle(snapshot_revision, CHART_BUILD)
    except IncompleteObservedBundle as partial:
        figures = partial.figures
    except Exception:
        logging.exception("Composite HK liquidity bundle failed; rescuing core official data")
        figures = [_macro_error_figure(f"Chart {number}") for number in range(5, 9)]

    # A background refresh may yield an empty composite plot without raising.
    # Banking and funding are official stored data; salvage them separately.
    if not _figure_has_real_observations(figures[1]) or not _figure_has_real_observations(figures[2]):
        try:
            banking, funding = build_hk_core_snapshot_figures("5Y")
            if not _figure_has_real_observations(figures[1]) and _figure_has_real_observations(banking):
                figures[1] = banking
            if not _figure_has_real_observations(figures[2]) and _figure_has_real_observations(funding):
                figures[2] = funding
        except Exception:
            logging.exception("Independent HKMA banking/HIBOR source recovery failed")
    return figures


def _build_macro_figures_parallel(on_complete=None, auxiliary_jobs=None, on_aux_complete=None, budget=8.0):
    """Build concurrently and optionally publish completed charts immediately.

    Only data access and Plotly figure construction run in worker threads.
    Streamlit widgets/rendering stay on the main script thread.
    """
    snapshot_revision = _macro_snapshot_revision()

    def cached_chart(number):
        return _safe_macro_build(f"Chart {number}", lambda: _cached_macro_figure(number, snapshot_revision, CHART_BUILD))

    jobs = {
        1: lambda: cached_chart(1),
        2: lambda: cached_chart(2),
        3: lambda: cached_chart(3),
        4: lambda: cached_chart(4),
        "hk5": lambda: _safe_hk_bundle(snapshot_revision),
        9: lambda: cached_chart(9),
        10: lambda: cached_chart(10),
        11: lambda: cached_chart(11),
        12: lambda: cached_chart(12),
        13: lambda: cached_chart(13),
        14: lambda: cached_chart(14),
        15: lambda: cached_chart(15),
    }
    revision = (snapshot_revision, CHART_BUILD)
    futures = submit_jobs(jobs, name="macro-chart", workers=6, budget=budget, revision=revision)
    aux_futures = submit_jobs(auxiliary_jobs or {}, name="dashboard-aux", workers=2,
                              budget=budget, revision=(st.session_state.setdefault("_dashboard_session_token", uuid.uuid4().hex), _quote_refresh_key()))
    futures.update(aux_futures)
    results = {}
    published = set()
    for key, future in completed_jobs(futures, budget=budget):
        try:
            value = future.result()
        except Exception:
            logging.exception("Dashboard job failed: %s", key)
            continue
        if future in aux_futures:
            if on_aux_complete is not None:
                on_aux_complete(key, value)
            continue
        results[key] = value
        if on_complete is not None:
            if key == "hk5":
                for number in (5, 6, 7, 8):
                    on_complete(number, value[number - 5]); published.add(number)
            else:
                on_complete(key, value); published.add(key)
    # Running tasks remain bounded in shared pools and can warm caches for recovery.
    st.session_state["_late_dashboard_jobs"] = {future: key for future, key in futures.items()
                                                if not future.done()}
    for key in jobs:
        if key not in results:
            results[key] = ([_macro_error_figure(f"Chart {n}") for n in range(5, 9)]
                            if isinstance(key, str) else _macro_error_figure(f"Chart {key}"))
    if on_complete is not None:
        for number in range(1, 16):
            if number not in published:
                if number in (5, 6, 7, 8):
                    value = results["hk5"][number-5]
                else:
                    value = results[number]
                on_complete(number, value)

    hk5_bundle = results["hk5"]
    return {
        1: results[1],
        2: results[2],
        3: results[3],
        4: results[4],
        5: hk5_bundle[0],
        6: hk5_bundle[1],
        7: hk5_bundle[2],
        8: hk5_bundle[3],
        9: results[9],
        10: results[10],
        11: results[11],
        12: results[12],
        13: results[13],
        14: results[14],
        15: results[15],
    }


st.markdown(
    '<div id="macro-charts" class="section-anchor"></div>'
    '<div class="section-kicker">MACRO CHARTS</div>'
    '<div class="section-title">US monetary policy, Treasury yields and inflation expectations</div>',
    unsafe_allow_html=True,
)

# Reserve the existing document order, then fill sections as workers finish.
# Only the main Streamlit thread creates containers, fragments and widgets.
macro_slots = {}
section_headers = {5: "HONG KONG LIQUIDITY", 9: "EQUITY RISK & DRAWDOWNS",
                   14: "ASIA RATES", 11: "COMMODITIES", 12: "CRYPTO MARKET"}
for number in MACRO_DISPLAY_ORDER:
    if number == "us_drawdown":
        _render_equity_drawdown()
    elif number == "cn_drawdown":
        _render_china_drawdown()
    else:
        if number in section_headers:
            st.markdown(f'<div class="section-kicker">{section_headers[number]}</div>', unsafe_allow_html=True)
        macro_slots[number] = st.container()


def _render_completed_macro_chart(number, figure):
    renderers = {
        1: render_macro_chart_1, 2: render_macro_chart_2, 3: render_macro_chart_3,
        4: render_macro_chart_4, 5: render_macro_chart_5, 6: render_macro_chart_6,
        7: render_macro_chart_7, 8: render_macro_chart_8, 9: render_macro_chart_9,
        10: render_macro_chart_10, 11: render_macro_chart_11, 12: render_macro_chart_12,
        13: render_macro_chart_13, 14: render_macro_chart_14, 15: render_macro_chart_15,
    }
    with macro_slots[number]:
        renderers[number](figure)


_initial_symbols = _watchlist_symbols()
_initial_watch_missing = [symbol for symbol in _initial_symbols
                          if symbol not in st.session_state.get("_watchlist_quotes_snapshot", {})]
_auxiliary = {}
if not st.session_state.get("_market_quotes_snapshot") or time.time()-st.session_state.get("_market_quotes_snapshot_time", 0) >= 60:
    _market_key = (_quote_refresh_key(), st.session_state.get("_market_refresh_key", 0))
    _auxiliary["market"] = lambda: _fetch_quote_rows(MARKET_SYMBOLS.values(), _market_key)
if _initial_watch_missing:
    _auxiliary["watchlist"] = lambda: _fetch_quote_rows(_initial_watch_missing)
_rendered_quote_sections = set()


def _publish_quote_section(key, rows=None):
    if key in _rendered_quote_sections:
        return
    _rendered_quote_sections.add(key)
    if key == "market":
        if rows is not None:
            st.session_state["_market_quotes_snapshot"] = {
                name: _remember_quote(symbol, rows.get(symbol, _empty_quote()))
                for name, symbol in MARKET_SYMBOLS.items()}
            st.session_state["_market_quotes_snapshot_time"] = time.time()
        with market_overview_slot:
            render_market_overview(defer_initial=True)
    else:
        if rows is not None:
            _apply_watchlist_quote_rows(_initial_symbols, rows, _initial_watch_missing)
        with watchlists_slot:
            render_watchlists(defer_initial=True)


for _section in ("market", "watchlist"):
    if _section not in _auxiliary:
        _publish_quote_section(_section)
with st.spinner("正在加载图表…"):
    macro_figures = _build_macro_figures_parallel(
        on_complete=_render_completed_macro_chart, auxiliary_jobs=_auxiliary,
        on_aux_complete=_publish_quote_section)
for _section in ("market", "watchlist"):
    _publish_quote_section(_section)


# Poll only completion/revision metadata; source fetching stays in bounded workers.
# An app rerun is needed to replace timed-out fragment arguments with ready data.
st.session_state["_source_watch_revision"] = _macro_snapshot_revision()
st.session_state["_source_watch_until"] = time.monotonic() + 120


def _publish_late_dashboard_result(key, value):
    """Commit delayed observations on the UI thread, retaining newer quotes."""
    if key not in ("market", "watchlist"):
        figures = value if isinstance(value, (list, tuple)) else (value,)
        return any(_figure_has_real_observations(figure) for figure in figures)
    if not isinstance(value, dict) or not any(
        row.get("price") is not None for row in value.values() if isinstance(row, dict)
    ):
        return False
    if key == "market":
        previous = st.session_state.get("_market_quotes_snapshot", {})
        snapshot = {}
        for name, symbol in MARKET_SYMBOLS.items():
            old = previous.get(name, _empty_quote())
            late = value.get(symbol, _empty_quote())
            snapshot[name] = _remember_quote(symbol, _newest_quote([old, late]))
        st.session_state["_market_quotes_snapshot"] = snapshot
        st.session_state["_market_quotes_snapshot_time"] = time.time()
    else:
        symbols = _watchlist_symbols()
        previous = st.session_state.get("_watchlist_quotes_snapshot", {})
        requested = [symbol for symbol in symbols if symbol in value]
        rows = {symbol: _newest_quote([previous.get(symbol, _empty_quote()), value[symbol]])
                for symbol in requested}
        _apply_watchlist_quote_rows(symbols, rows, requested)
    return True


@st.fragment(run_every=2, key="source_completion")
def _poll_source_completion():
    if time.monotonic() > st.session_state.get("_source_watch_until", 0):
        # A long-open page still needs to notice new repository snapshots.
        # After startup, check only file metadata once per minute.
        now = time.monotonic()
        if now - st.session_state.get("_last_source_revision_check", 0) < 60:
            return
        st.session_state["_last_source_revision_check"] = now
    pending = st.session_state.get("_late_dashboard_jobs", {})
    ready = False
    for future, key in list(pending.items()):
        if not future.done():
            continue
        pending.pop(future, None)
        try:
            value = future.result()
            # Persist completed quotes before rerunning: a new refresh bucket
            # must not discard the successful result and start another fetch.
            completed = _publish_late_dashboard_result(key, value)
            ready = ready or completed
        except Exception:
            pass
    revision = _macro_snapshot_revision()
    if ready or revision != st.session_state.get("_source_watch_revision"):
        st.session_state["_source_watch_revision"] = revision
        st.rerun()


_poll_source_completion()

@st.fragment(run_every=60, key="all_source_freshness")
def _render_all_source_freshness(figures):
    rows = []
    def add(module, symbol, row):
        _, quote_ts = _quote_session_context(row, _symbol_market(symbol))
        when = (datetime.fromtimestamp(quote_ts, DASHBOARD_TZ).strftime("%Y-%m-%d %H:%M:%S HKT")
                if quote_ts is not None else "未取得")
        rows.append({"模块": module, "代码": symbol, "最新报价时间": when})
    for label, symbol in MARKET_SYMBOLS.items():
        add("市场概览", symbol, st.session_state.get("_market_quotes_snapshot", {}).get(label, {}))
    for symbol, row in st.session_state.get("_watchlist_quotes_snapshot", {}).items():
        add("自选", symbol, row)
    display_figures = {MACRO_DISPLAY_NUMBER[number]: figure
                       for number, figure in figures.items()}
    display_figures[11] = _build_equity_drawdown()
    display_figures[12] = _build_china_drawdown()
    render_freshness_overview(display_figures, quote_rows=rows, news=_read_existing_news_snapshot())

_render_all_source_freshness(macro_figures)

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

