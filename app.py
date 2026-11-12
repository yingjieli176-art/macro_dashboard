import html
import importlib
from collections.abc import Mapping
from copy import deepcopy
import json
import logging
import math
import os
import time
import uuid
import requests
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
if _echarts_axes is not None and getattr(_echarts_axes, "SRF_JPY_BAR_WIDTH", None) != 8:
    _echarts_axes = importlib.reload(_echarts_axes)
try:
    from macro_platform import linked_charts as _linked_charts
except ImportError:
    _linked_charts = None
from macro_platform import chart_axes as _chart_axes
from macro_platform import dealer_gamma as _dealer_gamma
from macro_platform import move_index as _move_index
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
try:
    from macro_platform.tail_risk import load_tail_risk_snapshot
except ImportError:
    def load_tail_risk_snapshot(symbol):
        return pd.DataFrame(columns=["observation_date", symbol])
try:
    from macro_platform.spx_options import load_spx_put_call_snapshot
except ImportError:
    def load_spx_put_call_snapshot():
        return pd.DataFrame(columns=["observation_date", "SPX_PCR"])
from macro_platform import ai_credit as _ai_credit
if not hasattr(_ai_credit, "IG_OAS_NAME"):
    _ai_credit = importlib.reload(_ai_credit)
from macro_platform import copper as _copper_module
from macro_platform.srf_usage import load_srf_usage, usage_caption
# Refresh the builder during rolling deployments with cached modules.
if not getattr(_copper_module, "TCRC_STANDALONE", False):
    _copper_module = importlib.reload(_copper_module)
build_copper_flow_spread_figure = _copper_module.build_copper_flow_spread_figure
build_copper_tcrc_figure = _copper_module.build_copper_tcrc_figure
from macro_platform.copper_tcrc import METHOD_URL as COPPER_TCRC_METHOD_URL
from macro_platform import dashboard_layout as _dashboard_layout
if _dashboard_layout.CHART_NUMBERING != "display_us_credit_jp_cn_20":
    _dashboard_layout = importlib.reload(_dashboard_layout)
from macro_platform.asia_rates import build_china_rates_figure, build_japan_rates_figure
from macro_platform.yen_index import load_yen_market_index
from macro_platform.sp500_nikkei_ratio import build_sp500_nikkei_ratio_figure
try:
    import macro_platform.yen_carry as _yen_carry
    if getattr(_yen_carry, "CARRY_IMPLIED_VERSION", None) != 1:
        _yen_carry = importlib.reload(_yen_carry)
except ImportError:
    _yen_carry = None
from macro_platform.security_search import search_securities
from macro_platform import freshness_overview as _freshness_overview
if _freshness_overview.CHART_NUMBERING != _dashboard_layout.CHART_NUMBERING:
    _freshness_overview = importlib.reload(_freshness_overview)
render_freshness_overview = _freshness_overview.render_freshness_overview
from macro_platform.watchlist_state import WATCHLIST_KEYS, decode_watchlists, encode_watchlists, merge_default_watchlists, watchlist_needs_default_migration
from macro_platform.market_history import completed_daily_closes
# Keep startup-compatible with older data.py during Streamlit Cloud rolling
# deployments: optional/newer market getters must never crash the whole page.
import data as _market_data_module
try:
    from macro_platform import vix_market as _vix_market
except ImportError:
    _vix_market = None
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

get_dgs30 = getattr(_market_data_module, "get_dgs30", None)
if not callable(get_dgs30):
    def get_dgs30():
        return _fred_series("DGS30")

get_hy_oas = getattr(_market_data_module, "get_hy_oas", pd.DataFrame)
get_ig_oas = getattr(_market_data_module, "get_ig_oas", pd.DataFrame)


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
from macro_platform.dashboard_layout import MACRO_DISPLAY_ORDER, MACRO_DISPLAY_NUMBER, NUMERIC_CHART_IDS, HK_CHART_IDS
from macro_platform import japan_corridor as _japan_corridor
from macro_platform import jpy_implied_vol as _jpy_iv
from macro_platform.parameter_guide import CHART_PARAMETER_GUIDES
CHART_BUILD = "V1.0"
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


def _refresh_vix_market():
    if _vix_market is None:
        return
    quote = _vix_market.fetch_quote(get=http_get)
    _vix_market.write_quote(quote)
    # Share the existing FRED writer lock so an older background response
    # cannot overwrite a newly confirmed VIX close.
    with _market_data_module._FRED_LOCK:
        _vix_market.append_confirmed_close(quote)


@st.cache_resource(show_spinner=False, on_release=lambda worker: worker.close())
def _start_vix_quote_updater():
    return PeriodicWorker(_refresh_vix_market, 60, "vix-market-updater")


if _vix_market is not None:
    _start_vix_quote_updater()


@st.fragment(run_every=60, key="vix_latest_quote")
def render_latest_vix_quote():
    quote = _vix_market.read_quote() if _vix_market is not None else None
    if not quote:
        st.caption("VIX最新延迟报价暂未取得，历史曲线仍显示已核实的收盘数据。")
        return
    when = datetime.fromisoformat(quote["observed_at"])
    label = "最近收盘" if _vix_market.confirmed_close(quote) else "最新延迟报价"
    st.markdown(f'**VIX（{label}）：{quote["value"]:.2f}**')
    st.caption(f'报价时间：{when.astimezone(ZoneInfo("America/New_York")):%Y-%m-%d %H:%M:%S} 美东'
               f' / {when.astimezone(ZoneInfo("Asia/Shanghai")):%Y-%m-%d %H:%M:%S} 北京'
               ' · Cboe延迟行情，非逐笔实时 · 每60秒检查更新')

