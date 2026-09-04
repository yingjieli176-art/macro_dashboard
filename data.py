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

FRED_API_URL = (
    "https://api.stlouisfed.org/fred/series/observations"
)

FRED_API_KEY = st.secrets.get(
    "FRED_API_KEY",
    "",
)


# =========================================================
# NEWS
# =========================================================

# 第三方接口：
# type=101 = 东方财富「红字焦点快讯」
#
# 注意：
# 101 是平台已经定义好的「红字焦点快讯」
# 102 才是 7×24 全球直播全量。
#
# 这里明确只调用 101。
EASTMONEY_FOCUS_API = (
    "http://api.xcvts.cn/api/hotlist/eastmoney"
)

EASTMONEY_NEWS_URL = (
    "https://kuaixun.eastmoney.com/"
)

NEWS_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/152.0.0.0 Safari/537.36"
    ),
    "Referer": EASTMONEY_NEWS_URL,
    "Accept": (
        "application/json,"
        "text/plain,*/*"
    ),
}


# =========================================================
# FRED CORE
# =========================================================

def _fred_series(
    series_id,
):

    if not FRED_API_KEY:
        raise RuntimeError(
            "FRED_API_KEY 未设置。"
            "请在 Streamlit Secrets 中加入 FRED_API_KEY。"
        )

    params = {
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "sort_order": "asc",
    }

    response = requests.get(
        FRED_API_URL,
        params=params,
        timeout=8,
    )

    response.raise_for_status()

    payload = response.json()

    observations = payload.get(
        "observations",
        [],
    )

    rows = []

    for item in observations:

        value = item.get(
            "value"
        )

        if value in (
            None,
            "",
            ".",
        ):
            continue

        try:
            value = float(
                value
            )
        except (
            TypeError,
            ValueError,
        ):
            continue

        rows.append(
            {
                "observation_date": pd.to_datetime(
                    item["date"],
                    errors="coerce",
                ),
                series_id: value,
            }
        )

    df = pd.DataFrame(
        rows
    )

    if df.empty:
        raise RuntimeError(
            f"FRED {series_id} 没有返回有效数据。"
        )

    return (
        df
        .dropna(
            subset=[
                "observation_date"
            ]
        )
        .sort_values(
            "observation_date"
        )
    )


# =========================================================
# FRED SERIES
# =========================================================

@st.cache_data(ttl=3600)
def get_dgs3mo():
    return _fred_series(
        "DGS3MO"
    )


@st.cache_data(ttl=3600)
def get_dgs2():
    return _fred_series(
        "DGS2"
    )


@st.cache_data(ttl=3600)
def get_dgs10():
    return _fred_series(
        "DGS10"
    )


@st.cache_data(ttl=3600)
def get_dfii10():
    return _fred_series(
        "DFII10"
    )


@st.cache_data(ttl=3600)
def get_sofr():
    return _fred_series(
        "SOFR"
    )


@st.cache_data(ttl=3600)
def get_iorb():
    return _fred_series(
        "IORB"
    )


@st.cache_data(ttl=3600)
def get_effr():
    return _fred_series(
        "EFFR"
    )


@st.cache_data(ttl=3600)
def get_rrp_rate():
    return _fred_series(
        "RRPONTSYAWARD"
    )


# =========================================================
# TEXT CLEAN
# =========================================================

