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


def get_fred_series(series_id):

    api_key = st.secrets["FRED_API_KEY"]

    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "sort_order": "asc",
    }

    response = requests.get(
        FRED_API_URL,
        params=params,
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    df = pd.DataFrame(
        data["observations"]
    )

    df["observation_date"] = pd.to_datetime(
        df["date"]
    )

    df[series_id] = pd.to_numeric(
        df["value"],
        errors="coerce",
    )

    return df[
        [
            "observation_date",
            series_id,
        ]
    ]


# =========================================================
# Treasury Yield
# =========================================================

@st.cache_data(ttl=3600)
def get_dgs3mo():

    return get_fred_series(
        "DGS3MO"
    )


@st.cache_data(ttl=3600)
def get_dgs2():

    return get_fred_series(
        "DGS2"
    )


@st.cache_data(ttl=3600)
def get_dgs10():

    return get_fred_series(
        "DGS10"
    )


# =========================================================
# 10Y Real Yield
# =========================================================

@st.cache_data(ttl=3600)
def get_dfii10():

    return get_fred_series(
        "DFII10"
    )


# =========================================================
# Policy Rate Corridor
# =========================================================

@st.cache_data(ttl=3600)
def get_sofr():

    return get_fred_series(
        "SOFR"
    )


@st.cache_data(ttl=3600)
def get_iorb():

    return get_fred_series(
        "IORB"
    )


@st.cache_data(ttl=3600)
def get_effr():

    return get_fred_series(
        "EFFR"
    )


@st.cache_data(ttl=3600)
def get_rrp_rate():

    return get_fred_series(
        "RRPONTSYAWARD"
    )


# =========================================================
# News common helpers
# =========================================================

NEWS_HEADERS = {

    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/140.0.0.0 "
        "Safari/537.36"
    ),

    "Accept": (
        "application/json, "
        "text/plain, "
        "*/*"
    ),

    "Accept-Language": (
        "zh-CN,zh;q=0.9,en;q=0.8"
    ),
}


def clean_news_text(text):

    if not text:
        return ""

    text = str(text)

    # Remove HTML
    text = re.sub(
        r"<[^>]+>",
        "",
        text,
    )

    # Decode HTML entities
    text = html.unescape(
        text
    )

    # Remove special brackets
    text = text.replace(
        "〖",
        "",
    )

    text = text.replace(
        "〗",
        "",
    )

    # Normalize whitespace
    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def parse_news_time(value):

    if not value:
        return ""

    value = str(
        value
    ).strip()

    # HH:MM:SS
    match = re.search(
        r"(\d{2}:\d{2}:\d{2})",
        value,
    )

    if match:

        return match.group(
            1
        )

    # HH:MM
    match = re.search(
        r"(\d{2}:\d{2})",
        value,
    )

    if match:

        return match.group(
            1
        )

    return value


# =========================================================
# Sina Finance 7x24
# =========================================================

SINA_7X24_URL = (
    "https://zhibo.sina.com.cn/api/zhibo/feed"
)

SINA_7X24_PAGE_URL = (
    "https://finance.sina.com.cn/7x24/"
)


def fetch_sina_news(limit=30):

    timestamp = str(
        int(
            time.time() * 1000
        )
    )

    params = {

        "page": 1,

        "page_size": limit,

        "zhibo_id": 152,

        "tag_id": 0,

        "dire": "f",

        "dpc": 1,

        "pagesize": limit,

        "_": timestamp,
    }


    headers = {
        **NEWS_HEADERS,
        "Referer": SINA_7X24_PAGE_URL,
    }


    response = requests.get(
        SINA_7X24_URL,
        params=params,
        headers=headers,
        timeout=15,
    )

    response.raise_for_status()


    text = response.text.strip()


    # -----------------------------------------------------
    # JSON
    # -----------------------------------------------------

    if text.startswith("{"):

        data = response.json()

    else:

        start = text.find("{")
        end = text.rfind("}")

        if (
            start == -1
            or end == -1
        ):

            raise ValueError(
                "新浪接口返回内容不是有效 JSON"
            )

        data = json.loads(
            text[
                start:end + 1
            ]
        )


    # -----------------------------------------------------
    # Extract feed
    # -----------------------------------------------------

    items = (
        data
        .get("result", {})
        .get("data", {})
        .get("feed", {})
        .get("list", [])
    )


    if not items:

        raise ValueError(
            "新浪接口返回成功，但没有新闻数据"
        )


    news = []


    for item in items:

        content = clean_news_text(
            item.get(
                "rich_text",
                "",
            )
        )


        create_time = (

            item.get(
                "create_time"
            )

            or item.get(
                "update_time"
            )

            or item.get(
                "pub_time"
            )

            or ""
        )


        if not content:

            continue


        news.append(
            {
                "time": parse_news_time(
                    create_time
                ),

                "title": content,

                "url": SINA_7X24_PAGE_URL,

                "source": "新浪财经",
            }
        )


    if not news:

        raise ValueError(
            "新浪新闻数据为空"
        )


    return news[:limit]


# =========================================================
# Eastmoney fallback
# =========================================================

EASTMONEY_URL = (
    "https://np-weblist.eastmoney.com/"
    "comm/web/getFastNewsList"
)

EASTMONEY_PAGE_URL = (
    "https://kuaixun.eastmoney.com/"
)


def fetch_eastmoney_news(limit=30):

    params = {

        "client": "web",

        "biz": "web_724",

        "fastColumn": "102",

        "sortEnd": "",

        "pageSize": limit,

        "req_trace": str(
            int(
                time.time() * 1000
            )
        ),
    }


    headers = {
        **NEWS_HEADERS,
        "Referer": EASTMONEY_PAGE_URL,
    }


    response = requests.get(
        EASTMONEY_URL,
        params=params,
        headers=headers,
        timeout=15,
    )

    response.raise_for_status()


    data = response.json()


    items = (
        data
        .get("data", {})
        .get("fastNewsList", [])
    )


    if not items:

        raise ValueError(
            "东方财富接口没有返回新闻"
        )


    news = []


    for item in items:

        title = clean_news_text(

            item.get(
                "title"
            )

            or item.get(
                "summary"
            )

            or item.get(
                "brief"
            )

            or ""
        )


        if not title:

            continue


        news.append(
            {
                "time": parse_news_time(

                    item.get(
                        "showTime"
                    )

                    or item.get(
                        "time"
                    )

                    or ""
                ),

                "title": title,

                "url": EASTMONEY_PAGE_URL,

                "source": "东方财富",
            }
        )


    if not news:

        raise ValueError(
            "东方财富新闻数据为空"
        )


    return news[:limit]


# =========================================================
# Public news function
# =========================================================

@st.cache_data(ttl=60)
def get_sina_news(limit=30):

    errors = []


    # =====================================================
    # Primary: Sina
    # =====================================================

    try:

        news = fetch_sina_news(
            limit=limit
        )

        if news:

            return news, None

    except Exception as e:

        errors.append(
            f"新浪：{e}"
        )


    # =====================================================
    # Fallback: Eastmoney
    # =====================================================

    try:

        news = fetch_eastmoney_news(
            limit=limit
        )

        if news:

            return news, None

    except Exception as e:

        errors.append(
            f"东方财富：{e}"
        )


    # =====================================================
    # Both failed
    # =====================================================

    return (
        [],
        "；".join(errors)
    )
