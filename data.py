import html
import re

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

SINA_PAGE_URL = (
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
    "Referer": SINA_PAGE_URL,
    "Accept": (
        "application/json,text/plain,*/*"
    ),
}


# =========================================================
# FRED API
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
# FRED SERIES CACHE
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
# SINA PARSER
# =========================================================

def _extract_title(item):

    candidates = [
        item.get("content"),
        item.get("title"),
        item.get("rich_text"),
        item.get("text"),
        item.get("summary"),
    ]

    for value in candidates:

        if isinstance(
            value,
            dict,
        ):

            for key in (
                "content",
                "title",
                "text",
                "rich_text",
                "summary",
            ):

                if key in value:

                    text = _clean_text(
                        value[key]
                    )

                    if text:
                        return text

        elif isinstance(
            value,
            list,
        ):

            for part in value:

                text = _clean_text(
                    part
                )

                if text:
                    return text

        else:

            text = _clean_text(
                value
            )

            if text:
                return text

    return ""


def _extract_time(item):

    candidates = [
        item.get("create_time"),
        item.get("ctime"),
        item.get("time"),
        item.get("date"),
        item.get("pub_time"),
        item.get("pubTime"),
    ]

    for value in candidates:

        if value is None:
            continue

        text = _clean_text(
            value
        )

        match = re.search(
            r"\d{1,2}:\d{2}",
            text,
        )

        if match:
            return match.group(0)

    return ""


def _extract_url(item):

    keys = [
        "url",
        "link",
        "wapurl",
        "wap_url",
        "article_url",
        "articleUrl",
    ]

    for key in keys:

        value = item.get(key)

        if value:

            return str(
                value
            ).strip()

    return SINA_PAGE_URL


def _flatten_feed(payload):

    result = []

    def walk(obj):

        if isinstance(
            obj,
            dict,
        ):

            for key, value in obj.items():

                key_lower = str(
                    key
                ).lower()

                if (
                    key_lower
                    in {
                        "list",
                        "data",
                        "result",
                        "feed",
                        "items",
                        "messages",
                        "news",
                        "docs",
                    }
                ):

                    if isinstance(
                        value,
                        list,
                    ):

                        for item in value:

                            if isinstance(
                                item,
                                dict,
                            ):

                                result.append(
                                    item
                                )

                walk(value)

        elif isinstance(
            obj,
            list,
        ):

            for item in obj:

                if isinstance(
                    item,
                    dict,
                ):

                    result.append(
                        item
                    )

                walk(item)

    walk(payload)

    return result


# =========================================================
# NEWS IMPORTANCE
#
# 不是简单取前 N 条。
# 先抓取原始新闻 -> 评分 -> 过滤 -> 排序。
# =========================================================

HIGH_PRIORITY = {

    # -----------------------------------------------------
    # Fed / Monetary Policy
    # -----------------------------------------------------

    "fomc": 18,
    "美联储": 18,
    "联储": 16,
    "fed": 16,
    "powell": 18,
    "鲍威尔": 18,

    "降息": 16,
    "加息": 16,
    "利率决议": 18,
    "货币政策": 15,
    "央行": 12,

    # -----------------------------------------------------
    # US Macro
    # -----------------------------------------------------

    "cpi": 18,
    "核心cpi": 18,
    "pce": 18,
    "核心pce": 18,

    "非农": 18,
    "非农业": 18,
    "失业率": 15,
    "初请失业金": 13,

    "gdp": 16,
    "gdp增速": 16,

    "零售销售": 13,
    "ppi": 13,
    "ism": 13,

    "消费者信心": 12,
    "密歇根": 10,

    # -----------------------------------------------------
    # Treasury / Rates
    # -----------------------------------------------------

    "10年期美债": 15,
    "10年期国债": 15,
    "美债收益率": 15,
    "国债收益率": 12,

    "收益率曲线": 14,
    "倒挂": 14,
    "期限利差": 13,

    # -----------------------------------------------------
    # US Stock Market
    # -----------------------------------------------------

    "标普500": 13,
    "纳斯达克": 13,
    "道指": 12,
    "美股": 11,

    "熔断": 20,
    "暴跌": 17,
    "暴涨": 15,
    "大跌": 12,
    "大涨": 12,
    "崩盘": 18,
    "黑天鹅": 20,

    # -----------------------------------------------------
    # FX / Commodities
    # -----------------------------------------------------

    "美元指数": 13,
    "美元": 9,

    "黄金": 11,
    "原油": 11,
    "油价": 11,

    # -----------------------------------------------------
    # US Policy / Trade / Geopolitics
    # -----------------------------------------------------

    "关税": 17,
    "贸易战": 17,
    "特朗普": 14,
    "美国总统": 10,

    "制裁": 15,
    "出口管制": 15,

    "地缘政治": 15,
    "停火": 16,
    "战争": 18,
    "冲突": 13,

    # -----------------------------------------------------
    # China / Asia
    # -----------------------------------------------------

    "中国人民银行": 16,
    "人民银行": 15,

    "降准": 16,
    "存款准备金率": 16,
    "lpr": 14,

    "国常会": 13,
    "财政政策": 12,
    "刺激政策": 14,
    "房地产政策": 12,
}


MEDIUM_PRIORITY = {

    "英伟达": 6,
    "nvidia": 6,

    "苹果": 5,
    "微软": 5,

    "台积电": 7,

    "芯片": 6,
    "半导体": 6,

    "ai": 5,
    "人工智能": 5,

    "银行": 4,
    "能源": 4,
}


