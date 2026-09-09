from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
HK = ROOT / "macro_platform" / "hk_liquidity.py"
APP = ROOT / "app.py"
text = HK.read_text(encoding="utf-8")
app = APP.read_text(encoding="utf-8")

replacement = '''def _eastmoney_monthly_close(secids: list[str], label: str) -> pd.DataFrame:
    """Fallback five-year monthly index/stock history from Eastmoney K-lines."""
    for secid in secids:
        try:
            response = requests.get(
                "https://push2his.eastmoney.com/api/qt/stock/kline/get",
                params={
                    "secid": secid,
                    "klt": "103",
                    "fqt": "0",
                    "lmt": "100",
                    "end": "20500101",
                    "iscca": "1",
                    "fields1": "f1,f2,f3,f4,f5,f6,f7,f8",
                    "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64",
                    "ut": "f057cbcbce2a86e2866ab8877db1d059",
                    "forcect": "1",
                },
                headers={"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"},
                timeout=5.0,
            )
            response.raise_for_status()
            klines = (((response.json() or {}).get("data") or {}).get("klines") or [])
            rows = []
            for item in klines:
                parts = str(item).split(",")
                if len(parts) >= 3:
                    rows.append((parts[0], parts[2]))
            frame = pd.DataFrame(rows, columns=["observation_date", label])
            frame["observation_date"] = pd.to_datetime(frame["observation_date"], errors="coerce")
            frame[label] = pd.to_numeric(frame[label], errors="coerce")
            frame = frame.dropna().sort_values("observation_date")
            if frame.empty:
                continue
            frame["observation_date"] = frame["observation_date"].dt.to_period("M").dt.to_timestamp()
            frame = frame.drop_duplicates("observation_date", keep="last")[["observation_date", label]]
            if len(frame) >= 48:
                cutoff = frame["observation_date"].max() - pd.DateOffset(years=5)
                return frame[frame["observation_date"] >= cutoff].copy()
        except Exception:
            continue
    return pd.DataFrame(columns=["observation_date", label])


def _market_monthly_close(symbol: str, label: str) -> pd.DataFrame:
    """Fetch five years of month-end market levels with multi-route fallback.

    Some Yahoo symbols (notably HSTECH.HK) return only the current month at
    interval=1mo. If monthly history is too short, request 5Y daily history and
    resample it locally before trying Eastmoney.
    """
    symbols = [symbol]
    if str(symbol).upper() == "HSTECH.HK":
        symbols.append("^HSTECH")
    hosts = (
        "https://query1.finance.yahoo.com/v8/finance/chart/",
        "https://query2.finance.yahoo.com/v8/finance/chart/",
    )

    for interval in ("1mo", "1d"):
        for market_symbol in symbols:
            for host in hosts:
                try:
                    response = requests.get(
                        host + market_symbol,
                        params={
                            "range": "5y",
                            "interval": interval,
                            "includeAdjustedClose": "true",
                            "events": "div,splits",
                        },
                        headers={"User-Agent": "Mozilla/5.0"},
                        timeout=5.0,
                    )
                    response.raise_for_status()
                    result = (((response.json() or {}).get("chart") or {}).get("result") or [])
                    if not result:
                        continue
                    node = result[0] or {}
                    timestamps = node.get("timestamp") or []
                    indicators = node.get("indicators") or {}
                    quote_close = (indicators.get("quote") or [{}])[0].get("close") or []
                    adj_close = (indicators.get("adjclose") or [{}])[0].get("adjclose") or []
                    closes = adj_close if len(adj_close) == len(timestamps) else quote_close
                    if len(closes) != len(timestamps):
                        continue
                    frame = pd.DataFrame({
                        "observation_date": pd.to_datetime(
                            timestamps, unit="s", utc=True, errors="coerce"
                        ).tz_convert(None),
                        label: pd.to_numeric(closes, errors="coerce"),
                    }).dropna(subset=["observation_date", label])
                    if frame.empty:
                        continue
                    frame["observation_date"] = frame["observation_date"].dt.to_period("M").dt.to_timestamp()
                    frame = (
                        frame.sort_values("observation_date")
                        .drop_duplicates("observation_date", keep="last")
                        [["observation_date", label]]
                    )
                    if len(frame) >= 48:
                        return frame
                except Exception:
                    continue

    secids = {
        "0388.HK": ["116.00388"],
        "HSTECH.HK": ["124.HSTECH", "100.HSTECH"],
        "^HSTECH": ["124.HSTECH", "100.HSTECH"],
    }.get(str(symbol).upper(), [])
    if secids:
        fallback = _eastmoney_monthly_close(secids, label)
        if not fallback.empty:
            return fallback
    return pd.DataFrame(columns=["observation_date", label])

'''
pattern = r"def _market_monthly_close\(symbol: str, label: str\) -> pd\.DataFrame:\n.*?(?=\ndef _fred_daily_series)"
text, count = re.subn(pattern, replacement, text, flags=re.S)
if count != 1:
    raise RuntimeError(f"market history replacement count={count}")

# Correct HSTECH real-time Eastmoney market code as well.
app = app.replace(
    'if raw in ("HSTECH.HK", "^HSTECH"): return "100.HSTECH"',
    'if raw in ("HSTECH.HK", "^HSTECH"): return "124.HSTECH"',
    1,
)

HK.write_text(text, encoding="utf-8")
APP.write_text(app, encoding="utf-8")
print("added Yahoo daily-resample plus Eastmoney fallback for 5Y HKEX/HSTECH history")
