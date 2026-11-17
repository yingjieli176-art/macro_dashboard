"""Refresh all three bank premiums atomically from public raw closing prices."""
import concurrent.futures
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from macro_platform.bank_ah import BANKS, SNAPSHOT, calculate_premium
from macro_platform.market_history import completed_daily_closes


def fetch(symbol):
    errors = []
    for host in ("query1", "query2"):
        try:
            url = f"https://{host}.finance.yahoo.com/v8/finance/chart/{quote(symbol, safe='')}"
            response = requests.get(url, params={"range": "5y", "interval": "1d", "events": "div,splits"},
                                    headers={"User-Agent": "Mozilla/5.0"}, timeout=25)
            response.raise_for_status()
            node = response.json()["chart"]["result"][0]
            expected_currency = "HKD" if symbol.endswith(".HK") else "CNY"
            if node["meta"].get("symbol") != symbol or node["meta"].get("currency") != expected_currency:
                raise ValueError(f"Unexpected instrument or currency: {symbol}")
            frame = completed_daily_closes(node)
            if len(frame) < 900:
                raise ValueError(f"Insufficient history: {symbol} {len(frame)}")
            return frame
        except Exception as exc:
            errors.append(str(exc))
    raise RuntimeError(f"{symbol}: {errors}")


def main():
    symbols = [s for _, a, h, _ in BANKS.values() for s in (a, h)] + ["HKDCNY=X"]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        histories = dict(zip(symbols, pool.map(fetch, symbols)))
    series = {}
    old = json.loads(SNAPSHOT.read_text(encoding="utf-8")) if SNAPSHOT.exists() else {}
    for key, (name, a, h, _) in BANKS.items():
        frame = calculate_premium(histories[a], histories[h], histories["HKDCNY=X"])
        if len(frame) < 850:
            raise ValueError(f"Incomplete common-date history: {key}")
        latest = frame.observation_date.max().strftime("%Y-%m-%d")
        previous = old.get("series", {}).get(key, {}).get("records", [])
        if previous and latest < previous[-1]["observation_date"]:
            raise ValueError(f"Source regressed: {key}")
        frame["observation_date"] = frame.observation_date.dt.strftime("%Y-%m-%d")
        series[key] = {"name": name, "a_symbol": a, "h_symbol": h,
            "source_urls": [f"https://finance.yahoo.com/quote/{quote(s, safe='')}/history/" for s in (a, h, "HKDCNY=X")],
            "records": frame.to_dict("records")}
        print(name, len(frame), frame.observation_date.iloc[0], latest, flush=True)
    payload = {"source": "Yahoo Finance public daily history", "price_basis": "raw_close",
        "fx_basis": "HKDCNY=X: CNY per HKD; daily FX close, not synchronized equity auction fixing",
        "formula": "(A_CNY / (H_HKD * CNY_per_HKD) - 1) * 100",
        "alignment": "same-date completed bars only; no forward fill or interpolation",
        "updated_at": datetime.now(timezone.utc).isoformat(), "series": series}
    temporary = SNAPSHOT.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    temporary.replace(SNAPSHOT)


if __name__ == "__main__":
    main()
