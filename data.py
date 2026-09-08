import html
import json
import re
import time

import pandas as pd
import requests
import streamlit as st


# =========================================================
# FRED
# =========================================================

FRED_API_URL = "https://api.stlouisfed.org/fred/series/observations"
FRED_API_KEY = st.secrets.get("FRED_API_KEY", "")


# =========================================================
# NEWS
# =========================================================

# 官方东方财富 7×24 全球直播接口。
# fastColumn=102 = 7×24 全球快讯全量。
# 不再经过第三方聚合/代理接口，避免把第三方数据冒充东方财富官方来源。
EASTMONEY_FOCUS_API = (
    "https://np-weblist.eastmoney.com/comm/web/getFastNewsList"
)

EASTMONEY_NEWS_URL = "https://kuaixun.eastmoney.com/"

NEWS_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/152.0.0.0 Safari/537.36"
    ),
    "Referer": EASTMONEY_NEWS_URL,
    "Accept": "application/json, text/plain, */*",
}


# =========================================================
# FRED CORE
# =========================================================

def _fred_series(series_id):
    if not FRED_API_KEY:
        raise RuntimeError(
            "FRED_API_KEY 未设置。请在 Streamlit Secrets 中加入 FRED_API_KEY。"
        )

    params = {
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "sort_order": "asc",
    }
    response = requests.get(FRED_API_URL, params=params, timeout=4)
    response.raise_for_status()
    payload = response.json()
    observations = payload.get("observations", [])
    rows = []

    for item in observations:
        value = item.get("value")
        if value in (None, "", "."):
            continue
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        rows.append({
            "observation_date": pd.to_datetime(item["date"], errors="coerce"),
            series_id: value,
        })

    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError(f"FRED {series_id} 没有返回有效数据。")

    return df.dropna(subset=["observation_date"]).sort_values("observation_date")


# =========================================================
# FRED SERIES
# =========================================================

@st.cache_data(ttl=3600)
def get_dgs3mo(): return _fred_series("DGS3MO")

@st.cache_data(ttl=3600)
def get_dgs2(): return _fred_series("DGS2")

@st.cache_data(ttl=3600)
def get_dgs10(): return _fred_series("DGS10")

@st.cache_data(ttl=3600)
def get_dfii10(): return _fred_series("DFII10")

@st.cache_data(ttl=3600)
def get_sofr(): return _fred_series("SOFR")

@st.cache_data(ttl=3600)
def get_iorb(): return _fred_series("IORB")

@st.cache_data(ttl=3600)
def get_effr(): return _fred_series("EFFR")

@st.cache_data(ttl=3600)
def get_rrp_rate(): return _fred_series("RRPONTSYAWARD")

@st.cache_data(ttl=3600)
def get_gfdebtn(): return _fred_series("GFDEBTN")

@st.cache_data(ttl=3600)
def get_fygfdpun(): return _fred_series("FYGFDPUN")

@st.cache_data(ttl=3600)
def get_fdhbfrbn(): return _fred_series("FDHBFRBN")

@st.cache_data(ttl=3600)
def get_fdhbfin(): return _fred_series("FDHBFIN")

@st.cache_data(ttl=3600)
def get_fdhbpin(): return _fred_series("FDHBPIN")

@st.cache_data(ttl=3600)
def get_walcl(): return _fred_series("WALCL")

@st.cache_data(ttl=3600)
def get_wresbal(): return _fred_series("WRESBAL")

@st.cache_data(ttl=3600)
def get_wtre_gen(): return _fred_series("WTREGEN")

@st.cache_data(ttl=3600)
def get_rrp_daily(): return _fred_series("RRPONTSYD")


# =========================================================
# TEXT CLEAN
# =========================================================

def _clean_text(value):
    if value is None:
        return ""
    text = html.unescape(str(value))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# =========================================================
# JSON / NEWS LIST SEARCH
# =========================================================

def _find_list(obj):
    if isinstance(obj, list):
        return obj
    if not isinstance(obj, dict):
        return []

    for key in (
        "list", "List", "data", "Data", "items", "Items", "rows", "Rows",
        "news", "News", "fastNewsList", "FastNewsList",
    ):
        value = obj.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            result = _find_list(value)
            if result:
                return result

    for value in obj.values():
        if isinstance(value, dict):
            result = _find_list(value)
            if result:
                return result
        elif isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
            return value
    return []


def _get_field(item, names):
    if not isinstance(item, dict):
        return ""
    for name in names:
        if name not in item:
            continue
        value = item.get(name)
        if value not in (None, ""):
            return value
    return ""


# =========================================================
# TITLE / CONTENT / TIME / URL / ID
# =========================================================

def _extract_title(item):
    value = _get_field(item, [
        "title", "Title", "newsTitle", "NewsTitle", "showTitle", "ShowTitle",
        "art_title", "ArtTitle",
    ])
    title = _clean_text(value)
    if title:
        return title

    content = _clean_text(_get_field(item, ["content", "Content", "text", "Text"]))
    if not content:
        return ""
    match = re.match(r"^〖(.+?)〗", content, flags=re.DOTALL)
    if match:
        return match.group(1).strip()
    return content if len(content) <= 120 else content[:120] + "..."


def _extract_content(item):
    value = _get_field(item, [
        "summary", "Summary", "digest", "Digest",
        "content", "Content", "rich_text", "RichText", "text", "Text",
        "title", "Title", "newsTitle", "NewsTitle",
    ])
    return _clean_text(value)


