from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import akshare as ak
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data_snapshots" / "hk_market_daily.json"
CUTOFF_BUFFER = pd.DateOffset(years=5, months=1)
MIN_POINTS = 900

SERIES: dict[str, dict[str, str]] = {
    "0700.HK": {"name": "Tencent Holdings", "unit": "HKD", "source": "Yahoo Finance"},
    "0388.HK": {"name": "Hong Kong Exchanges and Clearing", "unit": "HKD", "source": "Yahoo Finance"},
    "^HSI": {"name": "Hang Seng Index", "unit": "points", "source": "Yahoo Finance"},
    "HSTECH": {"name": "Hang Seng TECH Index", "unit": "points", "source": "Sina Finance via AKShare"},
}


def _read_existing() -> dict[str, Any]:
    if not OUT.exists():
        return {}
    try:
        payload = json.loads(OUT.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _existing_frame(payload: dict[str, Any], symbol: str) -> pd.DataFrame:
    node = ((payload.get("series") or {}).get(symbol) or {}) if isinstance(payload, dict) else {}
    frame = pd.DataFrame(node.get("records") or [])
    if frame.empty or "observation_date" not in frame.columns or "close" not in frame.columns:
        return pd.DataFrame(columns=["observation_date", "close"])
    frame["observation_date"] = pd.to_datetime(frame["observation_date"], errors="coerce")
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    return (
        frame.dropna(subset=["observation_date", "close"])
        .sort_values("observation_date")
        .drop_duplicates("observation_date", keep="last")
        [["observation_date", "close"]]
    )


def _fetch_yahoo(symbol: str) -> pd.DataFrame:
    encoded = quote(symbol, safe="")
    hosts = (
        "https://query1.finance.yahoo.com/v8/finance/chart/",
        "https://query2.finance.yahoo.com/v8/finance/chart/",
    )
    last_error: Exception | None = None
    for host in hosts:
        try:
            response = requests.get(
                host + encoded,
                params={
                    "range": "5y",
                    "interval": "1d",
                    "includeAdjustedClose": "true",
                    "events": "div,splits",
                },
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=20,
            )
            response.raise_for_status()
            result = (((response.json() or {}).get("chart") or {}).get("result") or [])
            if not result:
                raise RuntimeError(f"Yahoo returned no result for {symbol}")
            node = result[0] or {}
            timestamps = node.get("timestamp") or []
            indicators = node.get("indicators") or {}
            quote_close = (indicators.get("quote") or [{}])[0].get("close") or []
            adj_close = (indicators.get("adjclose") or [{}])[0].get("adjclose") or []
            closes = adj_close if len(adj_close) == len(timestamps) else quote_close
            if len(closes) != len(timestamps):
                raise RuntimeError(f"Yahoo malformed history for {symbol}")
            frame = pd.DataFrame(
                {
                    "observation_date": pd.to_datetime(
                        timestamps, unit="s", utc=True, errors="coerce"
                    ).tz_convert(None),
                    "close": pd.to_numeric(closes, errors="coerce"),
                }
            )
            frame["observation_date"] = frame["observation_date"].dt.normalize()
            frame = (
                frame.dropna(subset=["observation_date", "close"])
                .sort_values("observation_date")
                .drop_duplicates("observation_date", keep="last")
            )
            if len(frame) < MIN_POINTS:
                raise RuntimeError(f"Yahoo history too short for {symbol}: {len(frame)}")
            return frame[["observation_date", "close"]]
        except Exception as exc:
            last_error = exc
            time.sleep(1)
    raise RuntimeError(f"Yahoo fetch failed for {symbol}: {last_error}")


def _fetch_hstech() -> pd.DataFrame:
    daily = ak.stock_hk_index_daily_sina(symbol="HSTECH").copy()
    if daily.empty or "date" not in daily.columns or "close" not in daily.columns:
        raise RuntimeError("Sina HSTECH history returned no usable data")
    daily["observation_date"] = pd.to_datetime(daily["date"], errors="coerce").dt.normalize()
    daily["close"] = pd.to_numeric(daily["close"], errors="coerce")
    daily = (
        daily.dropna(subset=["observation_date", "close"])
        .sort_values("observation_date")
        .drop_duplicates("observation_date", keep="last")
    )
    cutoff = pd.Timestamp.now().normalize() - CUTOFF_BUFFER
    daily = daily[daily["observation_date"] >= cutoff]
    if len(daily) < MIN_POINTS:
        raise RuntimeError(f"Sina HSTECH history too short: {len(daily)}")
    return daily[["observation_date", "close"]]


def _merge_history(old: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    frames = [frame for frame in (old, new) if not frame.empty]
    if not frames:
        return pd.DataFrame(columns=["observation_date", "close"])
    merged = pd.concat(frames, ignore_index=True)
    merged = (
        merged.dropna(subset=["observation_date", "close"])
        .sort_values("observation_date")
        .drop_duplicates("observation_date", keep="last")
    )
    cutoff = pd.Timestamp.now().normalize() - CUTOFF_BUFFER
    return merged[merged["observation_date"] >= cutoff].copy()


def main() -> None:
    existing = _read_existing()
    previous_series = existing.get("series") or {}
    now = datetime.now(timezone.utc).isoformat()
    output_series: dict[str, Any] = {}

    for symbol, meta in SERIES.items():
        old = _existing_frame(existing, symbol)
        fresh = pd.DataFrame(columns=["observation_date", "close"])
        error: str | None = None
        try:
            fresh = _fetch_hstech() if symbol == "HSTECH" else _fetch_yahoo(symbol)
        except Exception as exc:
            error = str(exc)
            print(f"warning: {symbol} fresh fetch failed: {error}")

        merged = _merge_history(old, fresh)
        if len(merged) < MIN_POINTS:
            raise RuntimeError(
                f"{symbol} has no adequate last-known-good history: {len(merged)} points; fetch_error={error}"
            )

        previous_node = previous_series.get(symbol) or {}
        successful_at = now if not fresh.empty else previous_node.get("last_successful_fetch")
        records = [
            {
                "observation_date": row.observation_date.strftime("%Y-%m-%d"),
                "close": round(float(row.close), 6),
            }
            for row in merged.itertuples(index=False)
        ]
        output_series[symbol] = {
            **meta,
            "record_count": len(records),
            "coverage_start": records[0]["observation_date"],
            "coverage_end": records[-1]["observation_date"],
            "last_successful_fetch": successful_at,
            "fresh_fetch_ok": not fresh.empty,
            "last_fetch_error": error,
            "records": records,
        }
        print(
            symbol,
            len(records),
            records[0]["observation_date"],
            "->",
            records[-1]["observation_date"],
            "fresh" if not fresh.empty else "last-known-good",
        )

    coverage_start = min(node["coverage_start"] for node in output_series.values())
    coverage_end = max(node["coverage_end"] for node in output_series.values())
    payload = {
        "schema_version": 1,
        "updated_at": now,
        "retention": "rolling 5 years plus one month buffer",
        "policy": "merge fresh observations into last-known-good history; never erase a usable series on fetch failure",
        "coverage_start": coverage_start,
        "coverage_end": coverage_end,
        "series": output_series,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("wrote", OUT, "through", coverage_end)


if __name__ == "__main__":
    main()