def _clean_text(
    value,
):

    if value is None:
        return ""

    text = html.unescape(
        str(value)
    )

    text = re.sub(
        r"<[^>]+>",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


# =========================================================
# JSON / NEWS LIST SEARCH
# =========================================================

def _find_list(
    obj,
):

    if isinstance(
        obj,
        list,
    ):
        return obj

    if not isinstance(
        obj,
        dict,
    ):
        return []

    # 常见字段
    for key in (
        "list",
        "List",
        "data",
        "Data",
        "items",
        "Items",
        "rows",
        "Rows",
        "news",
        "News",
        "fastNewsList",
        "FastNewsList",
    ):

        value = obj.get(
            key
        )

        if isinstance(
            value,
            list,
        ):
            return value

        if isinstance(
            value,
            dict,
        ):

            result = _find_list(
                value
            )

            if result:
                return result

    # 递归搜索
    for value in obj.values():

        if isinstance(
            value,
            dict,
        ):

            result = _find_list(
                value
            )

            if result:
                return result

        elif isinstance(
            value,
            list,
        ):

            if value and all(
                isinstance(
                    item,
                    dict,
                )
                for item in value
            ):
                return value

    return []


# =========================================================
# GET FIELD
# =========================================================

def _get_field(
    item,
    names,
):

    if not isinstance(
        item,
        dict,
    ):
        return ""

    for name in names:

        if name not in item:
            continue

        value = item.get(
            name
        )

        if value not in (
            None,
            "",
        ):
            return value

    return ""


# =========================================================
# TITLE
# =========================================================

def _extract_title(
    item,
):

    value = _get_field(
        item,
        [
            "title",
            "Title",
            "newsTitle",
            "NewsTitle",
            "showTitle",
            "ShowTitle",
            "art_title",
            "ArtTitle",
        ],
    )

    title = _clean_text(
        value
    )

    if title:
        return title

    content = _get_field(
        item,
        [
            "content",
            "Content",
            "text",
            "Text",
        ],
    )

    content = _clean_text(
        content
    )

    if not content:
        return ""

    # 兼容新浪式 〖标题〗正文
    match = re.match(
        r"^〖(.+?)〗",
        content,
        flags=re.DOTALL,
    )

    if match:
        return (
            match.group(1)
            .strip()
        )

    if len(content) <= 120:
        return content

    return (
        content[:120]
        + "..."
    )


# =========================================================
# CONTENT
# =========================================================

def _extract_content(
    item,
):

    value = _get_field(
        item,
        [
            "content",
            "Content",
            "rich_text",
            "RichText",
            "text",
            "Text",
            "title",
            "Title",
            "newsTitle",
            "NewsTitle",
        ],
    )

    return _clean_text(
        value
    )


# =========================================================
# TIME
# =========================================================

def _extract_time(
    item,
):

    value = _get_field(
        item,
        [
            "showTime",
            "ShowTime",
            "time",
            "Time",
            "createTime",
            "CreateTime",
            "create_time",
            "updateTime",
            "UpdateTime",
            "publishTime",
            "PublishTime",
            "ctime",
            "Ctime",
        ],
    )

    text = _clean_text(
        value
    )

    if not text:
        return ""

    match = re.search(
        r"(\d{1,2}:\d{2}(?::\d{2})?)",
        text,
    )

    if match:
        return match.group(1)

    return text


# =========================================================
# URL
# =========================================================

def _extract_url(
    item,
):

    value = _get_field(
        item,
        [
            "url",
            "URL",
            "Url",
            "newsUrl",
            "NewsUrl",
            "articleUrl",
            "ArticleUrl",
            "url_h5",
            "urlH5",
            "link",
            "Link",
        ],
    )

    url = _clean_text(
        value
    )

    if (
        url.startswith(
            "http://"
        )
        or url.startswith(
            "https://"
        )
    ):
        return url

    return EASTMONEY_NEWS_URL


# =========================================================
# ID
# =========================================================

def _extract_id(
    item,
):

    value = _get_field(
        item,
        [
            "id",
            "ID",
            "newsId",
            "NewsId",
            "art_code",
            "ArtCode",
            "code",
            "Code",
        ],
    )

    return str(
        value
        or ""
    )


# =========================================================
# REQUEST FOCUS NEWS
# =========================================================

def _request_focus_news(
    page_size=100,
):

    params = {
        "type": "101",
    }

    response = requests.get(
        EASTMONEY_FOCUS_API,
        params=params,
        headers=NEWS_HEADERS,
        timeout=5,
    )

    response.raise_for_status()

    # 正常 JSON
    try:
        return response.json()

    except ValueError:
        pass

    # JSONP / 包装文本兼容
    text = (
        response.text
        .strip()
    )

    first_brace = text.find(
        "{"
    )

    last_brace = text.rfind(
        "}"
    )

    if (
        first_brace >= 0
        and last_brace > first_brace
    ):

        json_text = text[
            first_brace:
            last_brace + 1
        ]

        return json.loads(
            json_text
        )

    raise RuntimeError(
        "东方财富红字焦点快讯返回的数据格式无法解析。"
    )


# =========================================================
# PARSE NEWS
# =========================================================

def _parse_focus_news(
    raw_items,
):

    result = []

    seen = set()

    for item in raw_items:

        if not isinstance(
            item,
            dict,
        ):
            continue

        title = _extract_title(
            item
        )

        content = _extract_content(
            item
        )

        if not title and not content:
            continue

        if not title:
            title = content

        if not content:
            content = title

        # 去重
        normalized = re.sub(
            r"\s+",
            "",
            (
                title
                + content
            ).lower(),
        )

        if not normalized:
            continue

        if normalized in seen:
            continue

        seen.add(
            normalized
        )

        result.append(
            {
                "id": _extract_id(
                    item
                ),
                "title": title,
                "content": content,
                "time": _extract_time(
                    item
                ),
                "url": _extract_url(
                    item
                ),
            }
        )

    return result


# =========================================================
# GET NEWS
# =========================================================

@st.cache_data(ttl=60)
def get_sina_news(
    limit=50,
):
    """
    为了兼容现有 app.py，
    函数名暂时保留 get_sina_news。

    实际数据源：
        东方财富红字焦点快讯

    type=101：
        平台已经筛选好的红字焦点消息

    不做：
        - 关键词评分
        - AI 判断
        - 自己定义重点
        - 从全量 7×24 中二次筛选
    """

    try:

        payload = _request_focus_news(
            page_size=max(
                100,
                limit,
            )
        )

        raw_items = _find_list(
            payload
        )

        if not raw_items:

            return (
                [],
                "东方财富红字焦点快讯接口没有返回新闻列表。",
            )

        news_items = _parse_focus_news(
            raw_items
        )

        if not news_items:

            return (
                [],
                "东方财富红字焦点快讯接口返回数据，但没有解析出有效新闻。",
            )

        return (
            news_items[:limit],
            None,
        )

    except Exception as exc:

        return (
            [],
            f"东方财富红字焦点快讯：{exc}",
        )


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
        params={
            "range": "1d",
            "interval": "1m",
            "includePrePost": "true",
        },
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
        timestamps = result[0].get("timestamp") or []
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
    "get_dgs3mo",
    "get_dgs2",
    "get_dgs10",
    "get_dfii10",
    "get_sofr",
    "get_iorb",
    "get_effr",
    "get_rrp_rate",
    "get_sina_news",
    "get_market_snapshot",
]
