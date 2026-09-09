from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
HK = ROOT / "macro_platform" / "hk_liquidity.py"
APP = ROOT / "app.py"

hk = HK.read_text(encoding="utf-8")
app = APP.read_text(encoding="utf-8")

# 1) io.StringIO for key-free FRED CSV fallback.
if "from io import StringIO" not in hk:
    hk = hk.replace("import json\n", "import json\nfrom io import StringIO\n", 1)

# 2) Replace market-history fetcher with resilient Yahoo hosts + HSTECH alias fallback,
#    and add a daily FRED loader for 5Y USD/HKD history.
pattern = r"def _market_monthly_close\(symbol: str, label: str\) -> pd\.DataFrame:\n.*?(?=\ndef build_hk_liquidity_figures)"
replacement = '''def _market_monthly_close(symbol: str, label: str) -> pd.DataFrame:
    """Fetch up to five years of month-end market levels.

    Yahoo market history is enrichment only. Try both public chart hosts and,
    for Hang Seng TECH, a secondary symbol alias. A failure must never blank
    the HKMA liquidity charts.
    """
    symbols = [symbol]
    if str(symbol).upper() == "HSTECH.HK":
        symbols.append("^HSTECH")
    hosts = (
        "https://query1.finance.yahoo.com/v8/finance/chart/",
        "https://query2.finance.yahoo.com/v8/finance/chart/",
    )
    for market_symbol in symbols:
        for host in hosts:
            try:
                response = requests.get(
                    host + market_symbol,
                    params={
                        "range": "5y",
                        "interval": "1mo",
                        "includeAdjustedClose": "true",
                        "events": "div,splits",
                    },
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=4.0,
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
                frame = pd.DataFrame(
                    {
                        "observation_date": pd.to_datetime(
                            timestamps, unit="s", utc=True, errors="coerce"
                        ).tz_convert(None),
                        label: pd.to_numeric(closes, errors="coerce"),
                    }
                ).dropna(subset=["observation_date", label])
                if frame.empty:
                    continue
                frame["observation_date"] = (
                    frame["observation_date"].dt.to_period("M").dt.to_timestamp()
                )
                return (
                    frame.sort_values("observation_date")
                    .drop_duplicates("observation_date", keep="last")
                    [["observation_date", label]]
                )
            except Exception:
                continue
    return pd.DataFrame(columns=["observation_date", label])


def _fred_daily_series(series_id: str, label: str) -> pd.DataFrame:
    """Load a public FRED daily series without requiring an API key."""
    try:
        response = requests.get(
            "https://fred.stlouisfed.org/graph/fredgraph.csv",
            params={"id": series_id},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=4.0,
        )
        response.raise_for_status()
        frame = pd.read_csv(StringIO(response.text))
        if frame.empty or len(frame.columns) < 2:
            return pd.DataFrame(columns=["observation_date", label])
        date_col = frame.columns[0]
        value_col = series_id if series_id in frame.columns else frame.columns[1]
        frame["observation_date"] = pd.to_datetime(frame[date_col], errors="coerce")
        frame[label] = pd.to_numeric(frame[value_col], errors="coerce")
        frame = frame.dropna(subset=["observation_date", label]).sort_values("observation_date")
        if frame.empty:
            return pd.DataFrame(columns=["observation_date", label])
        cutoff = frame["observation_date"].max() - pd.DateOffset(years=5)
        return frame.loc[frame["observation_date"] >= cutoff, ["observation_date", label]].copy()
    except Exception:
        return pd.DataFrame(columns=["observation_date", label])

'''
hk, n = re.subn(pattern, replacement, hk, flags=re.S)
if n != 1:
    raise RuntimeError(f"market history function replacement count={n}")

