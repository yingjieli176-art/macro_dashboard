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
# SINA 7×24
# =========================================================

SINA_FEED_URL = (
    "https://zhibo.sina.com.cn/api/zhibo/feed"
)

SINA_7X24_URL = (
    "https://finance.sina.com.cn/7x24/"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/152.0.0.0 Safari/537.36"
    ),
    "Referer": SINA_7X24_URL,
    "Accept": (
        "application/json,text/plain,*/*"
    ),
}


# =========================================================
# FRED
# =========================================================

def _fred_series(series_id):

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
        timeout=20,
    )

    response.raise_for_status()

    payload = response.json()

    observations = payload.get(
        "observations",
        [],
    )

    rows = []

    for item in observations:

        value = item.get("value")

        if value in (
            None,
            "",
            ".",
        ):
            continue

        try:
            value = float(value)

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

    df = pd.DataFrame(rows)

    if df.empty:
        raise RuntimeError(
            f"FRED {series_id} 没有返回有效数据。"
        )

    return (
        df
        .dropna(
            subset=["observation_date"]
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
    return _fred_series("DGS3MO")


@st.cache_data(ttl=3600)
def get_dgs2():
    return _fred_series("DGS2")


@st.cache_data(ttl=3600)
def get_dgs10():
    return _fred_series("DGS10")


@st.cache_data(ttl=3600)
def get_dfii10():
    return _fred_series("DFII10")


@st.cache_data(ttl=3600)
def get_sofr():
    return _fred_series("SOFR")


@st.cache_data(ttl=3600)
def get_iorb():
    return _fred_series("IORB")


@st.cache_data(ttl=3600)
def get_effr():
    return _fred_series("EFFR")


@st.cache_data(ttl=3600)
def get_rrp_rate():
    return _fred_series("RRPONTSYAWARD")


# =========================================================
# TEXT CLEAN
# =========================================================

def _clean_text(value):

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
# SINA NEWS TEXT
# =========================================================

def _extract_title(content):

    content = _clean_text(
        content
    )

    if not content:
        return ""

    # 新浪7×24很多消息格式：
    #
    # 〖标题〗正文
    #
    match = re.match(
        r"^〖(.+?)〗",
        content,
        flags=re.DOTALL,
    )

    if match:
        return match.group(1).strip()

    # 没有标题符号时，直接使用前面的句子
    if len(content) <= 120:
        return content

    return content[:120] + "..."


def _extract_time(item):

    value = item.get(
        "create_time"
    )

    if not value:
        value = item.get(
            "update_time",
            "",
        )

    text = _clean_text(
        value
    )

    if not text:
        return ""

    # 例如：
    # 2026-09-03 13:21:30
    # 13:21:30
    # 13:21
    match = re.search(
        r"(\d{1,2}:\d{2}(?::\d{2})?)",
        text,
    )

    if match:
        return match.group(1)

    return text


def _extract_content(item):

    for key in (
        "rich_text",
        "content",
        "title",
        "text",
    ):

        value = item.get(
            key
        )

        if value:

            text = _clean_text(
                value
            )

            if text:
                return text

    return ""


# =========================================================
# SINA FEED REQUEST
# =========================================================

def _request_sina_feed(
    page_size=100,
):

    params = {
        "page": 1,
        "page_size": page_size,
        "zhibo_id": 152,
        "tag_id": 0,
        "dire": "f",
        "dpc": 1,
        "pagesize": page_size,
        "type": 1,
        "_": int(
            time.time() * 1000
        ),
    }

    response = requests.get(
        SINA_FEED_URL,
        params=params,
        headers=HEADERS,
        timeout=15,
    )

    response.raise_for_status()

    # 正常 JSON
    try:
        return response.json()

    except ValueError:
        pass

    # 有些情况下新浪会返回 JSONP
    text = response.text.strip()

    # 尝试从 JSONP 中截取 JSON
    first_brace = text.find("{")
    last_brace = text.rfind("}")

    if (
        first_brace >= 0
        and last_brace > first_brace
    ):

        json_text = text[
            first_brace:last_brace + 1
        ]

        return json.loads(
            json_text
        )

    raise RuntimeError(
        "新浪7×24返回的数据格式无法解析。"
    )


# =========================================================
# GET RAW SINA LIST
# =========================================================

def _get_sina_raw_list():

    data = _request_sina_feed(
        page_size=100
    )

    try:

        items = (
            data
            ["result"]
            ["data"]
            ["feed"]
            ["list"]
        )

    except (
        KeyError,
        TypeError,
    ):

        raise RuntimeError(
            "新浪7×24接口结构发生变化，"
            "找不到 result.data.feed.list。"
        )

    if not isinstance(
        items,
        list,
    ):

        raise RuntimeError(
            "新浪7×24没有返回新闻列表。"
        )

    return items


# =========================================================
# IMPORTANT:
#
# 新浪公开 feed 本身没有稳定暴露给我们的
# “焦点 typeid=9”字段。
#
# 因此这里不再自己做关键词评分。
#
# 优先使用新浪返回的原始排序。
#
# 这意味着：
#   新浪排在前面的 → 我们排前面
#   新浪新增的      → 自动进入
#   新浪删除/更新的 → 自动刷新
#
# 不进行二次“AI判断重点”。
# =========================================================


def _parse_sina_items(
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

        content = _extract_content(
            item
        )

        if not content:
            continue

        # -------------------------------------------------
        # 去掉重复消息
        # -------------------------------------------------

        normalized = re.sub(
            r"\s+",
            "",
            content.lower(),
        )

        if not normalized:
            continue

        if normalized in seen:
            continue

        seen.add(
            normalized
        )

        # -------------------------------------------------
        # ID
        # -------------------------------------------------

        news_id = str(
            item.get(
                "id",
                "",
            )
        )

        # -------------------------------------------------
        # 新浪原始时间
        # -------------------------------------------------

        news_time = _extract_time(
            item
        )

        # -------------------------------------------------
        # 标题
        # -------------------------------------------------

        title = _extract_title(
            content
        )

        # -------------------------------------------------
        # URL
        #
        # 新浪feed通常不会给每条直接URL，
        # 所以使用7×24主页作为跳转入口。
        # -------------------------------------------------

        url = SINA_7X24_URL

        result.append(
            {
                "id": news_id,
                "title": title,
                "content": content,
                "time": news_time,
                "url": url,
            }
        )

    return result


# =========================================================
# GET SINA 7×24
# =========================================================

@st.cache_data(ttl=60)
def get_sina_news(
    limit=50,
):

    try:

        raw_items = (
            _get_sina_raw_list()
        )

        news_items = (
            _parse_sina_items(
                raw_items
            )
        )

        if not news_items:

            return (
                [],
                "新浪7×24接口返回了数据，但没有有效快讯。",
            )

        # -------------------------------------------------
        # 直接使用新浪自己的顺序
        #
        # 不做关键词评分
        # 不做自己的“重点判断”
        # -------------------------------------------------

        return (
            news_items[:limit],
            None,
        )

    except Exception as exc:

        return (
            [],
            f"新浪7×24：{exc}",
        )


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
]
