from __future__ import annotations

import base64
import json
import zlib
from typing import Any

WATCHLIST_KEYS = ("market_search_us", "market_search_hk", "market_search_cn")
_SHORT_KEY = {
    "market_search_us": "u",
    "market_search_hk": "h",
    "market_search_cn": "c",
}
_MARKET = {
    "market_search_us": "US",
    "market_search_hk": "HK",
    "market_search_cn": "CN",
}
MAX_ITEMS_PER_MARKET = 40


def _clean_item(item: Any, market: str) -> dict[str, str] | None:
    if not isinstance(item, dict):
        return None
    symbol = str(item.get("symbol") or "").strip().upper()
    if not symbol:
        return None
    name = str(item.get("name") or symbol).strip()[:120] or symbol
    return {
        "symbol": symbol,
        "name": name,
        "exchange": "",
        "market": market,
    }


def normalize_watchlists(payload: Any) -> dict[str, list[dict[str, str]]]:
    result = {key: [] for key in WATCHLIST_KEYS}
    if not isinstance(payload, dict):
        return result

    for key in WATCHLIST_KEYS:
        raw_items = payload.get(key, [])
        if isinstance(raw_items, dict):
            raw_items = [raw_items]
        if not isinstance(raw_items, list):
            continue
        seen: set[str] = set()
        for raw in raw_items:
            item = _clean_item(raw, _MARKET[key])
            if not item or item["symbol"] in seen:
                continue
            seen.add(item["symbol"])
            result[key].append(item)
            if len(result[key]) >= MAX_ITEMS_PER_MARKET:
                break
    return result


def encode_watchlists(payload: Any) -> str:
    normalized = normalize_watchlists(payload)
    compact: dict[str, Any] = {"v": 2}
    for key in WATCHLIST_KEYS:
        rows = normalized[key]
        compact[_SHORT_KEY[key]] = [[row["symbol"], row["name"]] for row in rows]
    raw = json.dumps(compact, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    packed = zlib.compress(raw, level=9)
    token = base64.urlsafe_b64encode(packed).decode("ascii").rstrip("=")
    return "v2." + token


def _decode_v2(raw: str) -> dict[str, list[dict[str, str]]]:
    token = raw[3:]
    token += "=" * (-len(token) % 4)
    packed = base64.urlsafe_b64decode(token.encode("ascii"))
    compact = json.loads(zlib.decompress(packed).decode("utf-8"))
    if not isinstance(compact, dict) or compact.get("v") != 2:
        raise ValueError("unsupported watchlist payload")

    payload: dict[str, list[dict[str, str]]] = {key: [] for key in WATCHLIST_KEYS}
    reverse = {value: key for key, value in _SHORT_KEY.items()}
    for short_key, key in reverse.items():
        rows = compact.get(short_key, [])
        if not isinstance(rows, list):
            continue
        market = _MARKET[key]
        for row in rows[:MAX_ITEMS_PER_MARKET]:
            if not isinstance(row, list) or not row:
                continue
            symbol = str(row[0] or "").strip().upper()
            if not symbol:
                continue
            name = str(row[1] if len(row) > 1 else symbol).strip()[:120] or symbol
            payload[key].append({"symbol": symbol, "name": name, "exchange": "", "market": market})
    return normalize_watchlists(payload)


def decode_watchlists(raw: Any) -> dict[str, list[dict[str, str]]]:
    if raw is None:
        return {key: [] for key in WATCHLIST_KEYS}
    text = str(raw).strip()
    if not text:
        return {key: [] for key in WATCHLIST_KEYS}
    try:
        if text.startswith("v2."):
            return _decode_v2(text)
        # Backward compatibility with the original plain-JSON query parameter.
        return normalize_watchlists(json.loads(text))
    except Exception:
        return {key: [] for key in WATCHLIST_KEYS}
