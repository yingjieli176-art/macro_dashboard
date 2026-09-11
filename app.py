import html
import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import streamlit as st
from macro_platform.hk_liquidity import build_hk_liquidity_figure, build_hk_liquidity_figures, load_hk_liquidity
from macro_platform.chart_axes import apply_time_axis
from macro_platform.us_equity_risk import load_vixeq_snapshot
from macro_platform.watchlist_state import WATCHLIST_KEYS, decode_watchlists, encode_watchlists, merge_default_watchlists, watchlist_needs_default_migration
from data import (get_dgs3mo, get_dgs2, get_dgs10, get_dfii10, get_sofr, get_iorb, get_effr, get_rrp_rate, get_sina_news, get_walcl, get_wresbal, get_wtre_gen, get_tga_daily, get_rrp_daily, _fred_series)

st.set_page_config(page_title="Macro Dashboard", page_icon="📊", layout="wide")

EASTMONEY_FOCUS_URL = "https://kuaixun.eastmoney.com/"
EASTMONEY_QUOTE_URL = "https://push2.eastmoney.com/api/qt/stock/get"
EASTMONEY_SEARCH_URL = "https://searchapi.eastmoney.com/api/suggest/get"
EASTMONEY_UT = "bd1d9ddb04089700cf9c27f4f4961f5b"
TENCENT_QUOTE_URL = "https://qt.gtimg.cn/q="
TENCENT_MINUTE_URL = "https://web.ifzq.gtimg.cn/appstock/app/minute/query"
DIRECT_QUOTE_FRESH_SECONDS = 90
RANGES = ["5Y", "1Y", "6M", "3M", "1M"]
PLOTLY_CONFIG = {"displayModeBar": False, "scrollZoom": False, "doubleClick": False, "editable": False, "displaylogo": False}
WATCHLIST_PARAM = "watchlist"
REPO_URL = "https://github.com/yingjieli176-art/macro_dashboard"
DASHBOARD_TZ = ZoneInfo("Asia/Hong_Kong")

