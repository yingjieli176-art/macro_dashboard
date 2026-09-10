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
WATCHLIST_SCHEMA_VERSION = 3
DEFAULT_WATCHLIST_REVISION = 1

DEFAULT_WATCHLISTS = {
    "market_search_us": [
        {"symbol": "NVDA", "name": "英伟达"},
        {"symbol": "NBIS", "name": "Nebius"},
        {"symbol": "^NDX", "name": "纳斯达克100"},
    ],
    "market_search_hk": [
        {"symbol": "0700.HK", "name": "腾讯控股"},
        {"symbol": "0189.HK", "name": "东岳集团"},
    ],
    "market_search_cn": [
        {"symbol": "600160.SS", "name": "巨化股份"},
        {"symbol": "600021.SS", "name": "上海电力"},
    ],
}


def _empty() -> dict[str, list[dict[str, str]]]:
    return {key: [] for key in WATCHLIST_KEYS}


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
    result = _empty()
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


def default_watchlists() -> dict[str, list[dict[str, str]]]:
    return normalize_watchlists(DEFAULT_WATCHLISTS)


def merge_default_watchlists(payload: Any) -> dict[str, list[dict[str, str]]]:
    result = normalize_watchlists(payload)
    defaults = default_watchlists()
    for key in WATCHLIST_KEYS:
        seen = {row["symbol"] for row in result[key]}
        for row in defaults[key]:
            if row["symbol"] not in seen and len(result[key]) < MAX_ITEMS_PER_MARKET:
                result[key].append(dict(row))
                seen.add(row["symbol"])
    return result


def encode_watchlists(payload: Any) -> str:
    normalized = normalize_watchlists(payload)
    compact: dict[str, Any] = {
        "v": WATCHLIST_SCHEMA_VERSION,
        "d": DEFAULT_WATCHLIST_REVISION,
    }
    for key in WATCHLIST_KEYS:
        rows = normalized[key]
        compact[_SHORT_KEY[key]] = [[row["symbol"], row["name"]] for row in rows]
    raw = json.dumps(compact, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    packed = zlib.compress(raw, level=9)
    token = base64.urlsafe_b64encode(packed).decode("ascii").rstrip("=")
    return "v3." + token


def _unpack_token(raw: str, prefix: str) -> dict[str, Any]:
    token = raw[len(prefix):]
    token += "=" * (-len(token) % 4)
    packed = base64.urlsafe_b64decode(token.encode("ascii"))
    compact = json.loads(zlib.decompress(packed).decode("utf-8"))
    if not isinstance(compact, dict):
        raise ValueError("invalid watchlist payload")
    return compact


def _compact_to_payload(compact: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    payload = _empty()
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


def _decode_v3(raw: str) -> dict[str, list[dict[str, str]]]:
    compact = _unpack_token(raw, "v3.")
    if compact.get("v") != WATCHLIST_SCHEMA_VERSION:
        raise ValueError("unsupported watchlist payload")
    return _compact_to_payload(compact)


def _decode_v2(raw: str) -> dict[str, list[dict[str, str]]]:
    compact = _unpack_token(raw, "v2.")
    if compact.get("v") != 2:
        raise ValueError("unsupported legacy watchlist payload")
    return _compact_to_payload(compact)


def decode_watchlists(raw: Any) -> dict[str, list[dict[str, str]]]:
    if raw is None:
        return _empty()
    text = str(raw).strip()
    if not text:
        return _empty()
    try:
        if text.startswith("v3."):
            return _decode_v3(text)
        if text.startswith("v2."):
            return _decode_v2(text)
        return normalize_watchlists(json.loads(text))
    except Exception:
        return _empty()


def watchlist_needs_default_migration(raw: Any) -> bool:
    text = str(raw or "").strip()
    if not text.startswith("v3."):
        return True
    try:
        compact = _unpack_token(text, "v3.")
        return int(compact.get("d", 0)) < DEFAULT_WATCHLIST_REVISION
    except Exception:
        return True
