import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin


FRED_API_URL = "https://api.stlouisfed.org/fred/series/observations"


# =========================================================
# Generic FRED API
# =========================================================

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

    df = pd.DataFrame(data["observations"])

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
# 10Y Real Yield / Inflation
# =========================================================

@st.cache_data(ttl=3600)
def get_dfii10():
    return get_fred_series("DFII10")


# =========================================================
# Funding / Policy Rate Corridor
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
# News Helpers
# =========================================================

NEWS_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"
}


# =========================================================
# Sina Finance 7x24
# =========================================================

@st.cache_data(ttl=300)
def get_sina_news(limit=20):

    url = "https://finance.sina.com.cn/7x24/"

    try:
        response = requests.get(
            url,
            headers=NEWS_HEADERS,
            timeout=15
        )

        response.raise_for_status()

        response.encoding = response.apparent_encoding

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        news = []

        # -------------------------------------------------
        # Method 1:
        # Search page text for 7x24 live news items
        # -------------------------------------------------

        text_lines = [
            line.strip()
            for line in soup.get_text("\n").splitlines()
            if line.strip()
        ]

        for line in text_lines:

            # Typical Sina time format:
            # 08:02:16
            if len(line) >= 9 and line[2] == ":" and line[5] == ":":
                time_text = line[:8]
                title = line[9:].strip()

                if len(title) >= 4:

                    news.append({
                        "time": time_text,
                        "title": title,
                        "url": url
                    })

        # -------------------------------------------------
        # Remove duplicates
        # -------------------------------------------------

        unique_news = []
        seen = set()

        for item in news:

            key = (
                item["time"],
                item["title"]
            )

            if key not in seen:

                seen.add(key)
                unique_news.append(item)

        return unique_news[:limit]

    except Exception:
        return []


# =========================================================
# WSJ Public Headlines
# =========================================================

@st.cache_data(ttl=600)
def get_wsj_news(limit=12):

    urls = [
        "https://www.wsj.com/finance",
        "https://www.wsj.com/livecoverage"
    ]

    news = []
    seen = set()

    for page_url in urls:

        try:

            response = requests.get(
                page_url,
                headers=NEWS_HEADERS,
                timeout=15
            )

            response.raise_for_status()

            soup = BeautifulSoup(
                response.text,
                "html.parser"
            )

            # -------------------------------------------------
            # Collect links from page
            # -------------------------------------------------

            for link in soup.find_all("a"):

                href = link.get("href")

                if not href:
                    continue

                title = link.get_text(
                    " ",
                    strip=True
                )

                if not title:
                    continue

                # Absolute URL
                href = urljoin(
                    "https://www.wsj.com",
                    href
                )

                # Only WSJ article / live coverage links
                if "wsj.com" not in href:
                    continue

                if not (
                    "/finance/" in href
                    or "/livecoverage/" in href
                    or "/markets/" in href
                ):
                    continue

                # Filter out very short / navigation text
                if len(title) < 15:
                    continue

                # Avoid duplicate titles
                if title in seen:
                    continue

                seen.add(title)

                news.append({
                    "time": "",
                    "title": title,
                    "url": href
                })

                if len(news) >= limit:
                    break

        except Exception:
            continue

        if len(news) >= limit:
            break

    return news[:limit]
