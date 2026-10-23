"""Market-scoped security lookup with Chinese names, codes and ETF support."""
import re

from macro_platform.request_runtime import http_get, request_budget
from macro_platform.watchlist_state import DEFAULT_WATCHLISTS

EASTMONEY_URL = "https://searchapi.eastmoney.com/api/suggest/get"
YAHOO_URLS = ("https://query1.finance.yahoo.com/v1/finance/search",
              "https://query2.finance.yahoo.com/v1/finance/search")
KEYS = {"US": "market_search_us", "HK": "market_search_hk", "CN": "market_search_cn"}
# Verified identifiers also work when remote search is unavailable. These
# provide names/codes only; quotes still come from the normal live providers.
KNOWN = {
    "HK": [("1810.HK", "小米集团-W", ("小米", "小米集团", "Xiaomi")),
           ("9988.HK", "阿里巴巴-W", ("阿里", "阿里巴巴", "Alibaba")),
           ("3690.HK", "美团-W", ("美团", "Meituan")),
           ("9618.HK", "京东集团-SW", ("京东", "JD")),
           ("1211.HK", "比亚迪股份", ("比亚迪", "BYD"))],
    "US": [("AAPL", "苹果", ("Apple",)), ("MSFT", "微软", ("Microsoft",)),
           ("TSLA", "特斯拉", ("Tesla",)), ("SPY", "标普500ETF", ()),
           ("QQQ", "纳斯达克100ETF", ())],
    "CN": [],
}


def _key(text):
    return re.sub(r"\s+", "", str(text)).casefold()


def local_matches(market, query):
    rows = [(r["symbol"], r["name"], ()) for r in DEFAULT_WATCHLISTS.get(KEYS.get(market), [])]
    rows += KNOWN.get(market, [])
    matches = []
    exact = False
    needle = _key(query)
    for symbol, name, aliases in rows:
        code = symbol.split(".")[0]
        tokens = [symbol, code, name, *aliases]
        if code.isdigit():
            tokens.append(code.lstrip("0") or "0")
            if market == "HK":
                tokens.extend((code.zfill(5), code.zfill(5) + ".HK"))
        normalized = [_key(t) for t in tokens]
        if needle and any(needle in t for t in normalized):
            is_exact = needle in normalized
            exact |= is_exact
            matches.append((not is_exact, {"symbol": symbol, "name": name, "exchange": market}))
    return [row for _, row in sorted(matches, key=lambda pair: pair[0])], exact


def eastmoney_matches(payload, market):
    table = payload.get("QuotationCodeTable")
    if not isinstance(table, dict) or not isinstance(table.get("Data"), (list, type(None))):
        raise ValueError("Invalid search response")
    results = []
    for row in table.get("Data") or []:
        code = str(row.get("Code") or "").upper()
        quote_id = str(row.get("QuoteID") or "")
        venue = str(row.get("MktNum") or quote_id.split(".")[0])
        if market == "HK" and venue == "116" and code.isdigit() and len(code) <= 5:
            symbol = code.zfill(4) + ".HK" if len(code) <= 4 else str(int(code)).zfill(4) + ".HK"
        elif market == "CN" and venue in {"0", "1"} and re.fullmatch(r"\d{6}", code):
            symbol = code + (".SS" if venue == "1" else ".SZ")
        elif market == "US" and venue in {"105", "106", "107"} and re.fullmatch(r"[A-Z][A-Z0-9.-]{0,14}", code):
            symbol = code.replace(".", "-")
        else:
            continue
        results.append({"symbol": symbol, "name": row.get("Name") or symbol, "exchange": market})
    return results


def yahoo_matches(payload, market):
    if not isinstance(payload.get("quotes"), list):
        raise ValueError("Invalid search response")
    results = []
    for row in payload["quotes"]:
        if str(row.get("quoteType") or "").upper() not in {"EQUITY", "ETF", "INDEX"}:
            continue
        symbol = str(row.get("symbol") or "").upper()
        if market == "HK":
            if not re.fullmatch(r"\d{4,5}\.HK", symbol):
                continue
            symbol = str(int(symbol[:-3])).zfill(4) + ".HK"
        elif market == "CN":
            if not re.fullmatch(r"\d{6}\.(SS|SZ)", symbol):
                continue
        elif market == "US":
            if not re.fullmatch(r"\^?[A-Z][A-Z0-9-]{0,14}", symbol):
                continue
        else:
            continue
        results.append({"symbol": symbol, "name": row.get("longname") or row.get("shortname") or symbol,
                        "exchange": row.get("exchange") or row.get("exchDisp") or market})
    return results


def search_securities(market, query, get=None):
    query = str(query or "").strip()
    if not query or market not in KEYS:
        return {"items": [], "unavailable": False}
    local, exact = local_matches(market, query)
    if exact:
        return {"items": local[:10], "unavailable": False}
    get = get or http_get
    calls = [(url, {"q": query, "quotesCount": 20, "newsCount": 0}, yahoo_matches)
             for url in YAHOO_URLS]
    domestic = (EASTMONEY_URL, {"input": query, "type": "14", "count": 20,
                              "token": "D43BF722C8E33BDC906FB85D85E326E8"}, eastmoney_matches)
    calls.insert(len(calls) if market == "US" else 0, domestic)
    succeeded = False
    with request_budget(7):
        for url, params, parse in calls:
            try:
                response = get(url, params=params, headers={"User-Agent": "Mozilla/5.0"}, timeout=(1.5, 2.0))
                response.raise_for_status()
                items = parse(response.json(), market)
                succeeded = True
            except Exception:
                continue
            if items:
                unique = {row["symbol"]: row for row in items}
                for row in local:
                    unique.setdefault(row["symbol"], row)
                return {"items": list(unique.values())[:10], "unavailable": False}
    return {"items": local[:10], "unavailable": not succeeded and not local}
