import re
import html
import json
import time

import streamlit as st
import pandas as pd
import requests


# =========================================================
# FRED
# =========================================================

FRED_API_URL = "https://api.stlouisfed.org/fred/series/observations"


def get_fred_series(series_id):

    api_key = st.secrets["FRED_API_KEY"]

    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "sort_order": "asc"
    }

    response = requests.get(
        FRED_API_URL,
        params=params,
        timeout=30
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
        errors="coerce"
    )

    return df[
        ["observation_date", series_id]
    ]


# =========================================================
# Treasury Yield
# =========================================================

@st.cache_data(ttl=3600)
def get_dgs3mo():
    return get_fred_series("DGS3MO")


@st.cache_data(ttl=3600)
def get_dgs2():
    return get_fred_series("DGS2")


@st.cache_data(ttl=3600)
def get_dgs10():
    return get_fred_series("DGS10")


# =========================================================
# 10Y Real Yield
# =========================================================

@st.cache_data(ttl=3600)
def get_dfii10():
    return get_fred_series("DFII10")


# =========================================================
# Policy Rate Corridor
# =========================================================

@st.cache_data(ttl=3600)
def get_sofr():
    return get_fred_series("SOFR")


@st.cache_data(ttl=3600)
def get_iorb():
    return get_fred_series("IORB")


@st.cache_data(ttl=3600)
def get_effr():
    return get_fred_series("EFFR")


@st.cache_data(ttl=3600)
def get_rrp_rate():
    return get_fred_series("RRPONTSYAWARD")


# =========================================================
# Sina Finance 7x24
# =========================================================

SINA_7X24_URL = (
    "https://zhibo.sina.com.cn/api/zhibo/feed"
)

SINA_7X24_PAGE_URL = (
    "https://finance.sina.com.cn/7x24/"
)


SINA_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/140.0 Safari/537.36"
    ),
    "Referer": SINA_7X24_PAGE_URL,
    "Accept": (
        "application/json, text/plain, */*"
    ),
    "Accept-Language": (
        "zh-CN,zh;q=0.9,en;q=0.8"
    ),
}


def clean_sina_text(text):

    if not text:
        return ""

    # Remove HTML tags
    text = re.sub(
        r"<[^>]+>",
        "",
        text
    )

    # Decode HTML entities
    text = html.unescape(text)

    # Remove Sina special brackets
    text = text.replace("〖", "")
    text = text.replace("〗", "")

    # Normalize whitespace
    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


def parse_sina_time(value):

    if not value:
        return ""

    value = str(value).strip()

    # Already looks like HH:MM:SS
    if re.match(
        r"^\d{2}:\d{2}:\d{2}$",
        value
    ):
        return value

    # Extract HH:MM:SS from a datetime
    match = re.search(
        r"(\d{2}:\d{2}:\d{2})",
        value
    )

    if match:
        return match.group(1)

    return value


@st.cache_data(ttl=60)
def get_sina_news(limit=20):

    timestamp = str(
        int(time.time() * 1000)
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

    try:

        response = requests.get(
            SINA_7X24_URL,
            params=params,
            headers=SINA_HEADERS,
            timeout=15
        )

        response.raise_for_status()

        text = response.text.strip()

        # -------------------------------------------------
        # Handle JSON / JSONP
        # -------------------------------------------------

        if text.startswith("{"):

            data = response.json()

        else:

            # Try to locate JSON object
            start = text.find("{")
            end = text.rfind("}")

            if start == -1 or end == -1:
                raise ValueError(
                    "新浪接口返回的内容不是有效 JSON"
                )

            data = json.loads(
                text[start:end + 1]
            )

        # -------------------------------------------------
        # Extract feed
        # -------------------------------------------------

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

            content = clean_sina_text(
                item.get(
                    "rich_text",
                    ""
                )
            )

            create_time = (
                item.get("create_time")
                or item.get("update_time")
                or item.get("pub_time")
                or ""
            )

            if not content:
                continue

            news.append(
                {
                    "time": parse_sina_time(
                        create_time
                    ),
                    "title": content,
                    "url": SINA_7X24_PAGE_URL
                }
            )

        if not news:
            raise ValueError(
                "新浪新闻数据为空"
            )

        return news[:limit], None

    except Exception as e:

        return [], str(e)


# =========================================================
# WSJ
# =========================================================

@st.cache_data(ttl=600)
def get_wsj_news(limit=10):

    url = "https://www.wsj.com/finance"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/140.0 Safari/537.36"
        ),
        "Accept-Language": (
            "en-US,en;q=0.9"
        ),
    }

    try:

        response = requests.get(
            url,
            headers=headers,
            timeout=15
        )

        response.raise_for_status()

        from bs4 import BeautifulSoup

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        news = []
        seen = set()

        for link in soup.find_all("a"):

            title = link.get_text(
                " ",
                strip=True
            )

            href = link.get("href")

            if not title or not href:
                continue

            if href.startswith("/"):
                href = (
                    "https://www.wsj.com"
                    + href
                )

            if "wsj.com" not in href:
                continue

            if len(title) < 20:
                continue

            if title in seen:
                continue

            bad_words = [
                "Sign In",
                "Subscribe",
                "Search",
                "Markets",
                "Quotes Lookup",
                "S&P 500 Stocks",
                "Dow Jones",
                "Nasdaq",
            ]

            if any(
                word.lower()
                in title.lower()
                for word in bad_words
            ):
                continue

            seen.add(title)

            news.append(
                {
                    "time": "",
                    "title": title,
                    "url": href
                }
            )

            if len(news) >= limit:
                break

        return news[:limit], None

    except Exception as e:

        return [], str(e)