# 3) Keep five-year market histories independent from the short HKMA monthly snapshot.
old_market = '''    hkex_price = _market_monthly_close("0388.HK", "HKEX Price")
    hstech_index = _market_monthly_close("HSTECH.HK", "HSTECH Index")
    market_data = data[["observation_date"]].copy()
    for frame in (hkex_price, hstech_index):
        if not frame.empty:
            market_data = market_data.merge(frame, on="observation_date", how="left")
'''
new_market = '''    hkex_price = _market_monthly_close("0388.HK", "HKEX Price")
    hstech_index = _market_monthly_close("HSTECH.HK", "HSTECH Index")
    market_data = pd.DataFrame(columns=["observation_date"])
    for frame in (hkex_price, hstech_index):
        if frame.empty:
            continue
        if market_data.empty:
            market_data = frame.copy()
        else:
            market_data = market_data.merge(frame, on="observation_date", how="outer")
    if not market_data.empty:
        market_data = market_data.sort_values("observation_date")

    # Monthly HKMA FX is useful for consistency, but DEXHKUS gives a much fresher
    # daily five-year USD/HKD history for the convertibility-band panel.
    fx_daily = _fred_daily_series("DEXHKUS", "USD/HKD")
'''
if old_market not in hk:
    raise RuntimeError("market_data block not found")
hk = hk.replace(old_market, new_market, 1)

# 4) Let reference lines span the actual FX/market history instead of the short monthly snapshot.
old_sig = '''    def add_constant(
        fig: go.Figure,
        value: float,
        name: str,
        color: str,
        dash: str = "dot",
        width: float = 1.4,
        secondary_y: bool | None = None,
    ) -> None:
        trace = go.Scatter(
            x=data["observation_date"], y=[value] * len(data), name=name, mode="lines",
'''
new_sig = '''    def add_constant(
        fig: go.Figure,
        value: float,
        name: str,
        color: str,
        dash: str = "dot",
        width: float = 1.4,
        secondary_y: bool | None = None,
        x_frame: pd.DataFrame | None = None,
    ) -> None:
        base = data if x_frame is None or x_frame.empty else x_frame
        trace = go.Scatter(
            x=base["observation_date"], y=[value] * len(base), name=name, mode="lines",
'''
if old_sig not in hk:
    raise RuntimeError("add_constant block not found")
hk = hk.replace(old_sig, new_sig, 1)

# 5) Make 5-1 title freshness follow the market history when available.
old_money_style = '''    style(money, "5-1. HK Money Supply & Market Pulse", right_axis=True)
'''
new_money_style = '''    style(money, "5-1. HK Money Supply & Market Pulse", right_axis=True)
    if not market_data.empty:
        market_latest = market_data["observation_date"].max().strftime("%Y-%m")
        money.update_layout(title_text=f"5-1. HK Money Supply & Market Pulse · market latest {market_latest}")
'''
if old_money_style not in hk:
    raise RuntimeError("money style block not found")
hk = hk.replace(old_money_style, new_money_style, 1)

# 6) Use daily FRED FX when available and reverse the USD/HKD axis so strong HKD is visually higher.
old_fx = '''    fx = make_subplots(specs=[[{"secondary_y": True}]])
    add_line(fx, data, "USD/HKD", "USD/HKD", COLORS["fx"], 2.6, unit="", secondary_y=False)
    add_constant(fx, 7.75, "Strong-side CU 7.75", COLORS["strong"], "dot", 1.4, secondary_y=False)
    add_constant(fx, 7.80, "Linked Rate Center 7.80", "#64748b", "dash", 1.5, secondary_y=False)
    add_constant(fx, 7.85, "Weak-side CU 7.85", COLORS["weak"], "dot", 1.4, secondary_y=False)
'''
new_fx = '''    fx = make_subplots(specs=[[{"secondary_y": True}]])
    fx_source = fx_daily if not fx_daily.empty else data[["observation_date", "USD/HKD"]].dropna().copy()
    add_line(fx, fx_source, "USD/HKD", "USD/HKD", COLORS["fx"], 2.6, unit="", secondary_y=False)
    add_constant(fx, 7.75, "Strong-side CU 7.75", COLORS["strong"], "dot", 1.4, secondary_y=False, x_frame=fx_source)
    add_constant(fx, 7.80, "Linked Rate Center 7.80", "#64748b", "dash", 1.5, secondary_y=False, x_frame=fx_source)
    add_constant(fx, 7.85, "Weak-side CU 7.85", COLORS["weak"], "dot", 1.4, secondary_y=False, x_frame=fx_source)
'''
if old_fx not in hk:
    raise RuntimeError("fx block not found")
