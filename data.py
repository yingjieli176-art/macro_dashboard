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
# NEWS
# =========================================================

SINA_FEED_URL = (
    "https://zhibo.sina.com.cn/api/zhibo/feed"
)

SINA_PAGE_URL = (
    "https://finance.sina.com.cn/7x24/"
)

EASTMONEY_FEED_URL = (
    "https://np-weblist.eastmoney.com/"
    "comm/web/getFastNewsList"
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
# NEWS FIELD EXTRACTION
# =========================================================

def _extract_title(item):

    candidates = [
        item.get("rich_text"),
        item.get("content"),
        item.get("title"),
        item.get("text"),
        item.get("summary"),
    ]

    for value in candidates:

        if isinstance(
            value,
            dict,
        ):

            for key in (
                "rich_text",
                "content",
                "title",
                "text",
                "summary",
            ):

                if key not in value:
                    continue

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


# =========================================================
# GENERIC FEED FLATTENER
# =========================================================

def _flatten_feed(payload):

    result = []

    def walk(obj):

        if isinstance(
            obj,
            dict,
        ):

            # 如果本身已经像一条新闻
            if any(
                key in obj
                for key in (
                    "rich_text",
                    "content",
                    "title",
                    "text",
                )
            ):
                result.append(obj)

            for value in obj.values():
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
                    walk(item)

    walk(payload)

    return result


# =========================================================
# IMPORTANCE KEYWORDS
#
# 分数越高越重要。
# =========================================================

HIGH_PRIORITY = {

    # -----------------------------------------------------
    # Fed / Monetary Policy
    # -----------------------------------------------------

    "fomc": 20,
    "美联储": 20,
    "联储": 17,
    "fed": 17,

    "powell": 20,
    "鲍威尔": 20,

    "利率决议": 20,
    "降息": 18,
    "加息": 18,
    "降准": 18,

    "货币政策": 17,
    "央行": 14,

    # -----------------------------------------------------
    # Inflation / Employment / Macro
    # -----------------------------------------------------

    "核心cpi": 20,
    "cpi": 19,

    "核心pce": 20,
    "pce": 19,

    "非农": 20,
    "非农业": 20,

    "失业率": 17,
    "初请失业金": 15,

    "gdp": 18,
    "gdp增速": 18,

    "ppi": 15,
    "零售销售": 15,

    "ism": 15,
    "消费者信心": 14,
    "密歇根": 12,

    # -----------------------------------------------------
    # Treasury / Interest Rate
    # -----------------------------------------------------

    "10年期美债": 18,
    "10年期国债": 18,
    "美债收益率": 18,
    "国债收益率": 15,

    "收益率曲线": 17,
    "期限利差": 16,
    "倒挂": 17,

    "美债": 12,
    "国债": 10,

    "利率": 9,

    # -----------------------------------------------------
    # US Equity Market
    # -----------------------------------------------------

    "标普500": 15,
    "标普": 12,

    "纳斯达克": 15,
    "纳指": 13,

    "道指": 13,

    "美股": 12,

    "熔断": 25,
    "崩盘": 23,
    "黑天鹅": 23,

    "暴跌": 20,
    "暴涨": 18,

    "大跌": 15,
    "大涨": 15,

    # -----------------------------------------------------
    # FX / Commodities
    # -----------------------------------------------------

    "美元指数": 16,
    "美元": 9,

    "黄金": 13,
    "金价": 13,

    "原油": 13,
    "油价": 13,

    # -----------------------------------------------------
    # Trade / US Policy
    # -----------------------------------------------------

    "关税": 20,
    "贸易战": 20,

    "特朗普": 17,
    "美国总统": 12,

    "制裁": 17,
    "出口管制": 17,

    # -----------------------------------------------------
    # Geopolitics
    # -----------------------------------------------------

    "战争": 23,
    "停火": 20,
    "冲突": 17,

    "地缘政治": 18,

    # -----------------------------------------------------
    # China Macro
    # -----------------------------------------------------

    "中国人民银行": 19,
    "人民银行": 17,

    "存款准备金率": 18,
    "lpr": 16,

    "国常会": 16,
    "财政政策": 15,
    "刺激政策": 16,
    "房地产政策": 14,
}


MEDIUM_PRIORITY = {

    "英伟达": 7,
    "nvidia": 7,

    "苹果": 6,
    "微软": 6,

    "台积电": 8,

    "芯片": 7,
    "半导体": 7,

    "ai": 6,
    "人工智能": 6,

    "银行": 5,
    "能源": 5,

    "科技股": 5,
    "科技": 4,
}


LOW_PRIORITY = {

    # 普通个股资讯
    "目标价": -5,
    "机构上调": -4,
    "机构下调": -4,

    "评级": -5,
    "买入": -4,
    "卖出": -4,

    # 普通盘面信息
    "盘中": -2,
    "收盘": -2,

    # 个股新闻通常优先级较低
    "个股": -6,
}


# =========================================================
# IMPORTANCE SCORE
# =========================================================

def _importance_score(title):

    text = title.lower()

    score = 0

    matched = []

    # -----------------------------------------------------
    # High priority
    # -----------------------------------------------------

    for keyword, weight in HIGH_PRIORITY.items():

        if keyword.lower() in text:

            score += weight

            matched.append(
                (
                    keyword,
                    weight,
                )
            )

    # -----------------------------------------------------
    # Medium priority
    # -----------------------------------------------------

    for keyword, weight in MEDIUM_PRIORITY.items():

        if keyword.lower() in text:

            score += weight

            matched.append(
                (
                    keyword,
                    weight,
                )
            )

    # -----------------------------------------------------
    # Low priority
    # -----------------------------------------------------

    for keyword, weight in LOW_PRIORITY.items():

        if keyword.lower() in text:

            score += weight

    # -----------------------------------------------------
    # Significant market movement
    # -----------------------------------------------------

    movement_words = [
        "大幅",
        "大涨",
        "大跌",
        "暴涨",
        "暴跌",
        "创纪录",
        "历史新高",
        "历史新低",
        "创历史",
        "刷新纪录",
    ]

    movement_hit = False

    for word in movement_words:

        if word in title:

            score += 5
            movement_hit = True
            break

    # -----------------------------------------------------
    # Percentage
    # -----------------------------------------------------

    if re.search(
        r"\d+(?:\.\d+)?\s*%",
        title,
    ):

        score += 2

    # -----------------------------------------------------
    # Number / amount
    # -----------------------------------------------------

    if re.search(
        r"\d+(?:\.\d+)?\s*(?:万亿|千亿|亿|万亿美元|亿美元|亿元)",
        title,
    ):

        score += 2

    # -----------------------------------------------------
    # Very short title
    # -----------------------------------------------------

    if len(title) < 8:
        score -= 4

    # -----------------------------------------------------
    # Extremely long title
    # -----------------------------------------------------

    if len(title) > 220:
        score -= 2

    # -----------------------------------------------------
    # Determine tag
    # -----------------------------------------------------

    importance_tag = ""

    if matched:

        matched.sort(
            key=lambda x: x[1],
            reverse=True,
        )

        importance_tag = matched[0][0]

    elif movement_hit:

        importance_tag = "市场异动"

    return (
        score,
        importance_tag,
    )


# =========================================================
# DEDUPLICATION
# =========================================================

def _normalize_title(title):

    text = title.lower()

    text = re.sub(
        r"[\W_]+",
        "",
        text,
        flags=re.UNICODE,
    )

    return text


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

        normalized = _normalize_title(
            title
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
# DIVERSITY CONTROL
#
# 避免30条全部都是：
# 美联储 / 美股 / 英伟达
#
# 让宏观、利率、市场、商品、政策、
# 地缘政治尽量都有覆盖。
# =========================================================

def _classify_news(title):

    text = title.lower()

    if any(
        x in text
        for x in (
            "美联储",
            "fomc",
            "powell",
            "鲍威尔",
            "降息",
            "加息",
            "利率决议",
            "货币政策",
        )
    ):
        return "fed"

    if any(
        x in text
        for x in (
            "cpi",
            "pce",
            "非农",
            "失业率",
            "gdp",
            "ppi",
            "零售销售",
            "ism",
        )
    ):
        return "macro"

    if any(
        x in text
        for x in (
            "美债",
            "国债",
            "收益率",
            "期限利差",
            "收益率曲线",
            "倒挂",
        )
    ):
        return "rates"

    if any(
        x in text
        for x in (
            "标普",
            "标普500",
            "纳斯达克",
            "纳指",
            "道指",
            "美股",
            "熔断",
            "崩盘",
        )
    ):
        return "equity"

    if any(
        x in text
        for x in (
            "美元",
            "美元指数",
            "黄金",
            "原油",
            "油价",
        )
    ):
        return "fx_commodity"

    if any(
        x in text
        for x in (
            "关税",
            "贸易战",
            "特朗普",
            "制裁",
            "出口管制",
        )
    ):
        return "policy"

    if any(
        x in text
        for x in (
            "战争",
            "停火",
            "冲突",
            "地缘政治",
        )
    ):
        return "geopolitics"

    if any(
        x in text
        for x in (
            "人民银行",
            "降准",
            "lpr",
            "国常会",
            "财政政策",
            "房地产政策",
        )
    ):
        return "china"

    if any(
        x in text
        for x in (
            "英伟达",
            "nvidia",
            "苹果",
            "微软",
            "台积电",
            "芯片",
            "半导体",
            "人工智能",
        )
    ):
        return "technology"

    return "other"


def _select_diverse_news(
    items,
    target=20,
    maximum=30,
):

    if not items:
        return []

    # -----------------------------------------------------
    # 已经按照分数排序
    # -----------------------------------------------------

    selected = []

    category_count = {}

    # 第一轮：
    # 高分优先，同时避免单一类别霸占全部位置。
    for item in items:

        category = _classify_news(
            item["title"]
        )

        count = category_count.get(
            category,
            0,
        )

        # 单一类别最多先占 5 条
        if count >= 5:
            continue

        selected.append(
            item
        )

        category_count[category] = (
            count + 1
        )

        if len(selected) >= maximum:
            break

    # -----------------------------------------------------
    # 如果还不到20条，再放宽类别限制
    # -----------------------------------------------------

    if len(selected) < target:

        selected_keys = {
            _normalize_title(
                item["title"]
            )
            for item in selected
        }

        for item in items:

            key = _normalize_title(
                item["title"]
            )

            if key in selected_keys:
                continue

            selected.append(
                item
            )

            selected_keys.add(
                key
            )

            if len(selected) >= target:
                break

    return selected[:maximum]


# =========================================================
# PARSE RAW NEWS
# =========================================================

def _parse_news_items(raw_items):

    parsed = []

    for item in raw_items:

        if not isinstance(
            item,
            dict,
        ):
            continue

        title = _extract_title(
            item
        )

        if not title:
            continue

        score, tag = (
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
                "importance_tag": tag,
            }
        )

    return _deduplicate_news(
        parsed
    )


# =========================================================
# SINA NEWS
# =========================================================

def _get_sina_news_raw():

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

    return raw_items


# =========================================================
# EASTMONEY FALLBACK
# =========================================================

def _get_eastmoney_news_raw():

    params = {
        "client": "web",
        "biz": "web_news_col",
        "order": "1",
        "needInteract": "0",
        "pageSize": "100",
        "pageIndex": "1",
    }

    response = requests.get(
        EASTMONEY_FEED_URL,
        params=params,
        headers=HEADERS,
        timeout=15,
    )

    response.raise_for_status()

    payload = response.json()

    raw_items = _flatten_feed(
        payload
    )

    return raw_items


# =========================================================
# FINAL NEWS FUNCTION
# =========================================================

@st.cache_data(ttl=60)
def get_sina_news(limit=30):

    errors = []

    # =====================================================
    # 1. 新浪主源
    # =====================================================

    try:

        raw_items = _get_sina_news_raw()

        parsed = _parse_news_items(
            raw_items
        )

        if parsed:

            # -------------------------------------------------
            # 第一层：真正重点
            # -------------------------------------------------

            important = [
                item
                for item in parsed
                if item["score"] >= 10
            ]

            important.sort(
                key=lambda x: x["score"],
                reverse=True,
            )

            # -------------------------------------------------
            # 第二层：重要市场新闻
            #
            # 如果真正重点不足20条，
            # 扩展到 >=6。
            # -------------------------------------------------

            if len(important) < 20:

                medium = [
                    item
                    for item in parsed
                    if item["score"] >= 6
                ]

                medium.sort(
                    key=lambda x: x["score"],
                    reverse=True,
                )

                # 合并并去重
                combined = (
                    important
                    + medium
                )

                combined = _deduplicate_news(
                    combined
                )

                combined.sort(
                    key=lambda x: x["score"],
                    reverse=True,
                )

                important = combined

            # -------------------------------------------------
            # 第三层：
            # 如果仍不足20条，再放宽到>=4。
            #
            # 这里只是为了避免新闻栏太空，
            # 不是简单取最新20条。
            # -------------------------------------------------

            if len(important) < 20:

                broad = [
                    item
                    for item in parsed
                    if item["score"] >= 4
                ]

                broad.sort(
                    key=lambda x: x["score"],
                    reverse=True,
                )

                combined = (
                    important
                    + broad
                )

                combined = _deduplicate_news(
                    combined
                )

                combined.sort(
                    key=lambda x: x["score"],
                    reverse=True,
                )

                important = combined

            # -------------------------------------------------
            # 最终多主题筛选
            # -------------------------------------------------

            selected = _select_diverse_news(
                important,
                target=20,
                maximum=max(
                    30,
                    limit,
                ),
            )

            if selected:

                return (
                    selected,
                    None,
                )

        errors.append(
            "新浪7×24没有筛选到足够的重点新闻。"
        )

    except Exception as exc:

        errors.append(
            f"新浪7×24：{exc}"
        )

    # =====================================================
    # 2. 东方财富备用源
    # =====================================================

    try:

        raw_items = (
            _get_eastmoney_news_raw()
        )

        parsed = _parse_news_items(
            raw_items
        )

        if parsed:

            important = [
                item
                for item in parsed
                if item["score"] >= 6
            ]

            important.sort(
                key=lambda x: x["score"],
                reverse=True,
            )

            if len(important) < 20:

                important = [
                    item
                    for item in parsed
                    if item["score"] >= 4
                ]

                important.sort(
                    key=lambda x: x["score"],
                    reverse=True,
                )

            selected = _select_diverse_news(
                important,
                target=20,
                maximum=max(
                    30,
                    limit,
                ),
            )

            if selected:

                return (
                    selected,
                    None,
                )

        errors.append(
            "东方财富备用源也没有筛选到足够的重点新闻。"
        )

    except Exception as exc:

        errors.append(
            f"东方财富备用源：{exc}"
        )

    # =====================================================
    # 3. 全部失败
    # =====================================================

    return (
        [],
        "；".join(errors),
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
