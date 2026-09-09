import html
import json
import re
import time

import pandas as pd
import requests
import streamlit as st

FRED_API_URL = "https://api.stlouisfed.org/fred/series/observations"
FRED_API_KEY = st.secrets.get("FRED_API_KEY", "")
EASTMONEY_FOCUS_API = "https://np-weblist.eastmoney.com/comm/web/getFastNewsList"
EASTMONEY_NEWS_URL = "https://kuaixun.eastmoney.com/"
NEWS_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36", "Referer": EASTMONEY_NEWS_URL, "Accept": "application/json, text/plain, */*"}

def _fred_series(series_id):
    if not FRED_API_KEY:
        raise RuntimeError("FRED_API_KEY 未设置。请在 Streamlit Secrets 中加入 FRED_API_KEY。")
    params = {"series_id": series_id, "api_key": FRED_API_KEY, "file_type": "json", "sort_order": "asc"}
    response = requests.get(FRED_API_URL, params=params, timeout=4); response.raise_for_status()
    rows = []
    for item in response.json().get("observations", []):
        value = item.get("value")
        if value in (None, "", "."): continue
        try: value = float(value)
        except (TypeError, ValueError): continue
        rows.append({"observation_date": pd.to_datetime(item["date"], errors="coerce"), series_id: value})
    df = pd.DataFrame(rows)
    if df.empty: raise RuntimeError(f"FRED {series_id} 没有返回有效数据。")
    return df.dropna(subset=["observation_date"]).sort_values("observation_date")

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

def _clean_text(value):
    if value is None: return ""
    text = html.unescape(str(value)); text = re.sub(r"<[^>]+>", " ", text); text = re.sub(r"\s+", " ", text)
    return text.strip()

def _find_list(obj):
    if isinstance(obj, list): return obj
    if not isinstance(obj, dict): return []
    for key in ("list", "List", "data", "Data", "items", "Items", "rows", "Rows", "news", "News", "fastNewsList", "FastNewsList"):
        value = obj.get(key)
        if isinstance(value, list): return value
        if isinstance(value, dict):
            result = _find_list(value)
            if result: return result
    for value in obj.values():
        if isinstance(value, dict):
            result = _find_list(value)
            if result: return result
        elif isinstance(value, list) and value and all(isinstance(item, dict) for item in value): return value
    return []

def _get_field(item, names):
    if not isinstance(item, dict): return ""
    for name in names:
        if name in item and item.get(name) not in (None, ""): return item.get(name)
    return ""

def _extract_title(item):
    title = _clean_text(_get_field(item, ["title", "Title", "newsTitle", "NewsTitle", "showTitle", "ShowTitle", "art_title", "ArtTitle"]))
    if title: return title
    content = _clean_text(_get_field(item, ["content", "Content", "text", "Text"]))
    if not content: return ""
    match = re.match(r"^〖(.+?)〗", content, flags=re.DOTALL)
    return match.group(1).strip() if match else (content if len(content) <= 120 else content[:120] + "...")

def _extract_content(item):
    return _clean_text(_get_field(item, ["summary", "Summary", "digest", "Digest", "content", "Content", "rich_text", "RichText", "text", "Text", "title", "Title", "newsTitle", "NewsTitle"]))

def _extract_time(item):
    text = _clean_text(_get_field(item, ["showTime", "ShowTime", "time", "Time", "createTime", "CreateTime", "create_time", "updateTime", "UpdateTime", "publishTime", "PublishTime", "ctime", "Ctime"]))
    if not text: return ""
    match = re.search(r"(\d{1,2}:\d{2}(?::\d{2})?)", text)
    return match.group(1) if match else text

def _extract_url(item):
    url = _clean_text(_get_field(item, ["url", "URL", "Url", "newsUrl", "NewsUrl", "articleUrl", "ArticleUrl", "url_h5", "urlH5", "link", "Link"]))
    return url if url.startswith(("http://", "https://")) else EASTMONEY_NEWS_URL

def _extract_id(item): return str(_get_field(item, ["id", "ID", "newsId", "NewsId", "art_code", "ArtCode", "code", "Code"]) or "")

def _request_focus_news(page_size=100):
    params = {"client": "web", "biz": "web_724", "fastColumn": "102", "sortEnd": "", "pageSize": str(page_size), "req_trace": str(int(time.time() * 1000))}
    response = requests.get(EASTMONEY_FOCUS_API, params=params, headers=NEWS_HEADERS, timeout=10); response.raise_for_status()
    try: return response.json()
    except ValueError:
        text = response.text.strip(); first_brace = text.find("{"); last_brace = text.rfind("}")
        if first_brace >= 0 and last_brace > first_brace: return json.loads(text[first_brace:last_brace + 1])
        raise RuntimeError("东方财富 7×24 全球直播返回的数据格式无法解析。")

def _parse_focus_news(raw_items):
    result = []; seen = set()
    for item in raw_items:
        if not isinstance(item, dict): continue
        title = _extract_title(item); content = _extract_content(item)
        if not title and not content: continue
        if not title: title = content
        if not content: content = title
        normalized = re.sub(r"\s+", "", (title + content).lower())
        if not normalized or normalized in seen: continue
        seen.add(normalized); result.append({"id": _extract_id(item), "title": title, "content": content, "time": _extract_time(item), "url": _extract_url(item)})
    return result

@st.cache_data(ttl=60)
def get_eastmoney_news(limit=50):
    try:
        raw_items = _find_list(_request_focus_news(page_size=max(100, limit)))
        if not raw_items: return [], "东方财富 7×24 全球直播接口没有返回新闻列表。"
        news_items = _parse_focus_news(raw_items)
        if not news_items: return [], "东方财富 7×24 全球直播接口返回数据，但没有解析出有效新闻。"
        return news_items[:limit], None
    except Exception as exc: return [], f"东方财富 7×24 全球直播：{exc}"
get_sina_news = get_eastmoney_news

YAHOO_CHART_API = "https://query1.finance.yahoo.com/v8/finance/chart/"
MARKET_SYMBOLS = {"纳斯达克": "^IXIC", "标普500": "^GSPC", "上证指数": "000001.SS", "深证成指": "399001.SZ", "韩国综合": "^KS11", "纳指期货": "NQ=F", "标普期货": "ES=F"}
MARKET_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"}

def _fetch_yahoo_quote(symbol):
    response = requests.get(YAHOO_CHART_API + symbol, params={"range": "1d", "interval": "1m", "includePrePost": "true"}, headers=MARKET_HEADERS, timeout=10); response.raise_for_status()
    result = (response.json().get("chart", {}).get("result") or [])
    if not result: raise RuntimeError("没有返回行情数据")
    meta = result[0].get("meta", {}); price = meta.get("regularMarketPrice"); previous = meta.get("previousClose")
    if price is None:
        values = [v for v in ((result[0].get("indicators", {}).get("quote") or [{}])[0]).get("close") or [] if v is not None]
        if values: price = values[-1]
    change = price - previous if price is not None and previous not in (None, 0) else None; change_pct = change / previous * 100 if change is not None else None
    return {"symbol": symbol, "price": price, "change": change, "change_pct": change_pct, "market_state": meta.get("marketState", ""), "currency": meta.get("currency", "")}

@st.cache_data(ttl=60)
def get_market_snapshot():
    rows = []
    for name, symbol in MARKET_SYMBOLS.items():
        try:
            quote = _fetch_yahoo_quote(symbol); quote["name"] = name; rows.append(quote)
        except Exception as exc:
            rows.append({"name": name, "symbol": symbol, "price": None, "change": None, "change_pct": None, "market_state": "", "currency": "", "error": str(exc)})
    return rows

# =========================================================
# PLOTLY DATE AXIS PATCH
# =========================================================
from plotly.basedatatypes import BaseFigure
_original_update_layout = BaseFigure.update_layout

def _date_ticks(start, end):
    span_days = max(0, (end - start).days)
    if span_days > 1500: freq, fmt = "6MS", "%Y-%m"
    elif span_days > 730: freq, fmt = "3MS", "%Y-%m"
    elif span_days > 330: freq, fmt = "2MS", "%Y-%m"
    elif span_days > 150: freq, fmt = "MS", "%b"
    elif span_days > 75: freq, fmt = "2W", "%m/%d"
    elif span_days > 35: freq, fmt = "7D", "%m/%d"
    elif span_days > 14: freq, fmt = "4D", "%m/%d"
    elif span_days > 7: freq, fmt = "2D", "%m/%d"
    else: freq, fmt = "1D", "%m/%d"
    ticks = pd.date_range(start=start.normalize(), end=end.normalize(), freq=freq)
    if len(ticks) == 0 or ticks[-1] < end.normalize(): ticks = ticks.append(pd.DatetimeIndex([end.normalize()]))
    ticks = ticks[(ticks >= start.normalize()) & (ticks <= end.normalize())]
    if len(ticks) > 12:
        step = max(1, (len(ticks) - 1) // 11); ticks = ticks[::step]
        if ticks[-1] != end.normalize(): ticks = ticks.append(pd.DatetimeIndex([end.normalize()]))
    return ticks, fmt

def _update_layout_with_consistent_date_axes(self, *args, **kwargs):
    xaxis = kwargs.get("xaxis")
    if isinstance(xaxis, dict) and "hoverformat" in xaxis and self.data:
        dates = []
        for trace in self.data:
            if trace.x is not None: dates.extend(list(trace.x))
        parsed = pd.Series(pd.to_datetime(dates, errors="coerce")).dropna().sort_values().drop_duplicates()
        if not parsed.empty:
            start, end = parsed.iloc[0], parsed.iloc[-1]; ticks, tick_fmt = _date_ticks(start, end)
            new_kwargs = dict(kwargs); new_xaxis = dict(xaxis)
            new_xaxis.update(tickmode="array", tickvals=ticks, ticktext=[v.strftime(tick_fmt) for v in ticks], tickangle=0, tickfont=dict(size=9), automargin=False, ticklabeloverflow="hide past div")
            new_kwargs["xaxis"] = new_xaxis
            # Do not overwrite an explicitly configured top year axis.
            if "xaxis2" not in kwargs:
                years = []; year_text = []
                for year in sorted(parsed.dt.year.unique().tolist()):
                    year_dates = parsed[parsed.dt.year == year]; y0, y1 = year_dates.iloc[0], year_dates.iloc[-1]
                    years.append(y0 + (y1 - y0) / 2); year_text.append(str(year))
                new_kwargs["xaxis2"] = dict(overlaying="x", anchor="y", side="top", tickmode="array", tickvals=years, ticktext=year_text, showgrid=False, showline=False, ticks="", fixedrange=True, tickfont=dict(size=9), tickangle=0, automargin=False)
            margin = dict(new_kwargs.get("margin") or {}); margin.update(l=max(56, margin.get("l", 0)), r=max(64, margin.get("r", 0)), t=max(76, margin.get("t", 0)), b=max(48, margin.get("b", 0))); new_kwargs["margin"] = margin
            legend = new_kwargs.get("legend")
            if isinstance(legend, dict):
                legend = dict(legend); legend["y"] = min(1.08, float(legend.get("y", 1.02))); new_kwargs["legend"] = legend
            kwargs = new_kwargs
    return _original_update_layout(self, *args, **kwargs)

BaseFigure.update_layout = _update_layout_with_consistent_date_axes

st.markdown("""<style><nobr>.block-container { max-width: 2200px !important; width: 100% !important; }</nobr></style>""", unsafe_allow_html=True)
