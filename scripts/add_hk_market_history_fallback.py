from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HK = ROOT / "macro_platform" / "hk_liquidity.py"
APP = ROOT / "app.py"
text = HK.read_text(encoding="utf-8")
app = APP.read_text(encoding="utf-8")

marker = 'def _market_monthly_close(symbol: str, label: str) -> pd.DataFrame:\n'
if marker not in text:
    raise RuntimeError("market history function not found")

helper = '''def _eastmoney_monthly_close(secid: str, label: str) -> pd.DataFrame:
    """Fallback five-year monthly price/index history from Eastmoney K-lines."""
    try:
        end = pd.Timestamp.today().strftime("%Y%m%d")
        beg = (pd.Timestamp.today() - pd.DateOffset(years=5, months=2)).strftime("%Y%m%d")
        response = requests.get(
            "https://push2his.eastmoney.com/api/qt/stock/kline/get",
            params={
                "secid": secid,
                "fields1": "f1,f2,f3,f4,f5,f6",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
                "klt": 103,
                "fqt": 0,
                "beg": beg,
                "end": end,
                "lmt": 80,
            },
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"},
            timeout=4.0,
        )
        response.raise_for_status()
        klines = (((response.json() or {}).get("data") or {}).get("klines") or [])
        rows = []
        for item in klines:
            parts = str(item).split(",")
            if len(parts) < 3:
                continue
            rows.append((parts[0], parts[2]))
        frame = pd.DataFrame(rows, columns=["observation_date", label])
        frame["observation_date"] = pd.to_datetime(frame["observation_date"], errors="coerce")
        frame[label] = pd.to_numeric(frame[label], errors="coerce")
        frame = frame.dropna().sort_values("observation_date")
        if frame.empty:
            return pd.DataFrame(columns=["observation_date", label])
        frame["observation_date"] = frame["observation_date"].dt.to_period("M").dt.to_timestamp()
        return frame.drop_duplicates("observation_date", keep="last")[["observation_date", label]]
    except Exception:
        return pd.DataFrame(columns=["observation_date", label])


'''
text = text.replace(marker, helper + marker, 1)

# Yahoo occasionally resolves HSTECH.HK but returns only the current month.
# Require at least four years of monthly observations before accepting it.
old_return = '''                return (
                    frame.sort_values("observation_date")
                    .drop_duplicates("observation_date", keep="last")
                    [["observation_date", label]]
                )
            except Exception:
                continue
    return pd.DataFrame(columns=["observation_date", label])
'''
new_return = '''                frame = (
                    frame.sort_values("observation_date")
                    .drop_duplicates("observation_date", keep="last")
                    [["observation_date", label]]
                )
                if len(frame) >= 48:
                    return frame
                continue
            except Exception:
                continue
    secid = {
        "0388.HK": "116.00388",
        "HSTECH.HK": "124.HSTECH",
        "^HSTECH": "124.HSTECH",
    }.get(str(symbol).upper())
    if secid:
        fallback = _eastmoney_monthly_close(secid, label)
        if len(fallback) >= 48:
            return fallback
    return pd.DataFrame(columns=["observation_date", label])
'''
if old_return not in text:
    raise RuntimeError("market history return block not found")
text = text.replace(old_return, new_return, 1)

# Fix the same market identifier in the real-time quote router.
app = app.replace(
    'if raw in ("HSTECH.HK", "^HSTECH"): return "100.HSTECH"',
    'if raw in ("HSTECH.HK", "^HSTECH"): return "124.HSTECH"',
    1,
)

HK.write_text(text, encoding="utf-8")
APP.write_text(app, encoding="utf-8")
print("added resilient 5Y HKEX/HSTECH history using Eastmoney 124.HSTECH fallback")
