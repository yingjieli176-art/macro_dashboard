from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data.py"
APP = ROOT / "app.py"

data = DATA.read_text(encoding="utf-8")
app = APP.read_text(encoding="utf-8")

# Allow non-FRED sources (Treasury FiscalData, Eastmoney, etc.) to work even
# when the module is imported outside Streamlit with no secrets.toml.
old_key = 'FRED_API_KEY = st.secrets.get("FRED_API_KEY", "")\n'
new_key = '''try:\n    FRED_API_KEY = st.secrets.get("FRED_API_KEY", "")\nexcept Exception:\n    FRED_API_KEY = ""\n'''
if old_key in data:
    data = data.replace(old_key, new_key, 1)

anchor = '@st.cache_data(ttl=3600)\ndef get_wtre_gen(): return _fred_series("WTREGEN")\n'
insert = '''@st.cache_data(ttl=3600)
def get_wtre_gen(): return _fred_series("WTREGEN")

@st.cache_data(ttl=3600)
def get_tga_daily():
    """Daily Treasury General Account balance from the U.S. Treasury DTS.

    The DTS schema has changed account labels/fields over time. Prefer the TGA
    closing-balance row, then Total Operating Balance, and accept the numeric
    value from close_today_bal or open_today_bal. If FiscalData is unavailable,
    fall back to the weekly Federal Reserve WTREGEN series.
    """
    url = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/dts/operating_cash_balance"
    cutoff = (pd.Timestamp.today().normalize() - pd.DateOffset(years=5, months=1)).strftime("%Y-%m-%d")
    try:
        response = requests.get(
            url,
            params={
                "filter": f"record_date:gte:{cutoff}",
                "sort": "record_date",
                "page[size]": 10000,
                "format": "json",
            },
            headers={"User-Agent": "MacroDashboard/1.0"},
            timeout=8,
        )
        response.raise_for_status()
        rows = (response.json() or {}).get("data") or []
        frame = pd.DataFrame(rows)
        if frame.empty or "record_date" not in frame.columns:
            raise RuntimeError("Treasury FiscalData returned no TGA rows")
        frame["observation_date"] = pd.to_datetime(frame["record_date"], errors="coerce")
        if "account_type" not in frame.columns:
            frame["account_type"] = ""
        frame["account_type"] = frame["account_type"].astype(str)
        for col in ("close_today_bal", "open_today_bal"):
            if col not in frame.columns:
                frame[col] = pd.NA
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
        frame["_value"] = frame["close_today_bal"].combine_first(frame["open_today_bal"])
        frame = frame.dropna(subset=["observation_date", "_value"])
        if frame.empty:
            raise RuntimeError("Treasury FiscalData returned no numeric TGA balances")

        def _priority(label):
            text = str(label).lower()
            if "treasury general account" in text and "closing" in text:
                return 0
            if "total operating balance" in text:
                return 1
            if "treasury general account" in text:
                return 2
            if "federal reserve account" in text:
                return 3
            return 9

        frame["_priority"] = frame["account_type"].map(_priority)
        frame = frame[frame["_priority"] < 9].sort_values(["observation_date", "_priority"])
        frame = frame.drop_duplicates("observation_date", keep="first")
        if frame.empty:
            raise RuntimeError("Treasury FiscalData TGA account labels were not recognized")
        # DTS balances are USD millions; dashboard chart uses USD trillions.
        frame["TGA_DAILY"] = frame["_value"] / 1_000_000.0
        return frame[["observation_date", "TGA_DAILY"]].sort_values("observation_date")
    except Exception:
        weekly = _fred_series("WTREGEN").copy()
        weekly["TGA_DAILY"] = pd.to_numeric(weekly["WTREGEN"], errors="coerce") / 1_000_000.0
        return weekly[["observation_date", "TGA_DAILY"]].dropna().sort_values("observation_date")
'''
if anchor not in data:
    raise RuntimeError("WTREGEN anchor not found")
data = data.replace(anchor, insert, 1)

old_import = 'get_sina_news, get_wresbal, get_wtre_gen, get_rrp_daily, _fred_series)'
new_import = 'get_sina_news, get_wresbal, get_wtre_gen, get_tga_daily, get_rrp_daily, _fred_series)'
if old_import not in app:
    raise RuntimeError("app data import anchor not found")
app = app.replace(old_import, new_import, 1)

old_specs = 'specs = [(get_wresbal, "WRESBAL"), (get_wtre_gen, "WTREGEN"), (get_rrp_daily, "RRPONTSYD")]'
new_specs = 'specs = [(get_wresbal, "WRESBAL"), (get_tga_daily, "TGA_DAILY"), (get_rrp_daily, "RRPONTSYD")]'
if old_specs not in app:
    raise RuntimeError("US liquidity specs anchor not found")
app = app.replace(old_specs, new_specs, 1)

old_transform = '''                if column == "RRPONTSYD": frame[column] = frame[column] / 1000.0; frame = frame.set_index("observation_date")[column].resample("W-WED").mean().rename(column).reset_index()
                else: frame[column] = frame[column] / 1000000.0
'''
new_transform = '''                if column == "RRPONTSYD": frame[column] = frame[column] / 1000.0; frame = frame.set_index("observation_date")[column].resample("W-WED").mean().rename(column).reset_index()
                elif column == "WRESBAL": frame[column] = frame[column] / 1000000.0
'''
if old_transform not in app:
    raise RuntimeError("US liquidity transform block not found")
app = app.replace(old_transform, new_transform, 1)

app = app.replace(
    '["WRESBAL", "WTREGEN", "RRPONTSYD"]',
    '["WRESBAL", "TGA_DAILY", "RRPONTSYD"]',
    2,
)
app = app.replace(
    'data["NetLiquidity"] = data["WRESBAL"] - data["WTREGEN"] - data["RRPONTSYD"]',
    'data["NetLiquidity"] = data["WRESBAL"] - data["TGA_DAILY"] - data["RRPONTSYD"]',
    1,
)
app = app.replace(
    '("WTREGEN", "TGA", 2.1, "dash")',
    '("TGA_DAILY", "TGA · Daily", 2.1, "dash")',
    1,
)
app = app.replace(
    '3. TGA（Treasury General Account）：美国财政部在美联储的总账户余额，财政资金进出会影响银行体系准备金。',
    '3. TGA（Treasury General Account）：优先使用美国财政部 Daily Treasury Statement 的日频 Operating Cash Balance；财政资金进出会直接影响银行体系准备金。FiscalData 不可用时自动回退到 FRED WTREGEN 周频数据。',
    1,
)
app = app.replace(
    '("TGA (WTREGEN)", "https://fred.stlouisfed.org/series/WTREGEN")',
    '("TGA · Daily Treasury Statement", "https://fiscaldata.treasury.gov/datasets/daily-treasury-statement/operating-cash-balance"), ("TGA fallback (WTREGEN)", "https://fred.stlouisfed.org/series/WTREGEN")',
    1,
)

DATA.write_text(data, encoding="utf-8")
APP.write_text(app, encoding="utf-8")
print("upgraded US TGA to Treasury FiscalData daily source with FRED fallback")