st.markdown("""
<style>
.block-container { padding-top: 0.70rem; padding-bottom: 2rem; max-width: 1760px; }
html, body, [class*="css"] { font-family: "Noto Sans TC", "Noto Sans CJK TC", "Microsoft JhengHei", "PingFang TC", "Segoe UI", sans-serif; }
.dashboard-title { font-size: 1.9rem; font-weight: 700; letter-spacing: -0.02em; margin-bottom: 0.1rem; }
.section-title { font-size: 1.30rem; font-weight: 650; letter-spacing: -0.01em; margin-top: 0.45rem; margin-bottom: 0.08rem; min-height: 28px; display: flex; align-items: center; }
.section-description { color: #6b7280; font-size: 0.84rem; margin-bottom: 0.18rem; min-height: 18px; display: flex; align-items: center; }
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
div[data-testid="stPlotlyChart"] { border: 1px solid #eef2f7; border-radius: 12px; padding: 2px 4px 0; background: #fff; overflow: hidden; }
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

@st.cache_data(ttl=15, show_spinner=False)
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
    manual_key = st.session_state.get("_watchlist_refresh_key", 0)
    return _stable_quote(symbol, f"{_quote_refresh_key()}:{manual_key}")


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

def render_market_groups():
    now = time.time(); snapshot = st.session_state.get("_market_quotes_snapshot"); snapshot_time = st.session_state.get("_market_quotes_snapshot_time", 0)
    if not isinstance(snapshot, dict) or now - snapshot_time >= 60:
        refresh_key = _quote_refresh_key()
        snapshot = {"nasdaq": _stable_quote("^IXIC", refresh_key), "sp500": _stable_quote("^GSPC", refresh_key), "dow": _stable_quote("^DJI", refresh_key), "hsi": _stable_quote("^HSI", refresh_key), "hstech": _stable_quote("HSTECH.HK", refresh_key), "sh": _stable_quote("000001.SS", refresh_key), "sz": _stable_quote("399001.SZ", refresh_key), "csi300": _stable_quote("000300.SS", refresh_key)}
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
st.markdown('<div class="section-title">市场概览</div><div class="section-description">主要指数行情带 · 港/A 双源择新 + 分时兜底 · 15 秒刷新</div>', unsafe_allow_html=True)

@st.fragment(run_every="15s")
def render_market_overview():
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
st.markdown('<div class="section-title">自选观察</div><div class="section-description">核心标的快速监控 · 港/A 腾讯 + 东方财富双源择新，分时兜底 · Yahoo 仅备用 · 15 秒自动刷新</div>', unsafe_allow_html=True)

@st.fragment(run_every="15s")
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
    base_right = 76 if has_secondary else 20
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

def get_start_date(date_range):
    end = pd.Timestamp.now(tz="Asia/Hong_Kong").tz_localize(None).normalize()
    return {"5Y": end - pd.DateOffset(years=5), "1Y": end - pd.DateOffset(years=1), "6M": end - pd.DateOffset(months=6), "3M": end - pd.DateOffset(months=3), "1M": end - pd.DateOffset(months=1)}[date_range]

def filter_range(data, date_range): return data[data["observation_date"] >= get_start_date(date_range)].copy()
def chart_height(compact, normal): return compact if compact_mode else normal

@st.cache_data(ttl=3600, show_spinner=False)
def get_fred_series(series_id): return _fred_series(series_id)



# === HK LIQUIDITY CHART 5 ===
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
    data = get_dgs10().merge(get_dfii10(), on="observation_date", how="outer").merge(get_fred_series("T10YIE"), on="observation_date", how="outer").sort_values("observation_date")
    for column in ("DGS10", "DFII10", "T10YIE"):
        data[column] = pd.to_numeric(data.get(column), errors="coerce")
    # Treasury identity: Nominal ≈ Real + Breakeven. Preserve observed values
    # first and synthesize only a missing leg when the other two are present.
    data["DGS10"] = data["DGS10"].combine_first(data["DFII10"] + data["T10YIE"])
    data["DFII10"] = data["DFII10"].combine_first(data["DGS10"] - data["T10YIE"])
    data["T10YIE"] = data["T10YIE"].combine_first(data["DGS10"] - data["DFII10"])
    data = filter_range(data, date_range); fig = go.Figure()
    for column, name, width, dash, yaxis in [("DGS10", "10Y Nominal", 2.8, None, None), ("DFII10", "10Y Real (R)", 2.6, None, "y2"), ("T10YIE", "10Y Breakeven (R)", 2.5, "dot", "y2")]: add_line(fig, data, column, name, width, dash, yaxis)
    fig.update_layout(yaxis_title="Nominal Yield (%)", yaxis2=dict(title="Real / Breakeven (%)", overlaying="y", side="right", anchor="free", position=1.0, showgrid=False, zeroline=False, fixedrange=True, automargin=True, tickfont=dict(size=9))); return apply_chart_style(fig, chart_height(310, 420), date_range)

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
        add_line(fig, filter_range(reserve, date_range), "WRESBAL", "Reserve Balances", 2.4, yaxis="y2", unit=" T")
    else:
        _mark_missing_series(fig, "Reserve Balances")

    tga = raw_series.get("TGA_DAILY")
    if tga is not None:
        tga_name = "TGA · Weekly fallback" if tga_is_fallback else "TGA"
        add_line(fig, filter_range(tga, date_range), "TGA_DAILY", tga_name, 2.2, "dash", "y2", " T")
    else:
        _mark_missing_series(fig, "TGA")

    rrp = raw_series.get("RRPONTSYD")
    if rrp is not None:
        add_line(fig, filter_range(rrp, date_range), "RRPONTSYD", "ON RRP", 2.2, "dot", "y3", " B")
    else:
        _mark_missing_series(fig, "ON RRP")

    # Predeclare secondary axes so apply_chart_style reserves enough space.
    fig.update_layout(
        yaxis2=dict(overlaying="y", side="right", anchor="free", position=0.86),
        yaxis3=dict(overlaying="y", side="right", anchor="free", position=0.97),
    )
    fig = apply_chart_style(fig, chart_height(320, 430), date_range)
    fig.update_layout(
        margin=dict(l=64, r=164, t=72, b=34, pad=2),
        legend=dict(y=1.09, x=0.01),
        xaxis=dict(domain=[0.0, 0.82]),
        yaxis=dict(
            title="Net Liquidity · USD T",
            showgrid=True, gridcolor="#e5e7eb", griddash="dot",
            zeroline=False, fixedrange=True, tickformat=".1f",
        ),
        yaxis2=dict(
            title="R1 · Reserve / TGA · USD T",
            overlaying="y", side="right", anchor="free", position=0.86,
            showgrid=False, zeroline=False, fixedrange=True,
            tickformat=".1f", tickfont=dict(size=10),
        ),
        yaxis3=dict(
            title="R2 · ON RRP · USD B",
            overlaying="y", side="right", anchor="free", position=0.97,
            showgrid=False, zeroline=True, zerolinecolor="#94a3b8",
            zerolinewidth=1, fixedrange=True, tickformat=".0f",
            tickfont=dict(size=10),
        ),
    )
    return fig


def build_fig3(date_range):
    data = get_dgs3mo().merge(get_dgs2(), on="observation_date", how="outer").merge(get_dgs10(), on="observation_date", how="outer").sort_values("observation_date")
    for column in ("DGS3MO", "DGS2", "DGS10"):
        data[column] = pd.to_numeric(data.get(column), errors="coerce")
    # Derive curve spreads locally from the displayed yields. This removes two
    # redundant FRED requests and guarantees spread/yield internal consistency.
    data["T10Y2Y"] = data["DGS10"] - data["DGS2"]
    data["T10Y3M"] = data["DGS10"] - data["DGS3MO"]
    data = filter_range(data, date_range); fig = go.Figure()
    for column, name, width in [("DGS3MO", "3M", 2.2), ("DGS2", "2Y", 2.4), ("DGS10", "10Y", 2.8)]: add_line(fig, data, column, name, width)
    add_line(fig, data, "T10Y2Y", "10Y−2Y (R)", 2.2, "dot", "y2", "%"); add_line(fig, data, "T10Y3M", "10Y−3M (R)", 2.2, "dash", "y2", "%")
    fig.update_traces(selector=dict(name="10Y−2Y (R)"), hovertemplate="10Y−2Y (R): %{y:.3f}%<extra></extra>"); fig.update_traces(selector=dict(name="10Y−3M (R)"), hovertemplate="10Y−3M (R): %{y:.3f}%<extra></extra>")
    fig.update_layout(yaxis=dict(title="Yield (%)", fixedrange=True), yaxis2=dict(title="Spread (%)", overlaying="y", side="right", anchor="free", position=1.0, showgrid=False, zeroline=True, zerolinecolor="#9ca3af", fixedrange=True, automargin=True, tickfont=dict(size=9))); return apply_chart_style(fig, chart_height(310, 420), date_range)


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
        yaxis2=dict(overlaying="y", side="right", anchor="free", position=0.86),
        yaxis3=dict(overlaying="y", side="right", anchor="free", position=0.97),
    )
    fig = apply_chart_style(fig, chart_height(320, 440), date_range)
    fig.update_layout(
        margin=dict(l=62, r=144, t=68, b=36, pad=2),
        legend=dict(y=1.095),
        xaxis=dict(domain=[0.0, 0.84]),
        yaxis=dict(
            title="VIX / VIXEQ",
            showgrid=True, gridcolor="#e5e7eb", griddash="dot",
            zeroline=False, fixedrange=True,
        ),
        yaxis2=dict(
            title="R1 · S&P 500",
            overlaying="y", side="right", anchor="free", position=0.86,
            showgrid=False, zeroline=False, fixedrange=True, tickfont=dict(size=10),
        ),
        yaxis3=dict(
            title="R2 · VIX3M−VIX",
            overlaying="y", side="right", anchor="free", position=0.97,
            showgrid=False, zeroline=True, zerolinecolor="#94a3b8",
            zerolinewidth=1, fixedrange=True, tickfont=dict(size=10),
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


def build_fig10(date_range, market_mode="Rebased 100"):
    """Precious metals: gold, silver, gold/silver ratio, and GVZ."""
    frames = []
    for symbol, column in (("GC=F", "Gold"), ("SI=F", "Silver")):
        try:
            frame = get_yahoo_daily_history(symbol).rename(columns={"close": column})
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
        add_line(fig, data, "GoldSilverRatio", "Gold/Silver Ratio", 2.2, "dash", "y2", "x")
        add_line(fig, data, "GVZCLS", "Gold Volatility · GVZ", 2.2, "dot", "y3", "")
        fig.update_layout(
            yaxis2=dict(overlaying="y", side="right", anchor="free", position=0.87),
            yaxis3=dict(overlaying="y", side="right", anchor="free", position=0.98),
        )
        fig = apply_chart_style(fig, chart_height(320, 440), date_range)
        fig.update_layout(
            margin=dict(l=62, r=150, t=72, b=34, pad=2),
            legend=dict(y=1.09, x=0.01),
            xaxis=dict(domain=[0.0, 0.84]),
            yaxis=dict(title="Gold / Silver · Rebased 100", tickformat=".1f"),
            yaxis2=dict(title="R1 · Gold/Silver Ratio", overlaying="y", side="right", anchor="free", position=0.87, showgrid=False, fixedrange=True, tickformat=".1f"),
            yaxis3=dict(title="R2 · GVZ", overlaying="y", side="right", anchor="free", position=0.98, showgrid=False, fixedrange=True, tickformat=".1f"),
        )
        return fig

    add_line(fig, data, "Gold", "Gold", 2.8, unit=" USD/oz")
    add_line(fig, data, "Silver", "Silver", 2.5, None, "y2", " USD/oz")
    add_line(fig, data, "GoldSilverRatio", "Gold/Silver Ratio", 2.2, "dash", "y3", "x")
    add_line(fig, data, "GVZCLS", "Gold Volatility · GVZ", 2.2, "dot", "y4", "")
    fig.update_layout(
        yaxis2=dict(overlaying="y", side="right", anchor="free", position=0.78),
        yaxis3=dict(overlaying="y", side="right", anchor="free", position=0.88),
        yaxis4=dict(overlaying="y", side="right", anchor="free", position=0.98),
    )
    fig = apply_chart_style(fig, chart_height(330, 450), date_range)
    fig.update_layout(
        margin=dict(l=68, r=220, t=72, b=34, pad=2),
        legend=dict(y=1.09, x=0.01),
        xaxis=dict(domain=[0.0, 0.75]),
        yaxis=dict(title="Gold · USD/oz", tickformat=",.0f"),
        yaxis2=dict(title="R1 · Silver · USD/oz", overlaying="y", side="right", anchor="free", position=0.78, showgrid=False, fixedrange=True, tickformat=".1f"),
        yaxis3=dict(title="R2 · Gold/Silver", overlaying="y", side="right", anchor="free", position=0.88, showgrid=False, fixedrange=True, tickformat=".1f"),
        yaxis4=dict(title="R3 · GVZ", overlaying="y", side="right", anchor="free", position=0.98, showgrid=False, fixedrange=True, tickformat=".1f"),
    )
    return fig


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
        add_line(fig, data, "ETHBTC", "ETH/BTC (R1)", 2.2, "dash", "y2", "")
        add_line(fig, data, "BTC_VOL_30D", "BTC 30D Realized Vol (R2)", 2.2, "dot", "y3", "%")
        fig.update_layout(
            yaxis2=dict(overlaying="y", side="right", anchor="free", position=0.925),
            yaxis3=dict(overlaying="y", side="right", anchor="free", position=0.99),
        )
        fig = apply_chart_style(fig, chart_height(320, 440), date_range)
        fig.update_layout(
            margin=dict(l=62, r=92, t=72, b=34, pad=2),
            legend=dict(y=1.09, x=0.01),
            xaxis=dict(domain=[0.0, 0.91]),
            yaxis=dict(title="BTC / ETH · Rebased 100", tickformat=".1f"),
            yaxis2=dict(title="", overlaying="y", side="right", anchor="free", position=0.925, showgrid=False, fixedrange=True, tickformat=".4f", tickfont=dict(size=9), ticks="outside", ticklen=3),
            yaxis3=dict(title="", overlaying="y", side="right", anchor="free", position=0.99, showgrid=False, fixedrange=True, tickformat=".0f", tickfont=dict(size=9), ticks="outside", ticklen=3),
        )
        return fig

    add_line(fig, data, "BTC", "BTC", 2.9, unit=" USD")
    add_line(fig, data, "ETH", "ETH (R1)", 2.6, None, "y2", " USD")
    add_line(fig, data, "ETHBTC", "ETH/BTC (R2)", 2.2, "dash", "y3", "")
    add_line(fig, data, "BTC_VOL_30D", "BTC 30D Realized Vol (R3)", 2.2, "dot", "y4", "%")
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


CRYPTO_MARKET_DESCRIPTION = (
    '<b>参数概念：</b><br>'
    '1. BTC / ETH：比特币与以太坊美元价格；默认 Rebased 100 共用左轴。Raw 模式中 BTC 使用左轴、ETH 使用 R1。<br>'
    '2. ETH/BTC：ETH 价格除以 BTC 价格；Rebased 100 使用 R1，Raw 使用 R2。上升表示 ETH 相对 BTC 走强。<br>'
    '3. BTC 30D Realized Vol：BTC 日收益率计算的 30 日年化实际波动率；Rebased 100 使用 R2，Raw 使用 R3，不是期权隐含波动率。<br><br>'
    '<b>读取提示：</b>默认优先看 Rebased 100 的 BTC / ETH 强弱，再结合 ETH/BTC 判断风险偏好是否从 BTC 向 ETH 扩散；波动率快速抬升意味着仓位风险同步放大。'
)

PARAM_DESCRIPTIONS = [
    '<b>参数概念：</b><br>1. IORB（Interest on Reserve Balances）：美联储向存款机构准备金余额支付的利率，是美国准备金利率体系的重要基准。<br>2. ON RRP（Overnight Reverse Repurchase Agreement）：美联储隔夜逆回购工具利率，金融机构可通过该工具进行隔夜资金配置。<br>3. EFFR（Effective Federal Funds Rate）：美国联邦基金市场实际成交形成的有效隔夜利率，反映银行间短期无担保资金价格。<br>4. SOFR（Secured Overnight Financing Rate）：以美国国债为抵押的隔夜融资利率，是美元有担保短期融资的重要基准。',
    '<b>参数概念：</b><br>1. 10Y Nominal：10 年期美国国债名义收益率，包含实际利率与通胀预期等因素。<br>2. 10Y Real：10 年期美国国债实际收益率，通常由通胀保值国债（TIPS）市场反映。<br>3. 10Y Breakeven：10 年期盈亏平衡通胀率，是名义国债收益率与实际收益率之间的差值，用于观察市场隐含的长期通胀预期。',
    '<b>参数概念：</b><br>1. 3M：3 个月期美国国债收益率，代表较短期限的美元无风险利率。<br>2. 2Y：2 年期美国国债收益率，通常对美联储政策路径及短中期利率预期较敏感。<br>3. 10Y：10 年期美国国债收益率，是全球金融市场重要的长期无风险利率参考。<br>4. 10Y−2Y：10 年期减 2 年期国债收益率利差，图中直接以百分比（%）显示，无需自行换算 bp。<br>5. 10Y−3M：10 年期减 3 个月期国债收益率利差，图中直接以百分比（%）显示，无需自行换算 bp。',
    '<b>参数概念：</b><br>1. Net Liquidity Proxy：WALCL（美联储总资产）− TGA − ON RRP 的常用资产负债表流动性代理，左轴单位 USD trillion；不是美联储官方指标。WALCL 为周频，计算时只在代理内部沿用至下一次公布。<br>2. Reserve Balances：存款机构存放在美联储的准备金余额；WRESBAL 为周频公布，使用右轴 R1，单位 USD trillion。图中的原始线只保留实际周频观测。<br>3. TGA（Treasury General Account）：优先使用美国财政部 Daily Treasury Statement 的日频 Operating Cash Balance；财政资金进出会直接影响银行体系准备金。FiscalData 不可用时自动回退到 FRED WTREGEN 周频数据。<br>4. ON RRP Balance：美联储隔夜逆回购工具余额，使用右轴 R2，单位 USD billion；单独设轴避免当前低余额被压在零线附近。',
    '<b>参数概念：</b><br>1. HKD M2 YoY：港元 M2 同比增速，M2 覆盖公众持有的现金、活期/储蓄/定期存款及相应货币工具，用于观察广义港元货币的中期扩张趋势。<br>2. HKD M3 YoY：港元 M3 同比增速，M3 在 M2 基础上进一步纳入限制牌照银行及接受存款公司的相关存款与可转让存款证，因此口径更广，但通常与 M2 高度同步。<br>3. Monetary Base YoY：香港货币基础总量同比变化，用于观察基础货币层面的中期扩张与收缩。<br>4. Aggregate Balance：银行体系总结余，单位 HK$ billion；总结余下降通常代表银行体系可用港元流动性趋紧。<br>5. O/N HIBOR：隔夜港元银行同业拆息，反映最短端港元资金价格。<br>6. 3M HIBOR：3 个月港元银行同业拆息，用来观察更持续的港元融资成本。<br>7. HKMA Base Rate：香港金管局基本利率，是港元利率体系的重要政策参考。<br>8. O/N−3M Spread（R）：隔夜 HIBOR 减 3M HIBOR，右轴单位 bp；显著转正通常代表短端资金压力上升。<br>9. USD/HKD：每 1 美元对应的港元价格；向 7.85 上升表示港元转弱，向 7.75 下降表示港元转强。<br>10. Strong-side CU 7.75：联系汇率制度下强方兑换保证。<br>11. Weak-side CU 7.85：联系汇率制度下弱方兑换保证。<br><br><b>读取提示：</b>M2/M3 为月度统计，公布存在时滞；图 5 使用 YoY 观察中期货币趋势并降低单月噪声。流动性评分内部仍使用最近 3 个月 M2/M3 MoM 均值，以保留对边际拐点的敏感度。',
]

def show_parameter_description(index): st.markdown(f'<div class="mini-description">{PARAM_DESCRIPTIONS[index]}</div>', unsafe_allow_html=True)

HK_PARAMETER_DESCRIPTIONS = [
    '<b>参数概念：</b><br>1. HKD M2 YoY：港元 M2 同比增速，作为主趋势线，用来观察广义港元货币的中期扩张或收缩；相比 MoM 更平滑。<br>2. HKD M2 MoM：港元 M2 月环比增速，作为边际动量线，用来观察最近一个月货币扩张/收缩是否加速；波动会明显高于 YoY。<br>3. Monetary Base YoY：香港货币基础总量同比变化，用于观察基础货币的中期扩张与收缩。<br>4. HKEX Price（R1）：港交所 0388.HK 市场价格，右轴单位 HKD；用于观察香港交易所股价与货币流动性变化之间的市场映射。<br>5. HSTECH Index（R2）：恒生科技指数 HSTECH 市场点位，右轴单位 points；市场历史独立拉取 5Y，不再被 HKMA 月度快照长度裁断。<br>6. HSI Index（R2）：恒生指数市场点位，右轴单位 points；使用 ^HSI 的 5Y 市场历史，用于对照香港大盘与流动性变化。<br>7. Tencent Price（R1）：腾讯控股 0700.HK 股价，Raw 模式与港交所共用 R1 港元价格轴；Rebased 100 模式把可视区间首个有效值归一到 100，便于比较相对弹性。<br><br><b>读取提示：</b>默认只保留 M2 的同比与环比：YoY 看趋势，MoM 看边际拐点。M3 YoY 仍保留在底层数据中，但因与 M2 YoY 高度同步，不再默认绘制，减少重复信息。<br><br><b>市场显示：</b>Raw 模式把股票价格放在 R1、指数点位放在 R2；Rebased 100 模式把 Tencent / HKEX / HSTECH / HSI 统一归一化，用于比较涨跌幅而不是绝对点位。',
    '<b>参数概念：</b><br>1. Closing Aggregate Balance：银行体系期末总结余，单位 HK$ billion；5Y 视图使用 HKMA 月度期末历史，数值下降通常代表可用港元流动性收紧。<br>2. Outstanding EFBN（R）：外汇基金票据及债券未偿还总额，右轴单位 HK$ billion，是香港货币基础的重要结构项。<br>3. EFBN Held by Licensed Banks（R）：由持牌银行持有的 EFBN，右轴单位 HK$ billion，用于观察银行体系持有的高流动性港元资产规模。<br><br><b>读取提示：</b>5Y 历史只展示 HKMA 实际公布的月度期末字段，不再用 Closing Aggregate Balance 复制生成 Opening 或 Forecast。若未来日频快照可用，短周期视图仍可显示真实 Opening / Closing / Forecast T+1。',
    '<b>参数概念：</b><br>1. O/N HIBOR：隔夜港元银行同业拆息，5Y 月度历史来自 C&SD 月刊（底层来源 HKAB / HKMA），反映最短端港元资金价格。<br>2. 3M HIBOR：3 个月港元银行同业拆息，用来观察更持续的港元融资成本。<br>3. HKMA Base Rate：香港金管局贴现窗基本利率；5Y 历史直接来自 HKMA 月末官方序列。<br>4. O/N−3M Spread（R）：隔夜 HIBOR 减 3M HIBOR，右轴单位 bp；显著转正通常代表短端资金压力上升。',
    '<b>参数概念：</b><br>1. USD/HKD：每 1 美元对应的港元价格；向 7.85 上升表示港元转弱，向 7.75 下降表示港元转强。<br>2. Strong-side CU 7.75：联系汇率制度下强方兑换保证。<br>3. Linked Rate Center 7.80：7.75–7.85 兑换保证区间的中点参考线，用于快速判断港元当前处在偏强侧还是偏弱侧；不是额外的兑换保证触发水平。<br>4. Weak-side CU 7.85：联系汇率制度下弱方兑换保证。<br>5. HKEX Price（R1）：港交所 0388.HK 市场价格，右轴单位 HKD。<br>6. HSTECH Index（R2）：恒生科技指数 HSTECH 市场点位，右轴单位 points。<br>7. HSI Index（R2）：恒生指数点位，Raw 模式对应 R2。<br>8. Tencent Price（R1）：腾讯控股 0700.HK 股价，Raw 模式对应 R1 港元价格轴。<br><br><b>市场显示：</b>Raw 模式保留真实价格/点位；Rebased 100 模式把四条市场资产在可视区间首个有效值归一到 100，用来比较谁更强、谁更弱。<br><br><b>读取提示：</b>USD/HKD 左轴已反向：7.75 强方兑换保证显示在上方、7.85 弱方兑换保证显示在下方，因此视觉方向直接对应“港元偏强/流动性偏强 → 港元偏弱/流动性偏弱”。灰色区域表示 7.75–7.85 联系汇率区间；其中 7.84–7.85 的淡红区域为 Weak-side Pressure Zone，用于提示接近弱方兑换保证的压力阶段；USD/HKD 优先使用仓库持久化的 Yahoo HKD=X 日频 5Y 快照，HKMA 月度汇率作为回退。',
]

def show_hk_parameter_description(index):
    st.markdown(f'<div class="mini-description">{HK_PARAMETER_DESCRIPTIONS[index]}</div>', unsafe_allow_html=True)


US_EQUITY_RISK_DESCRIPTION = '<b>参数概念：</b><br>1. VIX：基于 S&P 500 指数期权的约 30 天隐含波动率，反映指数层面的近端风险定价。<br>2. VIXEQ：Cboe S&P 500 Constituent Volatility Index，衡量一篮子标普 500 成分股按市值加权的约 30 天隐含波动率；它使用单股期权，因此与 VIX 并非同一个指标。<br>3. S&P 500（R1）：标普 500 指数点位，用来观察风险价格与现货大盘的同步/背离。<br>4. VIX3M−VIX（R2）：3 个月 VIX 减约 30 天 VIX。通常为正代表期限结构较正常；快速收窄或转负表示近端隐含波动率高于远端，常见于短期压力上升阶段。<br><br><b>读取提示：</b>VIX 与 VIXEQ 同时上升代表指数与成分股隐含波动率共同抬升；若 VIXEQ 相对 VIX 更强，通常意味着单股波动/分化风险更突出。VIXEQ 于 2024-11-04 正式开始实时发布；Cboe 官方历史文件提供回溯序列，图表使用官方历史值，不自行外推。'


PRECIOUS_METALS_DESCRIPTION = '<b>参数概念：</b><br>1. Gold：COMEX 黄金连续近月期货 GC=F 日收盘价，单位 USD/oz。<br>2. Silver：COMEX 白银连续近月期货 SI=F 日收盘价，单位 USD/oz。<br>3. Gold/Silver Ratio：金价 ÷ 银价；上升表示黄金相对白银更强，下降表示白银相对更强。<br>4. Gold Volatility / GVZ：Cboe Gold ETF Volatility Index，反映黄金相关期权的隐含波动率。<br><br><b>读取提示：</b>默认 Rebased 100 用于比较金银相对强弱；Raw 模式保留金银绝对价格，并为 Silver、金银比和 GVZ 使用独立右轴，避免不同量纲互相压缩。'

compact_mode = False

def render_core_charts():
    st.markdown('<div class="section-title">US monetary policy, Treasury yields and inflation expectations</div>', unsafe_allow_html=True)

    configs = [
        ('<div class="section-title">🏦 1. Fed Policy Rate & Money Market</div>', '<div class="section-description">IORB / ON RRP Rate / EFFR / SOFR</div>', "normal_corridor_range", build_fig1, [("IORB (IORB)", "https://fred.stlouisfed.org/series/IORB"), ("ON RRP Rate (RRPONTSYAWARD)", "https://fred.stlouisfed.org/series/RRPONTSYAWARD"), ("EFFR (EFFR)", "https://fred.stlouisfed.org/series/EFFR"), ("SOFR (SOFR)", "https://fred.stlouisfed.org/series/SOFR")], 0),
        ('<div class="section-title">2. 10Y Yield Structure</div>', '<div class="section-description">10Y Nominal / 10Y Real (R) / 10Y Breakeven (R)</div>', "normal_yield10_range", build_fig2, [("10Y Nominal (DGS10)", "https://fred.stlouisfed.org/series/DGS10"), ("10Y Real (DFII10)", "https://fred.stlouisfed.org/series/DFII10"), ("10Y Breakeven (T10YIE)", "https://fred.stlouisfed.org/series/T10YIE")], 1),
        ('<div class="section-title">3. Treasury Yield & Curve Spread</div>', '<div class="section-description">3M / 2Y / 10Y / 10Y−2Y (R) / 10Y−3M (R)</div>', "normal_treasury_range", build_fig3, [("3M Treasury (DGS3MO)", "https://fred.stlouisfed.org/series/DGS3MO"), ("2Y Treasury (DGS2)", "https://fred.stlouisfed.org/series/DGS2"), ("10Y Nominal (DGS10)", "https://fred.stlouisfed.org/series/DGS10"), ("10Y−2Y Spread (T10Y2Y)", "https://fred.stlouisfed.org/series/T10Y2Y"), ("10Y−3M Spread (T10Y3M)", "https://fred.stlouisfed.org/series/T10Y3M")], 2),
        ('<div class="section-title">4. US Liquidity</div>', '<div class="section-description">Net Liquidity (L) · Reserve Balances / TGA (R1) · ON RRP (R2)</div>', "normal_liquidity_range", build_fig4, [("Fed Total Assets (WALCL)", "https://fred.stlouisfed.org/series/WALCL"), ("Reserve Balances (WRESBAL)", "https://fred.stlouisfed.org/series/WRESBAL"), ("TGA · Daily Treasury Statement", "https://fiscaldata.treasury.gov/datasets/daily-treasury-statement/operating-cash-balance"), ("TGA fallback (WTREGEN)", "https://fred.stlouisfed.org/series/WTREGEN"), ("ON RRP Balance (RRPONTSYD)", "https://fred.stlouisfed.org/series/RRPONTSYD")], 3),
    ]

    for title, description, key, builder, sources, desc_index in configs:
        st.markdown(title, unsafe_allow_html=True)
        st.markdown(description, unsafe_allow_html=True)
        date_range = st.radio("时间范围", RANGES, horizontal=True, index=1, key=key, label_visibility="collapsed")
        st.plotly_chart(builder(date_range), use_container_width=True, config=PLOTLY_CONFIG)
        show_parameter_description(desc_index)
        add_sources(sources)
        st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)

    st.markdown('<div class="section-kicker">HONG KONG LIQUIDITY</div>', unsafe_allow_html=True)
    # Build the full Hong Kong data set once. Charts 5-8 then behave exactly
    # like charts 1-4: external title, description, independent range control,
    # chart, local parameter notes, local sources, divider.
    hk_configs = [
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
            '<div class="section-description">Aggregate Balance · Outstanding EFBN (R) · EFBN Held by Licensed Banks (R)</div>',
            "hk_6_range",
            [
                ("HKMA Monetary Base", "https://apidocs.hkma.gov.hk/documentation/market-data-and-statistics/monthly-statistical-bulletin/monetary-operation/monetary-base-endperiod/"),
                ("HKMA Daily Interbank Liquidity", "https://apidocs.hkma.gov.hk/documentation/market-data-and-statistics/daily-monetary-statistics/daily-figures-interbank-liquidity/"),
            ],
        ),
        (
            '<div class="section-title">7. HKD Funding</div>',
            '<div class="section-description">O/N HIBOR · 3M HIBOR · HKMA Base Rate · O/N−3M Spread (R)</div>',
            "hk_7_range",
            [
                ("HKMA Open API", "https://apidocs.hkma.gov.hk/"),
                ("HKMA Base Rate", "https://apidocs.hkma.gov.hk/documentation/market-data-and-statistics/monthly-statistical-bulletin/monetary-operation/disc-win-liquid-adj-win-rates-endperiod/"),
            ],
        ),
        (
            '<div class="section-title">8. USD/HKD Convertibility Band & Market</div>',
            '<div class="section-description">USD/HKD · Weak-side pressure 7.84–7.85 · Tencent / HKEX (R1) · HSTECH / HSI (R2)</div>',
            "hk_8_range",
            [
                ("HKMA Linked Exchange Rate System", "https://www.hkma.gov.hk/eng/key-functions/money/linked-exchange-rate-system/"),
                ("Yahoo Finance Market History", "https://finance.yahoo.com/"),
                ("Hang Seng Indexes · HSTECH", "https://www.hsi.com.hk/eng/indexes/all-indexes/hstech"),
                ("Hang Seng Indexes · HSI", "https://www.hsi.com.hk/eng/indexes/all-indexes/hsi"),
            ],
        ),
    ]

    for hk_index, (title, description, key, sources) in enumerate(hk_configs):
        st.markdown(title, unsafe_allow_html=True)
        st.markdown(description, unsafe_allow_html=True)
        hk_range = st.radio(
            "时间范围",
            RANGES,
            horizontal=True,
            index=1,
            key=key,
            label_visibility="collapsed",
        )
        hk_market_mode = "Raw"
        if hk_index in (0, 3):
            hk_market_mode = st.radio(
                "市场显示",
                ["Raw", "Rebased 100"],
                horizontal=True,
                index=0,
                key=f"{key}_market_mode",
                label_visibility="collapsed",
            )
        hk_figure = build_fig5(hk_range, market_mode=hk_market_mode)[hk_index]
        st.plotly_chart(
            hk_figure,
            use_container_width=True,
            config=PLOTLY_CONFIG,
        )
        show_hk_parameter_description(hk_index)
        add_sources(sources)
        if hk_index < len(hk_configs) - 1:
            st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)

    st.markdown(
        '<div class="section-kicker">US EQUITY RISK</div>'
        '<div class="section-title">9. US Equity Risk & Volatility Structure</div>'
        '<div class="section-description">VIX · VIXEQ · S&P 500 (R1) · VIX3M−VIX (R2)</div>',
        unsafe_allow_html=True,
    )
    risk_range = st.radio(
        "时间范围",
        RANGES,
        horizontal=True,
        index=1,
        key="us_equity_risk_range",
        label_visibility="collapsed",
    )
    st.plotly_chart(build_fig9(risk_range), use_container_width=True, config=PLOTLY_CONFIG)
    st.markdown(f'<div class="mini-description">{US_EQUITY_RISK_DESCRIPTION}</div>', unsafe_allow_html=True)
    add_sources([
        ("Cboe VIX", "https://www.cboe.com/tradable-products/vix/"),
        ("Cboe VIXEQ / Dispersion", "https://www.cboe.com/us/indices/dispersion/"),
        ("FRED VIX3M (VXVCLS)", "https://fred.stlouisfed.org/series/VXVCLS"),
        ("FRED S&P 500 (SP500)", "https://fred.stlouisfed.org/series/SP500"),
    ])
    st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)

    st.markdown(
        '<div class="section-kicker">PRECIOUS METALS</div>'
        '<div class="section-title">10. Precious Metals</div>'
        '<div class="section-description">Gold / Silver · Gold/Silver Ratio (R1) · Gold Volatility GVZ (R2/R3)</div>',
        unsafe_allow_html=True,
    )
    metals_range = st.radio(
        "时间范围", RANGES, horizontal=True, index=1,
        key="precious_metals_range", label_visibility="collapsed",
    )
    metals_mode = st.radio(
        "市场显示", ["Rebased 100", "Raw"], horizontal=True, index=0,
        key="precious_metals_mode", label_visibility="collapsed",
    )
    st.plotly_chart(build_fig10(metals_range, metals_mode), use_container_width=True, config=PLOTLY_CONFIG)
    st.markdown(f'<div class="mini-description">{PRECIOUS_METALS_DESCRIPTION}</div>', unsafe_allow_html=True)
    add_sources([
        ("Yahoo Finance · Gold Futures GC=F", "https://finance.yahoo.com/quote/GC=F/history/"),
        ("Yahoo Finance · Silver Futures SI=F", "https://finance.yahoo.com/quote/SI=F/history/"),
        ("FRED · Cboe Gold ETF Volatility Index (GVZCLS)", "https://fred.stlouisfed.org/series/GVZCLS"),
        ("Cboe · Gold Volatility", "https://www.cboe.com/tradable_products/vix/vix_historical_data/"),
    ])
    st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)

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

st.markdown('<div id="macro-charts" class="section-anchor"></div><div class="section-kicker">MACRO CHARTS</div>', unsafe_allow_html=True)
render_core_charts()
st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)

st.markdown('<div id="news" class="section-anchor"></div><div class="section-kicker">NEWS</div>', unsafe_allow_html=True)
st.markdown('<div class="section-title">📰 7×24 重点财经快讯</div>', unsafe_allow_html=True)
st.markdown('<div class="section-description">东方财富「红字焦点快讯」 · 源端焦点流 · 每60秒自动刷新</div>', unsafe_allow_html=True)

@st.fragment(run_every="60s")
def render_news_panel():
    _, action_col = st.columns([5, 1])
    with action_col:
        if st.button("🔄 立即刷新", key="refresh_7x24", use_container_width=True): get_sina_news.clear()
    news_items, news_error = get_sina_news(limit=50)
    if news_items:
        st.markdown(f'<div class="news-status">当前显示 {len(news_items)} 条 · 来源：东方财富红字焦点快讯 · 60秒自动刷新</div>', unsafe_allow_html=True); news_html = '<div class="news-box">'
        for idx, item in enumerate(news_items, start=1):
            news_time = html.escape(str(item.get("time", ""))); news_title = html.escape(str(item.get("title", ""))); news_content = html.escape(str(item.get("content", ""))); news_url = html.escape(str(item.get("url", EASTMONEY_FOCUS_URL)), quote=True)
            if not news_url.startswith(("http://", "https://")): news_url = EASTMONEY_FOCUS_URL
            body = f"<strong>{news_title}</strong><div style=\"margin-top:3px;\">{news_content}</div>" if news_title and news_content and news_title != news_content else (news_content or news_title)
            news_html += f'<div class="news-item"><span class="news-index">{idx}.</span><span class="news-time">{news_time}</span><div class="news-content"><a href="{news_url}" target="_blank" rel="noopener noreferrer">{body}</a></div></div>'
        st.markdown(news_html + "</div>", unsafe_allow_html=True)
    else:
        st.warning("暂时无法取得东方财富红字焦点快讯。")
        if news_error: st.caption(f"错误：{news_error}")
    add_sources([("东方财富红字焦点快讯", EASTMONEY_FOCUS_URL)])

render_news_panel()
st.markdown(f'<div class="source-text">Source: <a href="{EASTMONEY_FOCUS_URL}" target="_blank" rel="noopener noreferrer">Eastmoney 7×24 Focus News</a></div>', unsafe_allow_html=True)