st.markdown("""
<style>
.block-container { padding-top: 0.70rem; padding-bottom: 2rem; max-width: 1760px; }
html, body, [class*="css"] { font-family: "Noto Sans TC", "Noto Sans CJK TC", "Microsoft JhengHei", "PingFang TC", "Segoe UI", sans-serif; }
.dashboard-title { font-size: 1.9rem; font-weight: 700; letter-spacing: -0.02em; margin-bottom: 0.1rem; }
.section-title { font-size: 1.18rem; font-weight: 680; letter-spacing: -0.012em; margin-top: 0.52rem; margin-bottom: 0.04rem; min-height: 26px; display: flex; align-items: center; color:#1f2937; }
.section-description { color: #7b8493; font-size: 0.80rem; margin-bottom: 0.16rem; min-height: 17px; display: flex; align-items: center; }
.chart-parameters { color: #4b5563; font-size: 0.78rem; line-height: 1.55; margin: 4px 0 8px; overflow-wrap: anywhere; }
.chart-parameters > div { margin: 2px 0; }
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
        <div class="dashboard-subtitle" style="font-size:.68rem;color:#64748b">版本：{CHART_BUILD} · 自适应坐标轴</div>
      </div>
      <div class="dashboard-links">
        <a href="#market-overview">市场概览</a>
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
    if not 946684800 <= ts <= time.time() + 300:
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

def add_sources(sources, chart_key):
    notes = "".join(
        f"<div><b>{html.escape(name)}</b> · {html.escape(definition)}</div>"
        for name, definition in CHART_PARAMETER_GUIDES[chart_key]
    )
    st.markdown(f'<div class="chart-parameters">{notes}</div>', unsafe_allow_html=True)
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
                           (get_effr, "EFFR"), (get_sofr, "SOFR"),
                           (lambda: get_fred_series("SRFTSYD"), "SRFTSYD")):
        try:
            sources[column] = getter()
        except Exception:
            sources[column] = pd.DataFrame(columns=["observation_date", column])
    try:
        usage = load_srf_usage()
    except Exception:
        usage = pd.DataFrame(columns=["observation_date", "SRF_USAGE_BN"])
    sources["SRF_USAGE_BN"] = usage
    dates = filter_range(pd.concat(list(sources.values()), ignore_index=True), date_range)["observation_date"]
    fig = go.Figure()
    # IORB includes weekends; the other rates use business-day calendars.
    # Keep each source's actual rows, including any explicit missing reading.
    for column, name, width in [("IORB", "IORB", 2.6), ("RRPONTSYAWARD", "ON RRP", 2.6), ("EFFR", "EFFR", 2.6), ("SOFR", "SOFR", 2.2), ("SRFTSYD", "SRF", 2.6)]:
        frame = sources[column]
        add_line(fig, frame.loc[frame["observation_date"].isin(dates)], column, name, width,
                 dash="dash" if column == "SRFTSYD" else None)
    usage = usage.loc[usage["observation_date"].isin(dates)]
    if usage.empty:
        _mark_missing_series(fig, "SRF 实际用量 (R1)")
    else:
        fig.add_trace(go.Bar(x=usage["observation_date"], y=usage["SRF_USAGE_BN"],
            name="SRF 实际用量 (R1)", yaxis="y2", width=4*86400000, marker=dict(color="#007f73", opacity=1.0, line=dict(color="#004c46", width=1)),
            hovertemplate="SRF实际用量: %{y:.3f} 十亿美元<extra></extra>"))
    fig.update_layout(yaxis_title="Rate (%)", barmode="overlay", yaxis2=dict(
        title="SRF usage · USD bn", overlaying="y", side="right", showgrid=False,
        rangemode="tozero", zeroline=True, fixedrange=True))
    return apply_chart_style(fig, chart_height(310, 420), date_range)

def build_fig2(date_range):
    """Observed ten-year nominal, TIPS real yield and breakeven inflation.

    DFII10 is the observed ten-year inflation-indexed yield. Plot it once;
    do not relabel DFII5 or manufacture missing real-yield observations.
    """
    observed_nominal = get_dgs10()
    inferred_dates = list(observed_nominal.attrs.get("identity_derived_dates", []))
    data = (
        observed_nominal
        .merge(get_dfii10(), on="observation_date", how="outer")
        .merge(get_fred_series("T10YIE"), on="observation_date", how="outer")
        .sort_values("observation_date")
    )
    for column in ("DGS10", "DFII10", "T10YIE"):
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
        ("DGS10", "10年期名义收益率（DGS10）", 2.8, None, None),
        ("DFII10", "10年期实际收益率（TIPS · DFII10，右轴）", 2.6, None, "y2"),
        ("T10YIE", "10年期盈亏平衡通胀率（BEI · T10YIE，右轴）", 2.5, "dot", "y2"),
    ]:
        add_line(fig, data, column, name, width, dash, yaxis)
    fig.update_layout(
        yaxis_title="名义收益率（%）",
        yaxis2=dict(
            title="实际收益率 / 盈亏平衡通胀率（%）", overlaying="y", side="right",
            anchor="free", position=0.99, showgrid=False, zeroline=False,
            fixedrange=True, automargin=False, tickfont=dict(size=9),
            ticks="outside", ticklen=3,
        ),
    )
    return apply_chart_style(fig, chart_height(310, 420), date_range)

def build_fig3(date_range):
    dgs10 = get_dgs10()
    inferred_dates = list(dgs10.attrs.get("identity_derived_dates", []))
    data = get_dgs3mo().merge(get_dgs2(), on="observation_date", how="outer").merge(dgs10, on="observation_date", how="outer").merge(get_dgs30(), on="observation_date", how="outer").sort_values("observation_date")
    for column in ("DGS3MO", "DGS2", "DGS10", "DGS30"):
        data[column] = pd.to_numeric(data.get(column), errors="coerce")
    # Derive curve spreads locally from the displayed yields. This removes two
    # redundant FRED requests and guarantees spread/yield internal consistency.
    data["T10Y2Y"] = data["DGS10"] - data["DGS2"]
    data["T30Y10Y"] = data["DGS30"] - data["DGS10"]
    data = filter_range(data, date_range); fig = go.Figure()
    if inferred_dates:
        fig.update_layout(meta={"data_quality_notes": [
            f"10Y 名义收益率有 {len(inferred_dates)} 个日期由 DFII10＋T10YIE 恒等式重建（非独立 DGS10 实测值）。"
        ]})
    for column, name, width in [("DGS3MO", "3M", 2.2), ("DGS2", "2Y", 2.4), ("DGS10", "10Y", 2.8), ("DGS30", "30Y", 2.6)]: add_line(fig, data, column, name, width)
    add_line(fig, data, "T10Y2Y", "10Y−2Y (R1)", 2.2, "dot", "y2", "%"); add_line(fig, data, "T30Y10Y", "30Y−10Y (R1)", 2.2, "dash", "y2", "%")
    for name, color in {"30Y": "#dc2626", "10Y−2Y (R1)": "#ff994d", "30Y−10Y (R1)": "#00b6ed"}.items():
        fig.update_traces(line_color=color, selector=dict(name=name))
    fig.update_traces(selector=dict(name="10Y−2Y (R1)"), hovertemplate="10Y−2Y (R1): %{y:.3f}%<extra></extra>"); fig.update_traces(selector=dict(name="30Y−10Y (R1)"), hovertemplate="30Y−10Y (R1): %{y:.3f}%<extra></extra>")
    fig.update_layout(
        yaxis=dict(title="Yield (%)", fixedrange=True),
        yaxis2=dict(title="", overlaying="y", side="right",
                    anchor="free", position=0.99, showgrid=False, zeroline=True,
                    zerolinecolor="#9ca3af", fixedrange=True, automargin=False,
                    tickfont=dict(size=9), ticks="outside", ticklen=3),
    )
    ndx = filter_range(_load_yahoo_histories(("^NDX",))["^NDX"], date_range)
    name = "NASDAQ-100 (R2)"
    add_line(fig, ndx, "close", name, 2.4, yaxis="y3", unit=" pts")
    fig.update_traces(line_color="#9333ea", hovertemplate="NASDAQ-100: %{y:,.2f} pts<extra></extra>",
                      selector=dict(name=name))
    if not ndx.empty:
        fig.update_layout(
            xaxis_domain=[0, 0.87], yaxis2_position=0.89,
            yaxis3=dict(title="R2 · NASDAQ-100 (pts)", overlaying="y", side="right",
                        anchor="free", position=0.99, showgrid=False, fixedrange=True,
                        tickformat=",.0f", tickfont=dict(size=9), ticks="outside", ticklen=3),
        )
    fig = apply_chart_style(fig, chart_height(310, 420), date_range)
    if not ndx.empty:
        fig.update_layout(margin_r=130)
    return fig


def build_fig9(date_range):
    """US equity risk with implied correlation and same-date vol spreads."""
    frames = []
    sources = {}
    for series_id in ("VIXCLS", "SP500", "VXNCLS"):
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

    for symbol in ("COR3M",):
        try:
            correlation = load_correlation_snapshot(symbol)
            if not correlation.empty:
                frames.append(correlation)
                sources[symbol] = correlation
        except Exception:
            continue

    try:
        move_source = _move_index.load_move_snapshot()
        if not move_source.empty:
            frames.append(move_source)
            sources["MOVE"] = move_source
    except Exception:
        pass

    if not frames:
        fig = go.Figure()
        for name in ("VIX", "VIXEQ", "S&P 500 (R1)",
                     "VIXEQ/VIX (R2)", "COR3M (R3)", "MOVE 债市波动率（R4）", "MOVE/VIX (R5)", "VXN−VIX (R6)"):
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
    if "MOVE" in data.columns and "VIXCLS" in data.columns:
        vix = data["VIXCLS"].where(data["VIXCLS"].gt(0) & data["VIXCLS"].lt(float("inf")))
        move = data["MOVE"].where(data["MOVE"].gt(0) & data["MOVE"].lt(float("inf")))
        data["MOVE/VIX"] = (move / vix).replace([float("inf"), -float("inf")], float("nan"))
    if "VXNCLS" in data.columns and "VIXCLS" in data.columns:
        vxn = data.VXNCLS.where(data.VXNCLS.gt(0) & data.VXNCLS.lt(float("inf")))
        vix = data.VIXCLS.where(data.VIXCLS.gt(0) & data.VIXCLS.lt(float("inf")))
        data["VXN−VIX"] = vxn - vix
    data = filter_range(data, date_range)

    fig = go.Figure()
    for column, name, width, dash, axis, unit in (
        ("VIXCLS", "VIX", 3.0, None, None, ""),
        ("VIXEQ", "VIXEQ", 2.8, "dash", None, ""),
        ("SP500", "S&P 500 (R1)", 2.6, None, "y2", " pts"),
    ):
        source = sources.get(column, pd.DataFrame(columns=["observation_date"]))
        add_line(fig, data.loc[data["observation_date"].isin(source["observation_date"])],
                 column, name, width, dash, axis, unit)
    ratio_dates = [date for column in ("VIXEQ", "VIXCLS") if column in sources
                   for date in sources[column]["observation_date"]]
    add_line(fig, data.loc[data["observation_date"].isin(ratio_dates)],
             "VIXEQ/VIX", "VIXEQ/VIX (R2)", 2.8, "dot", "y3", unit="x")
    for symbol, dash in (("COR3M", "solid"),):
        source = sources.get(symbol, pd.DataFrame(columns=["observation_date"]))
        add_line(fig, data.loc[data["observation_date"].isin(source["observation_date"])],
                 symbol, f"{symbol} (R3)", 3.2, dash, "y4", unit=" pts")

    # Saturated, distinct hues and a solid COR3M stroke stay visible at crossings.
    risk_colors = {
        "VIX": "#1d4ed8", "VIXEQ": "#00875a", "S&P 500 (R1)": "#374151",
        "VIXEQ/VIX (R2)": "#d97706", "COR3M (R3)": "#c0006f",
    }
    for name, color in risk_colors.items():
        fig.update_traces(line_color=color, selector=dict(name=name))
    move = filter_range(sources.get("MOVE", pd.DataFrame(columns=["observation_date", "MOVE"])), date_range)
    add_line(fig, move, "MOVE", _move_index.SERIES_NAME, 2.3, yaxis="y5", unit=" pts")
    fig.update_traces(line_color="#0e7490", connectgaps=False,
                      selector=dict(name=_move_index.SERIES_NAME))
    ratio_dates = [day for column in ("MOVE", "VIXCLS") if column in sources
                   for day in sources[column]["observation_date"]]
    add_line(fig, data.loc[data.observation_date.isin(ratio_dates)],
             "MOVE/VIX", "MOVE/VIX (R5)", 2.3, "dot", "y6", unit="x")
    fig.update_traces(line_color="#7c3aed", connectgaps=False, selector=dict(name="MOVE/VIX (R5)"))
    spread_dates = [day for column in ("VXNCLS", "VIXCLS") if column in sources
                    for day in sources[column]["observation_date"]]
    add_line(fig, data.loc[data.observation_date.isin(spread_dates)],
             "VXN−VIX", "VXN−VIX (R6)", 2.4, yaxis="y7", unit=" pp")
    fig.update_traces(line_color="#b45309", connectgaps=False, selector=dict(name="VXN−VIX (R6)"))

    fig.update_layout(
        yaxis2=dict(overlaying="y", side="right", anchor="free", position=0.85),
        yaxis3=dict(overlaying="y", side="right", anchor="free", position=0.92),
        yaxis4=dict(overlaying="y", side="right", anchor="free", position=0.99),
    )
    fig = apply_chart_style(fig, chart_height(320, 440), date_range)
    fig.update_layout(
        margin=dict(l=62, r=140, t=100, b=36, pad=2),
        legend=dict(y=1.095),
        xaxis=dict(domain=[0.0, 0.83]),
        yaxis=dict(
            title="VIX / VIXEQ",
            showgrid=True, gridcolor="#e5e7eb", griddash="dot",
            zeroline=False, fixedrange=True,
        ),
        yaxis2=dict(
            title="",
            overlaying="y", side="right", anchor="free", position=0.85,
            showgrid=False, zeroline=False, fixedrange=True, tickfont=dict(size=9), ticks="outside", ticklen=3,
        ),
        yaxis3=dict(
            title="R2 · VIXEQ/VIX (倍)",
            overlaying="y", side="right", anchor="free", position=0.92,
            showgrid=False, zeroline=False, fixedrange=True, tickformat=".2f",
            tickfont=dict(size=9), ticks="outside", ticklen=3,
        ),
        yaxis4=dict(
            title="R3 · COR3M (pts)",
            overlaying="y", side="right", anchor="free", position=0.99,
            showgrid=False, zeroline=False, fixedrange=True, tickformat=".1f",
            tickfont=dict(size=9), ticks="outside", ticklen=3,
        ),
        yaxis5=dict(title="R4 · MOVE · pts", overlaying="y", side="right", anchor="free",
                    position=0.995, showgrid=False, zeroline=False, fixedrange=True),
        yaxis6=dict(title="R5 · MOVE/VIX (倍)", overlaying="y", side="right", anchor="free",
                    position=1, showgrid=False, zeroline=False, fixedrange=True),
        yaxis7=dict(title="R6 · VXN−VIX · pp", overlaying="y", side="right", anchor="free",
                    position=1, showgrid=False, zeroline=True, fixedrange=True),
    )
    fig.update_layout(margin_r=220, xaxis_domain=[0, 0.72])
    return fig


def build_fig10(date_range):
    """SPX implied-volatility ratios and dated SPX option volume sentiment."""
    def daily_mean(frame, column, window):
        # Average actual daily observations before cropping the visible range.
        frame = frame.copy()
        frame["observation_date"] = pd.to_datetime(frame["observation_date"], errors="coerce")
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame = frame.loc[frame[column].ge(0) & frame[column].lt(float("inf"))]
        frame = frame.dropna(subset=["observation_date"]).sort_values("observation_date")
        frame = frame.drop_duplicates("observation_date", keep="last")
        frame[column] = frame[column].rolling(window, min_periods=window).mean()
        return frame

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
    data["VIX/VIX3M"] = data["VIXCLS"] / data["VXVCLS"].where(data["VXVCLS"].gt(0))
    data = filter_range(data, date_range)
    fig = go.Figure()
    for column, name in (("VIXCLS", "VIX"), ("VXVCLS", "VIX3M")):
        add_line(fig, data.loc[data["observation_date"].isin(sources[column]["observation_date"])],
                 column, name, 2.6, unit=" pts")
    add_line(fig, data, "VIX/VIX3M", "VIX/VIX3M (R1)", 2.3, "dash", "y2", " x")
    for name, color in (("VIX", "#5070dd"), ("VIX3M", "#785db0"), ("VIX/VIX3M (R1)", "#ff994d")):
        fig.update_traces(line_color=color, selector=dict(name=name))
    tail_sources = {}
    for symbol, name, axis, color in (("SKEW", "SKEW 5D MA (R2)", "y3", "#b45309"),
                                       ("VVIX", "VVIX (R3)", "y4", "#dc2626")):
        try:
            observed = load_tail_risk_snapshot(symbol)
            if symbol == "SKEW":
                observed = daily_mean(observed, symbol, 5)
            observed = filter_range(observed, date_range)
        except Exception:
            observed = pd.DataFrame(columns=["observation_date", symbol])
        tail_sources[symbol] = observed
        add_line(fig, observed, symbol, name, 2.2, yaxis=axis, unit=" pts")
        fig.update_traces(line_color=color, selector=dict(name=name))
    relative = sources["VIXCLS"].merge(tail_sources["VVIX"], on="observation_date", how="outer").sort_values("observation_date")
    relative["VVIX/VIX"] = relative["VVIX"] / relative["VIXCLS"].where(relative["VIXCLS"].gt(0))
    add_line(fig, filter_range(relative, date_range), "VVIX/VIX", "VVIX/VIX (R4)", 2.2, "dashdot", "y5", " x")
    fig.update_traces(line_color="#be185d", selector=dict(name="VVIX/VIX (R4)"))
    try:
        short = load_tail_risk_snapshot("VIX9D")
    except Exception:
        short = pd.DataFrame(columns=["observation_date", "VIX9D"])
    short = sources["VIXCLS"].merge(short, on="observation_date", how="outer").sort_values("observation_date")
    short["9D/30D"] = short["VIX9D"] / short["VIXCLS"].where(short["VIXCLS"].gt(0))
    add_line(fig, filter_range(short, date_range), "9D/30D", "9D/30D (R1)", 2.2, "dot", "y2", " x")
    fig.update_traces(line_color="#0891b2", selector=dict(name="9D/30D (R1)"))
    try:
        pc = filter_range(daily_mean(load_spx_put_call_snapshot(), "SPX_PCR", 63), date_range)
    except Exception:
        pc = pd.DataFrame(columns=["observation_date", "SPX_PCR"])
    add_line(fig, pc, "SPX_PCR", "SPX P/C 63D MA (R1)", 2.1, yaxis="y2", unit=" x")
    fig.update_traces(line_color="#15803d", selector=dict(name="SPX P/C 63D MA (R1)"))
    gex = filter_range(_dealer_gamma.load_gex_snapshot(), date_range)
    add_line(fig, gex, "GEX_BN", _dealer_gamma.SERIES_NAME, 2.2, yaxis="y6", unit=" 十亿美元")
    fig.update_traces(line_color="#0f766e", connectgaps=False,
                      selector=dict(name=_dealer_gamma.SERIES_NAME))
    fig.update_layout(
        yaxis_title="VIX / VIX3M · pts",
        yaxis2=dict(title="R1 · Ratios · x", overlaying="y", side="right", anchor="free",
                    position=0.65, showgrid=False, zeroline=False, fixedrange=True),
        yaxis3=dict(title="R2 · SKEW · pts", overlaying="y", side="right", anchor="free",
                    position=0.75, showgrid=False, zeroline=False, fixedrange=True),
        yaxis4=dict(title="R3 · VVIX · pts", overlaying="y", side="right", anchor="free",
                    position=0.85, showgrid=False, zeroline=False, fixedrange=True),
        yaxis5=dict(title="R4 · VVIX/VIX · x", overlaying="y", side="right", anchor="free",
                    position=0.94, showgrid=False, zeroline=False, fixedrange=True),
        yaxis6=dict(title="R5 · GEX · 十亿美元", overlaying="y", side="right", anchor="free",
                    position=0.995, showgrid=False, zeroline=True, fixedrange=True),
    )
    fig = apply_chart_style(fig, chart_height(310, 420), date_range)
    # Join observed values for display; source values and ratio dates stay intact.
    fig.update_traces(connectgaps=True, line_dash="solid")
    fig.update_traces(connectgaps=False, selector=dict(name=_dealer_gamma.SERIES_NAME))
    # Fix colors by metric rather than palette order. Similar hues also use
    # different strokes so hiding another curve cannot change their identity.
    for name, color, dash, width in (
        ("VIX", "#2563eb", "solid", 2.6),
        ("VIX3M", "#7c3aed", "dash", 2.6),
        ("VIX/VIX3M (R1)", "#ea580c", "dash", 2.3),
        ("SKEW 5D MA (R2)", "#92400e", "solid", 2.4),
        ("VVIX (R3)", "#dc2626", "solid", 2.2),
        ("VVIX/VIX (R4)", "#be185d", "dashdot", 2.2),
        ("9D/30D (R1)", "#0891b2", "dot", 2.2),
        ("SPX P/C 63D MA (R1)", "#15803d", "solid", 2.4),
        (_dealer_gamma.SERIES_NAME, "#334155", "solid", 2.8),
    ):
        fig.update_traces(line_color=color, line_dash=dash, line_width=width,
                          selector=dict(name=name))
    fig.update_layout(xaxis_domain=[0, 0.60], margin_r=250)
    meta = dict(fig.layout.meta or {})
    meta["preserve_axis_titles"] = list(dict.fromkeys([*meta.get("preserve_axis_titles", []), "y6"]))
    fig.update_layout(meta=meta)
    return fig


@observed_cache()
def get_yahoo_daily_history(symbol):
    """Fetch five years of completed daily closes from Yahoo chart API."""
    best = pd.DataFrame(columns=["observation_date", "close"])
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        try:
            response = http_get(
                f"https://{host}/v8/finance/chart/{quote(symbol, safe='')}",
                params={"range": "5y", "interval": "1d", "includePrePost": "false", "events": "div,splits"},
                headers={"User-Agent": "Mozilla/5.0 (compatible; MacroDashboard/1.0)"},
                timeout=(3.0, 8.0),
            )
            response.raise_for_status()
            result = ((response.json() or {}).get("chart") or {}).get("result") or []
            if len(result) != 1:
                continue
            if symbol == "DX-Y.NYB":
                meta = result[0].get("meta") or {}
                if (meta.get("symbol"), meta.get("instrumentType"), meta.get("dataGranularity")) != (symbol, "INDEX", "1d"):
                    continue
            frame = completed_daily_closes(result[0])
            if not frame.empty and (best.empty or frame.observation_date.max() > best.observation_date.max()):
                best = frame
        except (requests.RequestException, ValueError, KeyError, TypeError):
            continue
    return best


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
    if nikkei.empty:
        # Reuse the same original last-good closes as the relative-strength
        # chart; a Yahoo outage must not erase an already verified Nikkei leg.
        from macro_platform.sp500_nikkei_ratio import _load_snapshot_index
        nikkei = _load_snapshot_index("NIKKEI").rename(columns={"NIKKEI": "close"})
    try:
        yen = load_yen_market_index()
    except Exception:
        yen = pd.DataFrame(columns=["observation_date", "usd_jpy_close"])
    return build_japan_rates_figure(date_range, nikkei=nikkei, yen_index=yen)


def build_fig16(date_range):
    if _yen_carry is None:
        raise RuntimeError("Yen carry chart module unavailable")
    from macro_platform.asia_rates import load_japan_gov_yields
    from macro_platform.cftc_yen import load_cftc_yen
    from macro_platform.topix import load_topix_snapshot
    from macro_platform.japan_short_rates import load_japan_3m
    frames = []
    for loader in (get_dgs10, load_japan_gov_yields, load_yen_market_index, load_cftc_yen, load_topix_snapshot, load_japan_3m):
        try:
            frames.append(loader())
        except Exception:
            frames.append(pd.DataFrame())
    inputs = dict(us=frames[0], japan=frames[1], fx=frames[2], positions=frames[3], topix=frames[4])
    inputs["japan_short"] = frames[5]
    if hasattr(_yen_carry, "DXY_NAME"):
        symbol = _yen_carry.DXY_SYMBOL
        stored = _yen_carry.load_dxy_snapshot()
        live = _load_yahoo_histories((symbol,))[symbol]
        inputs["dxy"] = pd.concat([stored, live], ignore_index=True)
    return _yen_carry.build_yen_carry_figure(date_range, **inputs)


def build_yen_volatility(date_range):
    from macro_platform.boj_policy import load_boj_policy

    return _yen_carry.build_yen_volatility_figure(
        date_range, fx=load_yen_market_index(), policy=load_boj_policy(),
    )


def build_yen_tic(date_range):
    from macro_platform.fred_observations import TIC_JAPAN_SERIES

    return _yen_carry.build_japan_tic_figure(
        date_range, series={sid: get_fred_series(sid) for sid in TIC_JAPAN_SERIES},
    )


def build_japan_holdings(date_range):
    return _yen_carry.combine_japan_holdings_figures(
        build_yen_tic(date_range), date_range=date_range,
        holdings=_yen_carry.build_japan_institution_figure(date_range, metric="holdings"),
        hedging=_yen_carry.build_japan_institution_figure(date_range, metric="hedging"),
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
    """Keep data-quality checks without per-chart observation-date footers."""
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
    renderer = linked if callable(linked) else getattr(st, "echarts_chart", None)
    if not callable(renderer):
        return None

    def render_isolated(option, **kwargs):
        # Recreate either renderer when series/axis structure changes, so old
        # axes and DOM-local selection state cannot survive a chart split.
        import hashlib
        import json
        structure = {
            "series": [(s.get("name"), s.get("type"), s.get("xAxisIndex", 0),
                        s.get("yAxisIndex", 0)) for s in option.get("series", [])],
            "axes": [(a.get("name"), a.get("type"), a.get("position"), a.get("inverse", False))
                     for a in option.get("yAxis", [])],
        }
        token = hashlib.sha256(json.dumps(structure, ensure_ascii=True).encode()).hexdigest()[:12]
        kwargs["key"] = f"{kwargs.get('key') or 'macro_chart'}_schema_{token}"
        return renderer(option, **kwargs)

    return render_isolated


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


def _render_adaptive_macro_figure(base_fig, element_key, mode=None, standard=False, selected_range=None):
    """Use viewport-filtered ECharts for every macro chart, not only US 1-4.

    Plotly's native time selector changes X without recalculating Y after
    arbitrary drag/slider zoom. ECharts filters visible data client-side and
    rescales every independent Y axis when the X viewport changes.
    """
    # Uniform Streamlit buttons work for all 15 charts, regardless of
    # whether ECharts or Plotly is currently the available renderer.
    # Their parent fragments prevent an X/Y viewport change from rerunning
    # the entire dashboard and refetching unrelated market data.
    if selected_range is None:
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
                    height=760 if (base_fig.layout.meta or {}).get("yen_combined") else 465,
                    width="stretch",
                    key=(f"{element_key}_echarts_{selected_range}" if standard else
                         f"{element_key}_adaptive_{mode or 'default'}_{selected_range}"),
                    theme=None,
                )
                if not standard:
                    if reused:
                        st.caption("沿用上次有效数据，更新暂不可用。")
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
    missing_series = list((base_fig.layout.meta or {}).get("missing_series", [])) if isinstance(base_fig.layout.meta, dict) else []
    if missing_series:
        st.warning("以下序列缺少观测数据：" + " · ".join(missing_series))
    if reused:
        st.caption("沿用上次有效数据，更新暂不可用。")
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
        if health.get("stale_names"):
            st.warning("以下序列可能尚未更新：" + "、".join(health["stale_names"]))
        if health.get("future_names"):
            st.warning("以下序列的观测日期超前，请检查源数据：" + "、".join(health["future_names"]))


def _render_standard_macro_chart(title, description, range_key, builder, sources, prebuilt_fig=None):
    st.markdown(title, unsafe_allow_html=True)
    st.markdown(description, unsafe_allow_html=True)
    base_fig = prebuilt_fig if prebuilt_fig is not None else builder("5Y")
    _render_adaptive_macro_figure(base_fig, range_key, standard=True)
    _show_data_quality_notes(base_fig)
    if range_key == "normal_corridor_range":
        st.caption(usage_caption())
    add_sources(sources, range_key)
    st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)


@st.fragment(key="us_macro_chart_1")
def render_macro_chart_1(prebuilt_fig=None):
    _render_standard_macro_chart(
        '<div class="section-title">1. Fed Policy Rate, Money Market & SRF Usage</div>',
        '<div class="section-description">IORB / ON RRP Rate / EFFR / SOFR / SRF Rate · 年化% · SRF 实际用量 (R1) · 十亿美元</div>',
        "normal_corridor_range",
        build_fig1,
        [
            ("IORB (IORB)", "https://fred.stlouisfed.org/series/IORB"),
            ("ON RRP Rate (RRPONTSYAWARD)", "https://fred.stlouisfed.org/series/RRPONTSYAWARD"),
            ("EFFR (EFFR)", "https://fred.stlouisfed.org/series/EFFR"),
            ("SOFR (SOFR)", "https://fred.stlouisfed.org/series/SOFR"),
            ("SRF Rate (SRFTSYD)", "https://fred.stlouisfed.org/series/SRFTSYD"),
            ("NY Fed · SRF actual accepted amounts", "https://www.newyorkfed.org/markets/desk-operations/repo"),
        ],
        prebuilt_fig=prebuilt_fig,
    )


@st.fragment(key="us_macro_chart_2")
def render_macro_chart_2(prebuilt_fig=None):
    _render_standard_macro_chart(
        f'<div class="section-title">{MACRO_DISPLAY_NUMBER[2]}. US Treasury Yield Structure · 10Y</div>',
        '<div class="section-description">10年期名义收益率（DGS10） / 10年期实际收益率（TIPS · DFII10，右轴） / 10年期盈亏平衡通胀率（BEI · T10YIE，右轴）</div>',
        "normal_yield10_range",
        build_fig2,
        [
            ("10年期名义收益率（DGS10）", "https://fred.stlouisfed.org/series/DGS10"),
            ("10年期实际收益率（TIPS · DFII10）", "https://fred.stlouisfed.org/series/DFII10"),
            ("10年期盈亏平衡通胀率（BEI · T10YIE）", "https://fred.stlouisfed.org/series/T10YIE"),
        ],
        prebuilt_fig=prebuilt_fig,
    )


@st.fragment(key="us_macro_chart_3")
def render_macro_chart_3(prebuilt_fig=None):
    _render_standard_macro_chart(
        f'<div class="section-title">{MACRO_DISPLAY_NUMBER[3]}. Treasury Yield & Curve Spread</div>',
        '<div class="section-description">3M / 2Y / 10Y / 30Y / 10Y−2Y (R1) / 30Y−10Y (R1) / NASDAQ-100 (R2)</div>',
        "normal_treasury_range",
        build_fig3,
        [
            ("3M Treasury (DGS3MO)", "https://fred.stlouisfed.org/series/DGS3MO"),
            ("2Y Treasury (DGS2)", "https://fred.stlouisfed.org/series/DGS2"),
            ("10年期名义收益率（DGS10）", "https://fred.stlouisfed.org/series/DGS10"),
            ("30Y Treasury (DGS30)", "https://fred.stlouisfed.org/series/DGS30"),
            ("NASDAQ-100 (^NDX)", "https://finance.yahoo.com/quote/%5ENDX/history/"),
        ],
        prebuilt_fig=prebuilt_fig,
    )


@st.fragment(key="us_macro_chart_4")
def render_macro_chart_4(prebuilt_fig=None):
    st.markdown(
        f'<div class="section-title">{MACRO_DISPLAY_NUMBER[4]}. 标普500 / 日经225（Nikkei 225）相对强弱</div>'
        '<div class="section-description">标普500（美国）÷ 日经225（日本）· 左轴：比值 · 右轴R1：标普点位 · 右轴R2：日经点位</div>',
        unsafe_allow_html=True,
    )
    base_fig = prebuilt_fig if prebuilt_fig is not None else _safe_macro_build(
        "Chart 4", build_sp500_nikkei_ratio_figure,
    )
    _render_adaptive_macro_figure(base_fig, "sp500_nikkei_ratio")
    add_sources([
        ("Yahoo Finance · S&P 500 (^GSPC)", "https://finance.yahoo.com/quote/%5EGSPC/history/"),
        ("Yahoo Finance · Nikkei 225 (^N225)", "https://finance.yahoo.com/quote/%5EN225/history/"),
        ("日经指数官方 · 日经225定义", "https://indexes.nikkei.co.jp/en/nkave/index/profile?idx=nk225"),
    ], "sp500_nikkei_ratio")
    st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)


HK_EQUITY_SOURCES = [
    ("Yahoo Finance · 腾讯 (0700.HK)", "https://hk.finance.yahoo.com/quote/0700.HK/history/"),
    ("Yahoo Finance · 港交所 (0388.HK)", "https://hk.finance.yahoo.com/quote/0388.HK/history/"),
    ("恒生指数公司 · 恒生科技指数", "https://www.hsi.com.hk/eng/indexes/all-indexes/hstech"),
    ("恒生指数公司 · 恒生指数", "https://www.hsi.com.hk/eng/indexes/all-indexes/hsi"),
]


HK_CHART_CONFIGS = [
    (
        f'<div class="section-title">{MACRO_DISPLAY_NUMBER[5]}. HK Money Supply & Market Pulse</div>',
        '<div class="section-description">M2 YoY / M2 MoM / Monetary Base YoY · Tencent / HKEX (R1) · HSTECH / HSI (R2)</div>',
        "hk_5_range",
        [
            ("HKMA Monetary Statistics", "https://apidocs.hkma.gov.hk/documentation/market-data-and-statistics/monthly-statistical-bulletin/financial/monetary-statistics/"),
            ("HKMA Monetary Base", "https://apidocs.hkma.gov.hk/documentation/market-data-and-statistics/monthly-statistical-bulletin/monetary-operation/monetary-base-endperiod/"),
            *HK_EQUITY_SOURCES,
        ],
    ),
    (
        f'<div class="section-title">{MACRO_DISPLAY_NUMBER[6]}. Banking-system Liquidity</div>',
        '<div class="section-description">Aggregate Balance · Outstanding EFBN (R1) · EFBN Held by Licensed Banks (R1)</div>',
        "hk_6_range",
        [
            ("HKMA Monetary Base", "https://apidocs.hkma.gov.hk/documentation/market-data-and-statistics/monthly-statistical-bulletin/monetary-operation/monetary-base-endperiod/"),
            ("HKMA Daily Interbank Liquidity", "https://apidocs.hkma.gov.hk/documentation/market-data-and-statistics/daily-monetary-statistics/daily-figures-interbank-liquidity/"),
        ],
    ),
    (
        f'<div class="section-title">{MACRO_DISPLAY_NUMBER[7]}. HKD Funding</div>',
        '<div class="section-description">O/N HIBOR · 3M HIBOR · HKMA Base Rate · O/N−3M Spread (R1)</div>',
        "hk_7_range",
        [
            ("HKMA · HIBOR 日线", "https://apidocs.hkma.gov.hk/documentation/market-data-and-statistics/monthly-statistical-bulletin/er-ir/hk-interbank-ir-daily/"),
            ("HKAB 当日 HIBOR 定盘", "https://www.hkab.org.hk/en/home"),
            ("HKMA Base Rate", "https://apidocs.hkma.gov.hk/documentation/market-data-and-statistics/monthly-statistical-bulletin/monetary-operation/disc-win-liquid-adj-win-rates-endperiod/"),
        ],
    ),
    (
        f'<div class="section-title">{MACRO_DISPLAY_NUMBER[8]}. USD/HKD Convertibility Band & Market</div>',
        '<div class="section-description">USD/HKD · Strong-side 7.75 · Center 7.80 · Weak-side 7.85 · Tencent / HKEX (R1) · HSTECH / HSI (R2)</div>',
        "hk_8_range",
        [
            ("HKMA Linked Exchange Rate System", "https://www.hkma.gov.hk/eng/key-functions/money/linked-exchange-rate-system/"),
            ("Yahoo Finance · USD/HKD 日线", "https://finance.yahoo.com/quote/HKD%3DX/history/"),
            *HK_EQUITY_SOURCES,
        ],
    ),
]


def _render_hk_macro_chart(hk_index, prebuilt_fig=None):
    title, description, range_key, sources = HK_CHART_CONFIGS[hk_index]
    st.markdown(title, unsafe_allow_html=True)
    st.markdown(description, unsafe_allow_html=True)
    fig = prebuilt_fig if prebuilt_fig is not None else _safe_hk_bundle(_macro_snapshot_revision())[hk_index]
    _render_adaptive_macro_figure(fig, range_key)
    add_sources(sources, range_key)
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
    st.markdown(f'<div class="section-title">{MACRO_DISPLAY_NUMBER["us_drawdown"]}. SPX / RSP · 价格走势与区间高点</div>', unsafe_allow_html=True)
    figure = _build_equity_drawdown()
    _render_adaptive_macro_figure(figure, "us_equity_drawdown", standard=True)
    summaries = (figure.layout.meta or {}).get("price_summary", [])
    for row in summaries:
        st.caption(f'{row["symbol"]} 最新收盘：{row["close"]:,.2f}（{row["date"]}）')
    add_sources([
        ("SPX 日线价格", "https://finance.yahoo.com/quote/%5EGSPC/history/"),
        ("RSP 日线价格", "https://finance.yahoo.com/quote/RSP/history/"),
        ("Invesco RSP", "https://www.invesco.com/us/financial-products/etfs/product-detail?productId=RSP"),
    ], "us_equity_drawdown")
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
    st.markdown(f'<div class="section-title">{MACRO_DISPLAY_NUMBER["cn_drawdown"]}. A股宽基 · 沪深300 / 中证1000 / 中证2000 价格走势</div>', unsafe_allow_html=True)
    figure = _build_china_drawdown()
    _render_adaptive_macro_figure(figure, "china_equity_drawdown", standard=True)
    for row in (figure.layout.meta or {}).get("price_summary", []):
        st.caption(f'{row["name"]}（{row["symbol"]}）最新收盘：{row["close"]:,.2f}（{row["date"]}）')
    add_sources([(name, f"https://www.csindex.com.cn/zh-CN/indices/index-detail/{code}")
                 for code, name in (("000300", "沪深300"), ("000852", "中证1000"), ("932000", "中证2000"))], "china_equity_drawdown")
    st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)


@st.fragment(key="macro_chart_9_viewport")
def render_macro_chart_9(prebuilt_fig=None):
    st.markdown(
        f'<div class="section-title">{MACRO_DISPLAY_NUMBER[9]}. US Equity Risk & Volatility Structure</div>'
        '<div class="section-description">VIX · VIXEQ · S&P 500 (R1) · VIXEQ/VIX (R2) · COR3M (R3) · MOVE 债市波动率 (R4) · MOVE/VIX (R5) · VXN−VIX（R6 · 波动率差，pp）</div>',
        unsafe_allow_html=True,
    )
    render_latest_vix_quote()
    base_fig = prebuilt_fig if prebuilt_fig is not None else build_fig9("5Y")
    _render_adaptive_macro_figure(base_fig, "us_equity_risk")
    observed_dates = []
    for trace in base_fig.data:
        valid_dates = [pd.Timestamp(day) for day, value in zip(trace.x, trace.y)
                       if pd.notna(value) and pd.notna(day)]
        if valid_dates:
            observed_dates.append(f"{trace.name}：{max(valid_dates):%Y-%m-%d}")
    if observed_dates:
        st.caption("日线实际观测日 · " + " · ".join(observed_dates))
    add_sources([
        ("Cboe VIX", "https://www.cboe.com/tradable-products/vix/"),
        ("Cboe VXN · 纳斯达克100隐含波动率", "https://cdn.cboe.com/api/global/us_indices/daily_prices/VXN_History.csv"),
        ("ICE · MOVE指数说明", _move_index.METHOD_URL),
        ("Yahoo · MOVE日度收盘", _move_index.SOURCE_URL),
        ("Cboe VIXEQ / Dispersion", "https://www.cboe.com/us/indices/dispersion/"),
        ("Cboe COR3M", "https://www.cboe.com/us/indices/implied/"),
        ("FRED S&P 500 (SP500)", "https://fred.stlouisfed.org/series/SP500"),
    ], "us_equity_risk")
    st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)


@st.fragment(key="vix_term_structure_chart")
def render_macro_chart_10(prebuilt_fig=None):
    st.markdown(
        f'<div class="section-title">{MACRO_DISPLAY_NUMBER[10]}. VIX & VIX3M Term Structure</div>'
        '<div class="section-description">VIX（30天≈1M） · VIX3M（约3M） · VIX/VIX3M · 9D/30D · SPX P/C 63日均（共用 R1） · SKEW 5日均 (R2) · VVIX (R3) · VVIX/VIX (R4) · GEX 做市商伽马（十亿美元，R5）</div>',
        unsafe_allow_html=True,
    )
    base_fig = prebuilt_fig if prebuilt_fig is not None else _safe_macro_build(
        "Chart 10", lambda: _cached_macro_figure(10, _macro_snapshot_revision(), CHART_BUILD),
    )
    _render_adaptive_macro_figure(base_fig, "vix_term_structure")
    st.caption("GEX为SqueezeMetrics发布的SPX做市商伽马模型估计，按原始美元值÷10亿显示。"
               "来源口径对应SPX每变动1点的对冲敞口变化；日期为交易日，日度自动更新。")
    add_sources([
        ("SqueezeMetrics · SPX GEX daily history", _dealer_gamma.SOURCE_URL),
        ("FRED · VIX (VIXCLS)", "https://fred.stlouisfed.org/series/VIXCLS"),
        ("FRED · VIX3M (VXVCLS)", "https://fred.stlouisfed.org/series/VXVCLS"),
        ("Cboe · SKEW Official Daily History", "https://cdn-api.cboe.com/api/global/us_indices/daily_prices/SKEW_History.csv"),
        ("Cboe · VVIX Official Daily History", "https://cdn-api.cboe.com/api/global/us_indices/daily_prices/VVIX_History.csv"),
        ("Cboe · VIX9D Official Daily History", "https://cdn-api.cboe.com/api/global/us_indices/daily_prices/VIX9D_History.csv"),
        ("Cboe · SPX + SPXW Volume Put/Call", "https://www.cboe.com/markets/us/options/market-statistics/daily"),
    ], "vix_term_structure")
    st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)


@st.fragment(key="precious_metals_chart")
def render_macro_chart_11(prebuilt_fig=None):
    st.markdown(
        f'<div class="section-title">{MACRO_DISPLAY_NUMBER[11]}. Precious Metals</div>'
        '<div class="section-description">Gold · Silver · Gold/Silver Ratio · Gold Volatility GVZ</div>',
        unsafe_allow_html=True,
    )
    base_fig = prebuilt_fig if prebuilt_fig is not None else _safe_macro_build(
        "Chart 11", lambda: _cached_macro_figure(11, _macro_snapshot_revision(), CHART_BUILD),
    )
    _render_adaptive_macro_figure(base_fig, "precious_metals")
    add_sources([
        ("Yahoo Finance · Gold Futures GC=F", "https://finance.yahoo.com/quote/GC=F/history/"),
        ("Yahoo Finance · Silver Futures SI=F", "https://finance.yahoo.com/quote/SI=F/history/"),
        ("FRED · Cboe Gold ETF Volatility Index (GVZCLS)", "https://fred.stlouisfed.org/series/GVZCLS"),
        ("Cboe · Gold Volatility", "https://www.cboe.com/tradable_products/vix/vix_historical_data/"),
    ], "precious_metals")
    st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)


@st.fragment(key="crypto_chart")
def render_macro_chart_12(prebuilt_fig=None):
    st.markdown(
        f'<div class="section-title">{MACRO_DISPLAY_NUMBER[12]}. Crypto Market</div>'
        '<div class="section-description">BTC · ETH · ETH/BTC · BTC 30D 实际波动率</div>',
        unsafe_allow_html=True,
    )
    base_fig = prebuilt_fig if prebuilt_fig is not None else _safe_macro_build(
        "Chart 12", lambda: _cached_macro_figure(12, _macro_snapshot_revision(), CHART_BUILD),
    )
    _render_adaptive_macro_figure(base_fig, "crypto_market")
    add_sources([
        ("Yahoo Finance · Bitcoin BTC-USD", "https://finance.yahoo.com/quote/BTC-USD/history/"),
        ("Yahoo Finance · Ethereum ETH-USD", "https://finance.yahoo.com/quote/ETH-USD/history/"),
    ], "crypto_market")
    st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)


@st.fragment(key="macro_chart_13_viewport")
def render_macro_chart_13(prebuilt_fig=None):
    st.markdown(
        f'<div class="section-title">{MACRO_DISPLAY_NUMBER[13]}. Copper Flow & WTI</div>'
        '<div class="section-description">COMEX inventory · LME inventory · LME 3M (R1) · COMEX HG converted (R1) · COMEX−LME 3M spread (R2) · WTI (R3) · 铜油比 (R4)</div>',
        unsafe_allow_html=True,
    )
    base_fig = prebuilt_fig if prebuilt_fig is not None else build_fig13("5Y")
    _render_adaptive_macro_figure(base_fig, "copper_flow")
    add_sources([
        ("CME · COMEX Warehouse & Depository Stocks", "https://www.cmegroup.com/solutions/clearing/operations-and-deliveries/nymex-delivery-notices.html"),
        ("CME · Copper Stocks 原始日报", "https://www.cmegroup.com/delivery_reports/Copper_Stocks.xls"),
        ("Yahoo Finance · COMEX Copper HG=F", "https://finance.yahoo.com/quote/HG=F/history/"),
        ("Yahoo Finance · WTI Crude Oil CL=F", "https://finance.yahoo.com/quote/CL=F/history/"),
        ("LME Copper", "https://www.lme.com/copper"),
        ("LME Warehouse & Stocks Reports", "https://www.lme.com/Market-data/Reports-and-data/Warehouse-and-stocks-reports"),
        ("Westmetall · LME Copper Daily Table", "https://www.westmetall.com/en/markdaten.php?action=table&field=LME_Cu_cash"),
        ("COCHILCO · Copper Inventories", "https://boletin.cochilco.cl/estadisticas/inventarios.asp"),
    ], "copper_flow")
    st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)


@st.fragment(key="copper_tcrc_viewport")
def render_copper_tcrc():
    st.markdown(
        f'<div class="section-title">{MACRO_DISPLAY_NUMBER["copper_tcrc"]}. Copper TC/RC · 铜精矿加工费</div>'
        '<div class="section-description">TC（粗炼费，美元/干吨） · RC（精炼费，TC÷10，美分/磅，右轴）</div>',
        unsafe_allow_html=True,
    )
    figure = _safe_macro_build("TC/RC", lambda: build_copper_tcrc_figure("5Y"))
    _render_adaptive_macro_figure(figure, "copper_tcrc")
    add_sources([
        ("Mysteel · 铜精矿TC/RC指数方法论", COPPER_TCRC_METHOD_URL),
        ("Mysteel · 2026-10-30现货TC指数原始发布", "https://youse.mysteel.com/a/26110208/7DCD2C67E671022B.html"),
    ], "copper_tcrc")
    st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)


@st.fragment(key="macro_chart_14_viewport")
def render_macro_chart_14(prebuilt_fig=None):
    st.markdown(
        f'<div class="section-title">{MACRO_DISPLAY_NUMBER[14]}. China Government Yields & US 5Y Real Yield</div>'
        '<div class="section-description">China 2Y / 10Y · US 5Y Real · TIPS · China 10Y−2Y (R1)</div>',
        unsafe_allow_html=True,
    )
    base_fig = prebuilt_fig if prebuilt_fig is not None else _safe_macro_build(
        "Chart 14", lambda: _cached_macro_figure(14, _macro_snapshot_revision(), CHART_BUILD))
    _render_adaptive_macro_figure(base_fig, "china_rates")
    add_sources([
        ("Eastmoney · China Treasury Yield History", "https://data.eastmoney.com/cjsj/zmgzsyl.html"),
        ("FRED · US 5Y TIPS Real Yield (DFII5)", "https://fred.stlouisfed.org/series/DFII5"),
    ], "china_rates")
    st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)


@st.fragment(key="macro_chart_15_viewport")
def render_macro_chart_15(prebuilt_fig=None):
    st.markdown(
        f'<div class="section-title">{MACRO_DISPLAY_NUMBER[15]}. Japan Government Yields & Nikkei 225 & USD/JPY</div>'
        '<div class="section-description">Japan 2Y / 10Y / 30Y · Japan 10Y−2Y / 30Y−10Y (R1) · Nikkei 225 (R2) · USD/JPY (R3)</div>',
        unsafe_allow_html=True,
    )
    base_fig = prebuilt_fig if prebuilt_fig is not None else _safe_macro_build(
        "Chart 15", lambda: _cached_macro_figure(15, _macro_snapshot_revision(), CHART_BUILD))
    _render_adaptive_macro_figure(base_fig, "japan_rates")
    add_sources([
        ("Japan MOF · JGB Interest Rates", "https://www.mof.go.jp/jgbs/reference/interest_rate/index.htm"),
        ("Yahoo Finance · Nikkei 225", "https://finance.yahoo.com/quote/%5EN225/history/"),
        ("Yahoo · USD/JPY daily closes", "https://finance.yahoo.com/quote/JPY%3DX/history/"),
    ], "japan_rates")
    st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)


@st.fragment(key="yen_carry_viewport")
def render_macro_chart_16(prebuilt_fig=None):
    st.markdown(
        f'<div class="section-title">{MACRO_DISPLAY_NUMBER[16]}. 日元套息分析 · Yen Carry Trade</div>'
        '<div class="section-description">美日10Y利差 · USD/JPY（R1 阳轴，向上＝日元走弱） · '
        'CFTC日元投机净仓位 (R2) · TOPIX（东证指数，R3） · 美元指数 DXY (R4) · '
        'JPY 3M · JPY 10Y · JPY 10Y - JPY 3M · USD/JPY 3M ATM 隐含波动率（Saxo，R5）</div>',
        unsafe_allow_html=True,
    )
    base_fig = prebuilt_fig if prebuilt_fig is not None else _safe_macro_build(
        "Chart 10", lambda: _cached_macro_figure(16, _macro_snapshot_revision(), CHART_BUILD))
    volatility = _safe_macro_build("yen_volatility", lambda: _cached_macro_figure(
        "yen_volatility", _macro_snapshot_revision(), CHART_BUILD))
    implied = _safe_macro_build("JPY 3M ATM", lambda: _cached_macro_figure(
        "yen_implied", _macro_snapshot_revision(), CHART_BUILD))
    combined = _yen_carry.combine_yen_carry_figures(base_fig, volatility=volatility, implied=implied)
    _render_adaptive_macro_figure(combined, "yen_carry")
    st.caption("全部曲线共用时间轴，可点击图例隐藏或显示。JPY 3M 为财务省周度拍卖收益率，"
               "10Y−3M 只按同日观测计算。BOJ利率按生效日阶梯显示。"
               "收益率为%，利差为百分点；美债持仓、机构外债及对冲率另见图12。")
    iv_rows = _jpy_iv.load_snapshot().get("records", [])
    if iv_rows:
        st.caption(f"3个月ATM隐含波动率（Saxo）：{iv_rows[-1]['value']:.2f}% · "
                   f"报价时间 {iv_rows[-1]['observation_timestamp']}。"
                   "来源为Saxo银行，非彭博原序列；历史从已核实报价起逐日累计，不补造历史。")
    add_sources([
        ("Saxo Bank · USDJPY 3M ATM implied volatility", _jpy_iv.SOURCE_URL),
        ("FRED · US 10Y Treasury (DGS10)", "https://fred.stlouisfed.org/series/DGS10"),
        ("CFTC · Commitments of Traders", "https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm"),
        ("Japan MOF · JGB Interest Rates", "https://www.mof.go.jp/jgbs/reference/interest_rate/index.htm"),
        ("Japan MOF · 3M Treasury Bill Auction History", "https://www.mof.go.jp/jgbs/reference/appendix/index.htm"),
        ("Yahoo · USD/JPY daily closes", "https://finance.yahoo.com/quote/JPY%3DX/history/"),
        ("Yahoo! Japan · TOPIX 日收盘", "https://finance.yahoo.co.jp/quote/998405.T/history"),
        ("JPX · TOPIX 指数说明", "https://www.jpx.co.jp/markets/indices/topix/index.html"),
        ("Yahoo Finance · DXY 日收盘", "https://finance.yahoo.com/quote/DX-Y.NYB/history/"),
        ("BIS · 日本政策利率 D.JP", "https://data.bis.org/topics/CBPOL/BIS,WS_CBPOL,1.0/D.JP"),
        ("BOJ · 2026 年 10 月政策声明", "https://www.boj.or.jp/en/mopo/mpmdeci/mpr_2026/k261030a.pdf"),
    ], "yen_carry")
    st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)


@st.fragment(key="japan_holdings_viewport")
def render_japan_holdings():
    st.markdown(f'<div class="section-title">{MACRO_DISPLAY_NUMBER["japan_holdings"]}. 日本美债持仓与机构外债 · Japan Holdings & Hedging</div>'
                '<div class="section-description">日本美债总持仓 / 长期 / 短期 · 长期净买入与估值变动 (R1) · '
                'GPIF与寿险外债 (R2) · 汇率对冲率 (R3)</div>', unsafe_allow_html=True)
    figure = _safe_macro_build("Japan holdings", lambda: _cached_macro_figure(
        "japan_holdings", _macro_snapshot_revision(), CHART_BUILD))
    _render_adaptive_macro_figure(figure, "japan_holdings")
    st.caption("TIC为月末持仓及当月变动，单位十亿美元；GPIF与寿险外债为万亿日元，"
               "对冲率为%。不同统计口径分别显示，仅使用实际观测或披露日期，不插值补齐。")
    st.markdown(
        "#### 日本寿险与养老金 · 机构披露\n\n"
        "| 样本与日期 | 美债持仓 | 外债规模与汇率对冲 |\n"
        "| --- | --- | --- |\n"
        "| 日本九家主要寿险 · 2026-03-31 | 样本美债总额未单列 | 外债约 67 万亿日元，"
        "其中约 43% 对冲。日本央行按一般账户估算，涵盖多个币种。 |\n"
        "| 日本公共养老金 GPIF · 2026-03-31 | 36.84 万亿日元 | 按 GPIF 逐券表加总 297 只美国国债票据和长期债券。"
        "美债专属对冲率未披露。 |\n"
        "| 日本邮政保险 · 2026-06-30 | 美债金额未单列 | 收益型资产外债 4.34 万亿日元。"
        "其中单列的 1.5 万亿日元外币债券约 80% 对冲，按披露的约数计算。 |"
    )
    st.caption("TIC、寿险外债和 GPIF 的逐券披露各有统计口径。GPIF 在资产配置表中将日元对冲外债归入国内债券。")
    add_sources([
        ("美国财政部 · TIC Table 5", "https://ticdata.treasury.gov/Publish/slt_table5.html"),
        ("FRED · 日本美债 TIC/CSLT", "https://fred.stlouisfed.org/series/FORTREASPOS42609"),
        ("日本央行 · 寿险外债与对冲（图 III-2-5）", "https://www.boj.or.jp/en/research/brp/fsr/data/fsr261023a.pdf#page=29"),
        ("GPIF · FY2025 年报与逐券表", "https://www.gpif.go.jp/en/performance/last-years-results.html"),
        ("GPIF · 历年逐券披露", "https://www.gpif.go.jp/en/performance/past-performances.html"),
        ("日本邮政保险 · 2026 年 6 月财报", "https://www.jp-life.japanpost.jp/english/news/assets/pdf/2026/pr0807en-01.pdf#page=32"),
    ], "japan_holdings")
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
    if isinstance(chart_number, str):
        builders = {
            'yen_volatility': build_yen_volatility,
            'yen_implied': _jpy_iv.build_figure,
            'japan_holdings': build_japan_holdings,
        }
        builder = builders[chart_number]
    elif chart_number != 4:
        builder = globals()[f"build_fig{chart_number}"]
    if chart_number == 4:
        try:
            builder = build_sp500_nikkei_ratio_figure
        except NameError:
            # Keep isolated helper tests and older import-compatible callers
            # able to resolve the new chart without eagerly evaluating it for
            # unrelated chart numbers.
            from macro_platform.sp500_nikkei_ratio import build_sp500_nikkei_ratio_figure as builder
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

    jobs = {}
    for number in NUMERIC_CHART_IDS:
        if number == HK_CHART_IDS[0]:
            jobs['hk5'] = lambda: _safe_hk_bundle(snapshot_revision)
        elif number not in HK_CHART_IDS:
            jobs[number] = lambda number=number: cached_chart(number)
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
                for number in HK_CHART_IDS:
                    on_complete(number, value[number - HK_CHART_IDS[0]]); published.add(number)
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
        for number in NUMERIC_CHART_IDS:
            if number not in published:
                if number in HK_CHART_IDS:
                    value = results["hk5"][number-HK_CHART_IDS[0]]
                else:
                    value = results[number]
                on_complete(number, value)

    return {number: (results['hk5'][number-HK_CHART_IDS[0]]
                     if number in HK_CHART_IDS else results[number])
            for number in NUMERIC_CHART_IDS}


@st.fragment(run_every=60, key="japan_corridor_viewport")
def render_japan_corridor():
    st.markdown(f'<div class="section-title">{MACRO_DISPLAY_NUMBER["japan_corridor"]}. 日本利率走廊 · 隔夜资金监控</div>'
                '<div class="section-description">补充存款利率（下沿参考） / 基本贷款利率（上沿参考） / TONA / Tokyo Repo 隔夜T+0 · 年化%</div>', unsafe_allow_html=True)
    figure = _japan_corridor.build_corridor_figure("5Y")
    _render_adaptive_macro_figure(figure, "japan_corridor")
    rows = _japan_corridor.latest_rows()
    st.caption(" · ".join(f"{r['指标']}：{r['最新值（%）']:.3f}%（{r['数据日期']}，{r['状态']}）"
                        for r in rows if r['最新值（%）'] is not None))
    add_sources([
        ("BOJ · 官方利率与生效日", "https://www.boj.or.jp/en/"),
        ("BOJ · TONA每日速報与确报", "https://www.boj.or.jp/en/statistics/market/short/mutan/index.htm"),
        ("JSDA · Tokyo Repo Rate", "https://www.jsda.or.jp/en/statistics/bonds/trr/"),
    ], "japan_corridor")
    st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)


@st.fragment(run_every=60, key="nvidia_cds_viewport")
def render_nvidia_cds():
    st.markdown(f'<div class="section-title">{MACRO_DISPLAY_NUMBER["nvidia_cds"]}. AI Credit · 公司CDS信用风险</div>'
                '<div class="section-description">英伟达 NVIDIA · AMD · 谷歌 Alphabet · 微软 Microsoft · 甲骨文 Oracle · 5Y CDS（bp） / HY OAS · IG OAS（R1 · %）</div>', unsafe_allow_html=True)
    payload = _ai_credit.load_cds_snapshot()
    hy_oas = get_hy_oas()
    ig_oas = get_ig_oas()
    figure = _ai_credit.build_cds_figure("5Y", payload=payload, hy_oas=hy_oas, ig_oas=ig_oas)
    _render_adaptive_macro_figure(figure, "nvidia_cds")
    if not figure.data:
        st.info("暂未取得可绘制的CDS观测，请查看数据源更新状态。")
    if hy_oas.empty:
        st.caption("HY OAS（R1）暂未取得 FRED 观测，稍后自动重试。")
    else:
        latest_oas = hy_oas.iloc[-1]
        status = " · 最近一次成功获取的观测" if hy_oas.attrs.get("is_stale") else ""
        st.caption(f"HY OAS（R1）{latest_oas.oas_pct:.2f}% · "
                   f"实际观测日 {latest_oas.observation_date:%Y-%m-%d}{status}")
    summary = _ai_credit.cds_summary(payload)
    if ig_oas.empty:
        st.caption("IG OAS（R1）暂未取得 FRED 观测，稍后自动重试。")
    else:
        latest_ig = ig_oas.iloc[-1]
        status = " · 最近一次成功获取的观测" if ig_oas.attrs.get("is_stale") else ""
        st.caption(f"IG OAS（R1）{latest_ig.oas_pct:.2f}% · 实际观测日 {latest_ig.observation_date:%Y-%m-%d}{status}")
    st.dataframe(summary, hide_index=True, width="stretch",
                 column_config={"最新CDS（bp）": st.column_config.NumberColumn(format="%.2f"),
                                "源日历覆盖率（%）": st.column_config.NumberColumn(format="%.1f%%")})
    add_sources([
        ("Open-Sourced Rates Observatory · CDS 历史数据", _ai_credit.SOURCE_URL),
        ("CDS 统计方法", _ai_credit.METHOD_URL),
        ("ICE Data Indices via FRED · HY OAS (BAMLH0A0HYM2)", _ai_credit.HY_OAS_URL),
        ("ICE Data Indices via FRED · IG OAS (BAMLC0A0CM)", _ai_credit.IG_OAS_URL),
    ], "nvidia_cds")
    st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)


st.markdown(
    '<div id="macro-charts" class="section-anchor"></div>'
    '<div class="section-kicker">MACRO CHARTS</div>'
    '<div class="section-title">US monetary policy, Treasury yields and inflation expectations</div>',
    unsafe_allow_html=True,
)

# Reserve the existing document order, then fill sections as workers finish.
# Only the main Streamlit thread creates containers, fragments and widgets.
macro_slots = {}
section_headers = {9: "US EQUITY RISK", "nvidia_cds": "US CREDIT RISK", 4: "US / JAPAN RELATIVE STRENGTH",
                   "japan_corridor": "JAPAN RATES & YEN", 14: "CHINA RATES & EQUITIES",
                   5: "HONG KONG LIQUIDITY", 11: "COMMODITIES", 12: "CRYPTO MARKET"}
for number in MACRO_DISPLAY_ORDER:
    if number in section_headers:
        st.markdown(f'<div class="section-kicker">{section_headers[number]}</div>', unsafe_allow_html=True)
    if number == "us_drawdown":
        _render_equity_drawdown()
    elif number == "cn_drawdown":
        _render_china_drawdown()
    elif number == "copper_tcrc":
        render_copper_tcrc()
    elif number == "nvidia_cds":
        render_nvidia_cds()
    elif number == "japan_holdings":
        render_japan_holdings()
    elif number == "japan_corridor":
        render_japan_corridor()
    else:
        macro_slots[number] = st.container()


def _render_completed_macro_chart(number, figure):
    with macro_slots[number]:
        globals()[f"render_macro_chart_{number}"](figure)


_auxiliary = {}
if not st.session_state.get("_market_quotes_snapshot") or time.time()-st.session_state.get("_market_quotes_snapshot_time", 0) >= 60:
    _market_key = (_quote_refresh_key(), st.session_state.get("_market_refresh_key", 0))
    _auxiliary["market"] = lambda: _fetch_quote_rows(MARKET_SYMBOLS.values(), _market_key)
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


for _section in ("market",):
    if _section not in _auxiliary:
        _publish_quote_section(_section)
with st.spinner("正在加载图表…"):
    macro_figures = _build_macro_figures_parallel(
        on_complete=_render_completed_macro_chart, auxiliary_jobs=_auxiliary,
        on_aux_complete=_publish_quote_section)
for _section in ("market",):
    _publish_quote_section(_section)


# Poll only completion/revision metadata; source fetching stays in bounded workers.
# An app rerun is needed to replace timed-out fragment arguments with ready data.
st.session_state["_source_watch_revision"] = _macro_snapshot_revision()
st.session_state["_source_watch_until"] = time.monotonic() + 120


def _publish_late_dashboard_result(key, value):
    """Commit delayed observations on the UI thread, retaining newer quotes."""
    if key == "watchlist":
        return False
    if key != "market":
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
    display_figures = {MACRO_DISPLAY_NUMBER[number]: figure
                       for number, figure in figures.items()}
    display_figures[MACRO_DISPLAY_NUMBER[16]] = _yen_carry.combine_yen_carry_figures(
        figures[16], volatility=_safe_macro_build("yen_volatility", lambda: _cached_macro_figure(
            "yen_volatility", _macro_snapshot_revision(), CHART_BUILD)),
        implied=_safe_macro_build("JPY 3M ATM", lambda: _cached_macro_figure(
            "yen_implied", _macro_snapshot_revision(), CHART_BUILD)))
    display_figures[MACRO_DISPLAY_NUMBER["japan_holdings"]] = _safe_macro_build(
        "Japan holdings", lambda: _cached_macro_figure("japan_holdings", _macro_snapshot_revision(), CHART_BUILD))
    display_figures[MACRO_DISPLAY_NUMBER["japan_corridor"]] = _japan_corridor.build_corridor_figure("5Y")
    display_figures[MACRO_DISPLAY_NUMBER["us_drawdown"]] = _build_equity_drawdown()
    display_figures[MACRO_DISPLAY_NUMBER["cn_drawdown"]] = _build_china_drawdown()
    display_figures[MACRO_DISPLAY_NUMBER["copper_tcrc"]] = build_copper_tcrc_figure("5Y")
    display_figures[MACRO_DISPLAY_NUMBER["nvidia_cds"]] = _ai_credit.build_cds_figure("5Y", hy_oas=get_hy_oas(), ig_oas=get_ig_oas())
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