def _extract_time(item):
    value = _get_field(item, [
        "showTime", "ShowTime", "time", "Time", "createTime", "CreateTime",
        "create_time", "updateTime", "UpdateTime", "publishTime", "PublishTime",
        "ctime", "Ctime",
    ])
    text = _clean_text(value)
    if not text:
        return ""
    match = re.search(r"(\d{1,2}:\d{2}(?::\d{2})?)", text)
    return match.group(1) if match else text


def _extract_url(item):
    value = _get_field(item, [
        "url", "URL", "Url", "newsUrl", "NewsUrl", "articleUrl", "ArticleUrl",
        "url_h5", "urlH5", "link", "Link",
    ])
    url = _clean_text(value)
    if url.startswith(("http://", "https://")):
        return url
    return EASTMONEY_NEWS_URL


def _extract_id(item):
    value = _get_field(item, [
        "id", "ID", "newsId", "NewsId", "art_code", "ArtCode", "code", "Code",
    ])
    return str(value or "")


# =========================================================
# REQUEST 7x24 NEWS — OFFICIAL EASTMONEY
# =========================================================

def _request_focus_news(page_size=100):
    params = {
        "client": "web",
        "biz": "web_724",
        "fastColumn": "102",
        "sortEnd": "",
        "pageSize": str(page_size),
        "req_trace": str(int(time.time() * 1000)),
    }
    response = requests.get(
        EASTMONEY_FOCUS_API,
        params=params,
        headers=NEWS_HEADERS,
        timeout=10,
    )
    response.raise_for_status()

    try:
        return response.json()
    except ValueError:
        text = response.text.strip()
        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace >= 0 and last_brace > first_brace:
            return json.loads(text[first_brace:last_brace + 1])
        raise RuntimeError("东方财富 7×24 全球直播返回的数据格式无法解析。")


# =========================================================
# PARSE NEWS
# =========================================================

def _parse_focus_news(raw_items):
    result = []
    seen = set()

    for item in raw_items:
        if not isinstance(item, dict):
            continue

        title = _extract_title(item)
        content = _extract_content(item)
        if not title and not content:
            continue
        if not title:
            title = content
        if not content:
            content = title

        normalized = re.sub(r"\s+", "", (title + content).lower())
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)

        result.append({
            "id": _extract_id(item),
            "title": title,
            "content": content,
            "time": _extract_time(item),
            "url": _extract_url(item),
        })

    return result


# =========================================================
# GET NEWS
# =========================================================

@st.cache_data(ttl=60)
def get_eastmoney_news(limit=50):
    """Fetch live 7×24 global news directly from Eastmoney's official endpoint."""
    try:
        payload = _request_focus_news(page_size=max(100, limit))
        raw_items = _find_list(payload)
        if not raw_items:
            return [], "东方财富 7×24 全球直播接口没有返回新闻列表。"

        news_items = _parse_focus_news(raw_items)
        if not news_items:
            return [], "东方财富 7×24 全球直播接口返回数据，但没有解析出有效新闻。"
        return news_items[:limit], None
    except Exception as exc:
        return [], f"东方财富 7×24 全球直播：{exc}"


# Backward-compatible alias. The data source is Eastmoney, not Sina.
get_sina_news = get_eastmoney_news


# =========================================================
# LIVE MARKET SNAPSHOT
# =========================================================

YAHOO_CHART_API = "https://query1.finance.yahoo.com/v8/finance/chart/"

MARKET_SYMBOLS = {
    "纳斯达克": "^IXIC",
    "标普500": "^GSPC",
    "上证指数": "000001.SS",
    "深证成指": "399001.SZ",
    "韩国综合": "^KS11",
    "纳指期货": "NQ=F",
    "标普期货": "ES=F",
}

MARKET_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/152.0.0.0 Safari/537.36"
    ),
}


def _fetch_yahoo_quote(symbol):
    response = requests.get(
        YAHOO_CHART_API + symbol,
        params={"range": "1d", "interval": "1m", "includePrePost": "true"},
        headers=MARKET_HEADERS,
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()
    result = payload.get("chart", {}).get("result") or []
    if not result:
        raise RuntimeError("没有返回行情数据")

    meta = result[0].get("meta", {})
    price = meta.get("regularMarketPrice")
    previous = meta.get("previousClose")

    if price is None:
        closes = (result[0].get("indicators", {}).get("quote") or [{}])[0].get("close") or []
        values = [v for v in closes if v is not None]
        if values:
            price = values[-1]

    change = None
    if price is not None and previous not in (None, 0):
        change = price - previous
        change_pct = change / previous * 100
    else:
        change_pct = None

    return {
        "symbol": symbol,
        "price": price,
        "change": change,
        "change_pct": change_pct,
        "market_state": meta.get("marketState", ""),
        "currency": meta.get("currency", ""),
    }


@st.cache_data(ttl=60)
def get_market_snapshot():
    rows = []
    for name, symbol in MARKET_SYMBOLS.items():
        try:
            quote = _fetch_yahoo_quote(symbol)
            quote["name"] = name
            rows.append(quote)
        except Exception as exc:
            rows.append({
                "name": name,
                "symbol": symbol,
                "price": None,
                "change": None,
                "change_pct": None,
                "market_state": "",
                "currency": "",
                "error": str(exc),
            })
    return rows


# =========================================================
# EXPORT
# =========================================================

__all__ = [
    "get_dgs3mo", "get_dgs2", "get_dgs10", "get_dfii10", "get_sofr",
    "get_iorb", "get_effr", "get_rrp_rate", "get_eastmoney_news", "get_sina_news", "get_market_snapshot",
    "get_wresbal", "get_wtre_gen", "get_rrp_daily", "_fred_series",
]