hk = hk.replace(old_fx, new_fx, 1)

old_axis = '''        title_text="USD/HKD", secondary_y=False, range=[7.73, 7.87],
'''
new_axis = '''        title_text="USD/HKD · Strong ↑ / Weak ↓", secondary_y=False, range=[7.87, 7.73],
'''
if old_axis not in hk:
    raise RuntimeError("fx axis range block not found")
hk = hk.replace(old_axis, new_axis, 1)

old_fx_style = '''    style(fx, "5-4. USD/HKD Convertibility Band & Market", height=450, right_axis=True)

    return [money, balance, funding, fx]
'''
new_fx_style = '''    style(fx, "5-4. USD/HKD Convertibility Band & Market", height=450, right_axis=True)
    if not fx_source.empty:
        fx_latest = fx_source["observation_date"].max().strftime("%Y-%m-%d")
        fx.update_layout(title_text=f"5-4. USD/HKD Convertibility Band & Market · FX latest {fx_latest}")

    return [money, balance, funding, fx]
'''
if old_fx_style not in hk:
    raise RuntimeError("fx style return block not found")
hk = hk.replace(old_fx_style, new_fx_style, 1)

# 7) Clarify freshness and reversed-axis semantics in the dashboard copy.
old_51 = '5. HSTECH Index（R）：恒生科技指数 HSTECH.HK 月末指数点位，右轴单位 points；用于观察高贝塔科技资产价格水平与香港流动性环境的关系。'
new_51 = '5. HSTECH Index（R）：恒生科技指数 HSTECH.HK 月末指数点位，右轴单位 points；市场历史独立拉取 5Y，不再被 HKMA 月度快照长度裁断。'
app = app.replace(old_51, new_51)

old_54_hint = '<b>读取提示：</b>灰色淡色区域表示 7.75–7.85 联系汇率兑换保证区间；7.80 为区间中点参考。市场价格水平用于对照汇率位置与香港风险资产表现。'
new_54_hint = '<b>读取提示：</b>USD/HKD 左轴已反向：7.75 强方兑换保证显示在上方、7.85 弱方兑换保证显示在下方，因此视觉方向直接对应“港元偏强/流动性偏强 → 港元偏弱/流动性偏弱”。灰色区域仍表示 7.75–7.85 联系汇率区间；USD/HKD 优先使用 FRED DEXHKUS 日频 5Y 历史，HKMA 月度汇率作为回退。'
if old_54_hint not in app:
    raise RuntimeError("5-4 hint not found")
app = app.replace(old_54_hint, new_54_hint, 1)

old_sources = '''        ("HKMA Open API", "https://apidocs.hkma.gov.hk/"),
        ("Yahoo Finance Market Data", "https://finance.yahoo.com/"),
'''
new_sources = '''        ("HKMA Open API", "https://apidocs.hkma.gov.hk/"),
        ("Hang Seng Indexes · HSTECH", "https://www.hsi.com.hk/eng/indexes/all-indexes/hstech"),
        ("FRED DEXHKUS · Daily USD/HKD", "https://fred.stlouisfed.org/series/DEXHKUS"),
        ("Yahoo Finance Market History", "https://finance.yahoo.com/"),
'''
if old_sources not in app:
    raise RuntimeError("HK source list block not found")
app = app.replace(old_sources, new_sources, 1)

HK.write_text(hk, encoding="utf-8")
APP.write_text(app, encoding="utf-8")
print("upgraded HK market history, FX freshness, and 5-4 liquidity-oriented axis")
