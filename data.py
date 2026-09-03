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
# EASTMONEY 7×24 / FOCUS NEWS
# =========================================================

# 东方财富实时资讯页面
EASTMONEY_NEWS_URL = (
    "https://kuaixun.eastmoney.com/"
)

# 东方财富现成的「红字焦点快讯」
#
# 101 = 红字焦点快讯
# 102 = 7×24 全球直播
#
# 这里明确使用 101，
# 不抓全量 7×24，
# 不自己判断什么是重点。
EASTMONEY_FOCUS_URL = (
    "https://np-listapi.eastmoney.com/"
    "comm/web/getNewsByColumns"
)

EASTMONEY_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/152.0.0.0 Safari/537.36"
    ),
    "Referer": EASTMONEY_NEWS_URL,
    "Accept": (
        "application/json,text/plain,*/*"
    ),
}


# =========================================================
# FRED
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
# GENERIC JSON VALUE
# =========================================================

def _first_value(
    item,
    keys,
):

    if not isinstance(
        item,
        dict,
    ):
        return ""

    for key in keys:

        value = item.get(
            key
        )

        if value not in (
            None,
            "",
        ):
            return value

    return ""


# =========================================================
# EASTMONEY TITLE
# =========================================================

def _extract_eastmoney_title(
    item,
):

    value = _first_value(
        item,
        [
            "title",
            "Title",
            "showTitle",
            "newsTitle",
            "NewsTitle",
            "content",
            "Content",
        ],
    )

    return _clean_text(
        value
    )


# =========================================================
# EASTMONEY CONTENT
# =========================================================

def _extract_eastmoney_content(
    item,
):

    value = _first_value(
        item,
        [
            "content",
            "Content",
            "title",
            "Title",
            "showTitle",
            "newsTitle",
            "NewsTitle",
        ],
    )

    return _clean_text(
        value
    )


# =========================================================
# EASTMONEY TIME
# =========================================================

def _extract_eastmoney_time(
    item,
):

    value = _first_value(
        item,
        [
            "showTime",
            "ShowTime",
            "time",
            "Time",
            "ctime",
            "Ctime",
            "publishTime",
            "PublishTime",
            "updateTime",
            "UpdateTime",
        ],
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


# =========================================================
# EASTMONEY URL
# =========================================================

def _extract_eastmoney_url(
    item,
):

    value = _first_value(
        item,
        [
            "url",
            "Url",
            "URL",
            "newsUrl",
            "NewsUrl",
            "url_h5",
            "urlH5",
            "articleUrl",
            "ArticleUrl",
        ],
    )

    value = _clean_text(
        value
    )

    if (
        value.startswith(
            "http://"
        )
        or value.startswith(
            "https://"
        )
    ):
        return value

    return EASTMONEY_NEWS_URL


# =========================================================
# EASTMONEY REQUEST
# =========================================================

def _request_eastmoney_focus(
    page_size=100,
):

    # -----------------------------------------------------
    # 东方财富「红字焦点快讯」
    #
    # column = 101
    #
    # 不使用全量 102。
    # -----------------------------------------------------

    params = {
        "client": "web",
        "biz": "web",
        "column": "101",
        "pageSize": page_size,
        "pageIndex": 1,
        "req_trace": int(
            time.time() * 1000
        ),
    }

    response = requests.get(
        EASTMONEY_FOCUS_URL,
        params=params,
        headers=EASTMONEY_HEADERS,
        timeout=15,
    )

    response.raise_for_status()

    # -----------------------------------------------------
    # 正常 JSON
    # -----------------------------------------------------

    try:

        return response.json()

    except ValueError:

        pass

    # -----------------------------------------------------
    # 某些情况下可能返回 JSONP / 包装文本
    # -----------------------------------------------------

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
        "东方财富焦点快讯返回的数据格式无法解析。"
    )


# =========================================================
# FIND NEWS LIST
# =========================================================

def _find_news_list(
    data,
):

    if isinstance(
        data,
        list,
    ):
        return data

    if not isinstance(
        data,
        dict,
    ):
        return []

    # -----------------------------------------------------
    # 常见结构直接查找
    # -----------------------------------------------------

    direct_keys = [
        "list",
        "List",
        "data",
        "Data",
        "items",
        "Items",
        "news",
        "News",
        "rows",
        "Rows",
    ]

    for key in direct_keys:

        value = data.get(
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

            nested = _find_news_list(
                value
            )

            if nested:
                return nested

    # -----------------------------------------------------
    # 递归寻找 list[dict]
    # -----------------------------------------------------

    for value in data.values():

        if isinstance(
            value,
            dict,
        ):

            result = _find_news_list(
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
                    x,
                    dict,
                )
                for x in value
            ):
                return value

    return []


# =========================================================
# PARSE EASTMONEY ITEMS
# =========================================================

def _parse_eastmoney_items(
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

        title = _extract_eastmoney_title(
            item
        )

        content = _extract_eastmoney_content(
            item
        )

        if not title and not content:
            continue

        # -------------------------------------------------
        # 如果 title 没有，使用 content
        # -------------------------------------------------

        if not title:
            title = content

        if not content:
            content = title

        # -------------------------------------------------
        # 去重
        # -------------------------------------------------

        normalized = re.sub(
            r"\s+",
            "",
            (
                title
                or content
            ).lower(),
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
            _first_value(
                item,
                [
                    "id",
                    "ID",
                    "newsId",
                    "NewsId",
                    "art_code",
                    "ArtCode",
                ],
            )
        )

        # -------------------------------------------------
        # 时间
        # -------------------------------------------------

        news_time = _extract_eastmoney_time(
            item
        )

        # -------------------------------------------------
        # URL
        # -------------------------------------------------

        url = _extract_eastmoney_url(
            item
        )

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
# GET EASTMONEY FOCUS NEWS
# =========================================================

@st.cache_data(ttl=60)
def get_sina_news(
    limit=50,
):
    """
    保留原来的函数名称，
    这样 app.py 不需要修改。

    实际来源已经改成：
    东方财富「红字焦点快讯」

    不做：
    - 关键词评分
    - AI 判断
    - 自定义重要度
    - 全量 7×24 再自行筛选

    直接使用平台已经筛选好的焦点资讯。
    """

    try:

        data = _request_eastmoney_focus(
            page_size=max(
                100,
                limit,
            )
        )

        raw_items = _find_news_list(
            data
        )

        if not raw_items:

            return (
                [],
                "东方财富焦点快讯接口没有返回新闻列表。",
            )

        news_items = _parse_eastmoney_items(
            raw_items
        )

        if not news_items:

            return (
                [],
                "东方财富焦点快讯接口返回了数据，但没有解析出有效快讯。",
            )

        return (
            news_items[:limit],
            None,
        )

    except Exception as exc:

        return (
            [],
            f"东方财富焦点快讯：{exc}",
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