LOW_PRIORITY = {

    "目标价": -4,
    "机构上调": -3,
    "机构下调": -3,

    "评级": -3,
    "买入": -3,
    "卖出": -3,

    "盘中": -2,
    "收盘": -2,

    "个股": -5,
}


def _importance_score(title):

    text = title.lower()

    score = 0

    matched = []

    # High priority
    for keyword, weight in HIGH_PRIORITY.items():

        if keyword.lower() in text:

            score += weight

            matched.append(
                (
                    keyword,
                    weight,
                )
            )

    # Medium priority
    for keyword, weight in MEDIUM_PRIORITY.items():

        if keyword.lower() in text:

            score += weight

            matched.append(
                (
                    keyword,
                    weight,
                )
            )

    # Low priority
    for keyword, weight in LOW_PRIORITY.items():

        if keyword.lower() in text:

            score += weight

    # Significant movement language
    if re.search(
        r"(大幅|大涨|大跌|暴涨|暴跌|创纪录|历史新高|历史新低)",
        title,
    ):

        score += 5

    # Percentage movement
    if re.search(
        r"\b\d+(?:\.\d+)?\s*%\b",
        title,
    ):

        score += 1

    # Too short usually means low information density
    if len(title) < 8:

        score -= 4

    # Extremely long title gets slight penalty
    if len(title) > 220:

        score -= 2

    importance_tag = ""

    if matched:

        matched.sort(
            key=lambda x: x[1],
            reverse=True,
        )

        importance_tag = matched[0][0]

    return (
        score,
        importance_tag,
    )


# =========================================================
# DEDUPLICATION
# =========================================================

def _deduplicate_news(items):

    result = []

    seen = set()

    for item in items:

        title = item.get(
            "title",
            "",
        ).strip()

        if not title:
            continue

        normalized = re.sub(
            r"[\W_]+",
            "",
            title.lower(),
            flags=re.UNICODE,
        )

        if not normalized:
            continue

        if normalized in seen:
            continue

        seen.add(
            normalized
        )

        result.append(
            item
        )

    return result


# =========================================================
# GET SINA NEWS
# =========================================================

@st.cache_data(ttl=60)
def get_sina_news(limit=30):

    errors = []

    # -----------------------------------------------------
    # Sina primary
    # -----------------------------------------------------

    try:

        params = {
            "zhibo_id": "152",
            "tag_id": "0",
            "page": 1,
            "pagesize": 100,
        }

        response = requests.get(
            SINA_FEED_URL,
            params=params,
            headers=HEADERS,
            timeout=15,
        )

        response.raise_for_status()

        payload = response.json()

        raw_items = _flatten_feed(
            payload
        )

        parsed = []

        for item in raw_items:

            title = _extract_title(
                item
            )

            if not title:
                continue

            score, importance_tag = (
                _importance_score(
                    title
                )
            )

            parsed.append(
                {
                    "title": title,
                    "time": _extract_time(
                        item
                    ),
                    "url": _extract_url(
                        item
                    ),
                    "score": score,
                    "importance_tag": importance_tag,
                }
            )

        parsed = _deduplicate_news(
            parsed
        )

        # -------------------------------------------------
        # 关键：
        # 不是“最新30条”
        # 而是先经过重要性阈值。
        # -------------------------------------------------

        important = [
            item
            for item in parsed
            if item["score"] >= 10
        ]

        # 重要性高的优先
        important.sort(
            key=lambda x: x["score"],
            reverse=True,
        )

        if important:

            return (
                important[:limit],
                None,
            )

        errors.append(
            "新浪抓取成功，但当前快讯没有达到重点新闻阈值。"
        )

    except Exception as exc:

        errors.append(
            f"新浪7×24：{exc}"
        )

    # =====================================================
    # Eastmoney fallback
    # =====================================================

    try:

        fallback_url = (
            "https://np-weblist.eastmoney.com/"
            "comm/web/getFastNewsList"
        )

        params = {
            "client": "web",
            "biz": "web_news_col",
            "order": "1",
            "needInteract": "0",
            "pageSize": "100",
            "pageIndex": "1",
        }

        response = requests.get(
            fallback_url,
            params=params,
            headers=HEADERS,
            timeout=15,
        )

        response.raise_for_status()

        payload = response.json()

        raw_items = _flatten_feed(
            payload
        )

        parsed = []

        for item in raw_items:

            title = _extract_title(
                item
            )

            if not title:
                continue

            score, importance_tag = (
                _importance_score(
                    title
                )
            )

            parsed.append(
                {
                    "title": title,
                    "time": _extract_time(
                        item
                    ),
                    "url": _extract_url(
                        item
                    ),
                    "score": score,
                    "importance_tag": importance_tag,
                }
            )

        parsed = _deduplicate_news(
            parsed
        )

        important = [
            item
            for item in parsed
            if item["score"] >= 10
        ]

        important.sort(
            key=lambda x: x["score"],
            reverse=True,
        )

        if important:

            return (
                important[:limit],
                None,
            )

        errors.append(
            "东方财富备用源也没有筛选到重点新闻。"
        )

    except Exception as exc:

        errors.append(
            f"东方财富备用源：{exc}"
        )

    return (
        [],
        "；".join(errors),
    )


# =========================================================
# EXPORTS
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
