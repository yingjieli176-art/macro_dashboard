from pathlib import Path
import re

APP = Path('app.py')
text = APP.read_text(encoding='utf-8')

# 1) Replace Chart 4 with readable multi-axis layout.
new_fig4 = r'''def build_fig4(date_range):
    """US liquidity chart with separate scales for unlike balance magnitudes.

    L: Net Liquidity = WALCL - TGA - ON RRP, USD trillions.
    R1: Reserve Balances and TGA, USD trillions.
    R2: ON RRP, USD billions.
    """
    specs = [
        (get_walcl, "WALCL", 1_000_000.0),
        (get_wresbal, "WRESBAL", 1_000_000.0),
        (get_tga_daily, "TGA_DAILY", 1.0),
        (get_rrp_daily, "RRPONTSYD", 1.0),
    ]
    raw_series = {}
    tga_is_fallback = False
    for getter, column, divisor in specs:
        try:
            frame = getter().copy()
            if column == "TGA_DAILY":
                tga_is_fallback = bool(frame.attrs.get("is_fallback", False))
            frame["observation_date"] = pd.to_datetime(frame["observation_date"], errors="coerce")
            frame[column] = pd.to_numeric(frame[column], errors="coerce") / divisor
            frame = frame.dropna(subset=["observation_date", column]).sort_values("observation_date")[["observation_date", column]]
            if not frame.empty:
                raw_series[column] = frame
        except Exception:
            continue

    fig = go.Figure()
    if not raw_series:
        for name in ("Net Liquidity", "Reserve Balances", "TGA", "ON RRP"):
            _mark_missing_series(fig, name)
        return apply_chart_style(fig, chart_height(320, 430), date_range)

    # Calculate the proxy on a union calendar. Forward filling is only used
    # inside the mixed-frequency calculation; displayed source traces remain
    # at their native observation dates.
    calc = None
    for column in ("WALCL", "TGA_DAILY", "RRPONTSYD"):
        frame = raw_series.get(column)
        if frame is None:
            continue
        calc = frame.copy() if calc is None else calc.merge(frame, on="observation_date", how="outer")
    calc = pd.DataFrame(columns=["observation_date"]) if calc is None else calc.sort_values("observation_date")
    component_cols = [c for c in ("WALCL", "TGA_DAILY", "RRPONTSYD") if c in calc.columns]
    if component_cols:
        calc[component_cols] = calc[component_cols].ffill()
    if all(c in calc.columns for c in ("WALCL", "TGA_DAILY", "RRPONTSYD")):
        calc["NetLiquidity"] = calc["WALCL"] - calc["TGA_DAILY"] - calc["RRPONTSYD"] / 1000.0
    calc = filter_range(calc, date_range)

    add_line(fig, calc, "NetLiquidity", "Net Liquidity", 3.0, unit=" T")

    reserve = raw_series.get("WRESBAL")
    if reserve is not None:
        add_line(fig, filter_range(reserve, date_range), "WRESBAL", "Reserve Balances", 2.4, yaxis="y2", unit=" T")
    else:
        _mark_missing_series(fig, "Reserve Balances")

    tga = raw_series.get("TGA_DAILY")
    if tga is not None:
        tga_name = "TGA · Weekly fallback" if tga_is_fallback else "TGA"
        add_line(fig, filter_range(tga, date_range), "TGA_DAILY", tga_name, 2.2, "dash", "y2", " T")
    else:
        _mark_missing_series(fig, "TGA")

    rrp = raw_series.get("RRPONTSYD")
    if rrp is not None:
        add_line(fig, filter_range(rrp, date_range), "RRPONTSYD", "ON RRP", 2.2, "dot", "y3", " B")
    else:
        _mark_missing_series(fig, "ON RRP")

    # Predeclare secondary axes so apply_chart_style reserves enough space.
    fig.update_layout(
        yaxis2=dict(overlaying="y", side="right", anchor="free", position=0.86),
        yaxis3=dict(overlaying="y", side="right", anchor="free", position=0.97),
    )
    fig = apply_chart_style(fig, chart_height(320, 430), date_range)
    fig.update_layout(
        margin=dict(l=64, r=164, t=72, b=34, pad=2),
        legend=dict(y=1.09, x=0.01),
        xaxis=dict(domain=[0.0, 0.82]),
        yaxis=dict(
            title="Net Liquidity · USD T",
            showgrid=True, gridcolor="#e5e7eb", griddash="dot",
            zeroline=False, fixedrange=True, tickformat=".1f",
        ),
        yaxis2=dict(
            title="R1 · Reserve / TGA · USD T",
            overlaying="y", side="right", anchor="free", position=0.86,
            showgrid=False, zeroline=False, fixedrange=True,
            tickformat=".1f", tickfont=dict(size=10),
        ),
        yaxis3=dict(
            title="R2 · ON RRP · USD B",
            overlaying="y", side="right", anchor="free", position=0.97,
            showgrid=False, zeroline=True, zerolinecolor="#94a3b8",
            zerolinewidth=1, fixedrange=True, tickformat=".0f",
            tickfont=dict(size=10),
        ),
    )
    return fig
'''

pattern = r'def build_fig4\(date_range\):\n.*?\n\ndef build_fig3\(date_range\):'
text, count = re.subn(pattern, new_fig4 + '\n\ndef build_fig3(date_range):', text, count=1, flags=re.S)
if count != 1:
    raise RuntimeError(f'build_fig4 replacement count={count}')

text = text.replace(
    '<div class="section-description">Net Liquidity / Reserve Balances / TGA / ON RRP</div>',
    '<div class="section-description">Net Liquidity (L) · Reserve Balances / TGA (R1) · ON RRP (R2)</div>',
    1,
)

old_desc = '1. Net Liquidity Proxy：WALCL（美联储总资产）− TGA − ON RRP 的常用资产负债表流动性代理，单位统一为 USD trillion；不是美联储官方指标。WALCL 为周频，计算时只在代理内部沿用至下一次公布。'
new_desc = '1. Net Liquidity Proxy：WALCL（美联储总资产）− TGA − ON RRP 的常用资产负债表流动性代理，左轴单位 USD trillion；不是美联储官方指标。WALCL 为周频，计算时只在代理内部沿用至下一次公布。'
text = text.replace(old_desc, new_desc, 1)
text = text.replace(
    '2. Reserve Balances：存款机构存放在美联储的准备金余额；WRESBAL 为周频公布，图中的原始线只保留实际周频观测，不再用前值填充伪装成日频。',
    '2. Reserve Balances：存款机构存放在美联储的准备金余额；WRESBAL 为周频公布，使用右轴 R1，单位 USD trillion。图中的原始线只保留实际周频观测。',
    1,
)
text = text.replace(
    '4. ON RRP Balance：美联储隔夜逆回购工具的余额，反映资金进入该工具的规模。',
    '4. ON RRP Balance：美联储隔夜逆回购工具余额，使用右轴 R2，单位 USD billion；单独设轴避免当前低余额被压在零线附近。',
    1,
)

# 2) Add Yahoo daily futures helper and Chart 10.
metals_builder = r'''

@st.cache_data(ttl=3600, show_spinner=False)
def get_yahoo_daily_history(symbol):
    """Fetch five years of completed daily closes from Yahoo chart API."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{requests.utils.quote(symbol, safe='')}"
    response = requests.get(
        url,
        params={"range": "5y", "interval": "1d", "includePrePost": "false", "events": "div,splits"},
        headers={"User-Agent": "Mozilla/5.0 (compatible; MacroDashboard/1.0)"},
        timeout=(3.0, 8.0),
    )
    response.raise_for_status()
    result = ((response.json() or {}).get("chart") or {}).get("result") or []
    if not result:
        return pd.DataFrame(columns=["observation_date", "close"])
    node = result[0]
    timestamps = node.get("timestamp") or []
    quotes = (((node.get("indicators") or {}).get("quote") or [{}])[0]).get("close") or []
    if not timestamps or not quotes:
        return pd.DataFrame(columns=["observation_date", "close"])
    size = min(len(timestamps), len(quotes))
    dates = pd.to_datetime(timestamps[:size], unit="s", utc=True)
    tz_name = (node.get("meta") or {}).get("exchangeTimezoneName") or "America/New_York"
    try:
        dates = dates.tz_convert(tz_name).tz_localize(None).normalize()
    except Exception:
        dates = dates.tz_convert("America/New_York").tz_localize(None).normalize()
    frame = pd.DataFrame({"observation_date": dates, "close": pd.to_numeric(quotes[:size], errors="coerce")})
    frame = frame.dropna(subset=["observation_date", "close"]).sort_values("observation_date")
    return frame.drop_duplicates("observation_date", keep="last")


def _rebase_100(series):
    values = pd.to_numeric(series, errors="coerce")
    valid = values.dropna()
    if valid.empty or float(valid.iloc[0]) == 0:
        return values * pd.NA
    return values / float(valid.iloc[0]) * 100.0


def build_fig10(date_range, market_mode="Rebased 100"):
    """Precious metals: gold, silver, gold/silver ratio, and GVZ."""
    frames = []
    for symbol, column in (("GC=F", "Gold"), ("SI=F", "Silver")):
        try:
            frame = get_yahoo_daily_history(symbol).rename(columns={"close": column})
            if not frame.empty:
                frames.append(frame[["observation_date", column]])
        except Exception:
            pass
    try:
        gvz = get_fred_series("GVZCLS").copy()
        gvz["observation_date"] = pd.to_datetime(gvz["observation_date"], errors="coerce")
        gvz["GVZCLS"] = pd.to_numeric(gvz["GVZCLS"], errors="coerce")
        gvz = gvz.dropna(subset=["observation_date", "GVZCLS"])[["observation_date", "GVZCLS"]]
        if not gvz.empty:
            frames.append(gvz)
    except Exception:
        pass

    if frames:
        data = frames[0]
        for frame in frames[1:]:
            data = data.merge(frame, on="observation_date", how="outer")
        data = data.sort_values("observation_date")
    else:
        data = pd.DataFrame(columns=["observation_date"])

    if "Gold" in data.columns and "Silver" in data.columns:
        gold = pd.to_numeric(data["Gold"], errors="coerce")
        silver = pd.to_numeric(data["Silver"], errors="coerce")
        data["GoldSilverRatio"] = gold.where(silver > 0) / silver.where(silver > 0)
    data = filter_range(data, date_range)

    fig = go.Figure()
    if market_mode == "Rebased 100":
        if "Gold" in data.columns:
            data["Gold_R100"] = _rebase_100(data["Gold"])
        if "Silver" in data.columns:
            data["Silver_R100"] = _rebase_100(data["Silver"])
        add_line(fig, data, "Gold_R100", "Gold · R100", 2.8, unit="")
        add_line(fig, data, "Silver_R100", "Silver · R100", 2.5, unit="")
        add_line(fig, data, "GoldSilverRatio", "Gold/Silver Ratio", 2.2, "dash", "y2", "x")
        add_line(fig, data, "GVZCLS", "Gold Volatility · GVZ", 2.2, "dot", "y3", "")
        fig.update_layout(
            yaxis2=dict(overlaying="y", side="right", anchor="free", position=0.87),
            yaxis3=dict(overlaying="y", side="right", anchor="free", position=0.98),
        )
        fig = apply_chart_style(fig, chart_height(320, 440), date_range)
        fig.update_layout(
            margin=dict(l=62, r=150, t=72, b=34, pad=2),
            legend=dict(y=1.09, x=0.01),
            xaxis=dict(domain=[0.0, 0.84]),
            yaxis=dict(title="Gold / Silver · Rebased 100", tickformat=".1f"),
            yaxis2=dict(title="R1 · Gold/Silver Ratio", overlaying="y", side="right", anchor="free", position=0.87, showgrid=False, fixedrange=True, tickformat=".1f"),
            yaxis3=dict(title="R2 · GVZ", overlaying="y", side="right", anchor="free", position=0.98, showgrid=False, fixedrange=True, tickformat=".1f"),
        )
        return fig

    add_line(fig, data, "Gold", "Gold", 2.8, unit=" USD/oz")
    add_line(fig, data, "Silver", "Silver", 2.5, None, "y2", " USD/oz")
    add_line(fig, data, "GoldSilverRatio", "Gold/Silver Ratio", 2.2, "dash", "y3", "x")
    add_line(fig, data, "GVZCLS", "Gold Volatility · GVZ", 2.2, "dot", "y4", "")
    fig.update_layout(
        yaxis2=dict(overlaying="y", side="right", anchor="free", position=0.78),
        yaxis3=dict(overlaying="y", side="right", anchor="free", position=0.88),
        yaxis4=dict(overlaying="y", side="right", anchor="free", position=0.98),
    )
    fig = apply_chart_style(fig, chart_height(330, 450), date_range)
    fig.update_layout(
        margin=dict(l=68, r=220, t=72, b=34, pad=2),
        legend=dict(y=1.09, x=0.01),
        xaxis=dict(domain=[0.0, 0.75]),
        yaxis=dict(title="Gold · USD/oz", tickformat=",.0f"),
        yaxis2=dict(title="R1 · Silver · USD/oz", overlaying="y", side="right", anchor="free", position=0.78, showgrid=False, fixedrange=True, tickformat=".1f"),
        yaxis3=dict(title="R2 · Gold/Silver", overlaying="y", side="right", anchor="free", position=0.88, showgrid=False, fixedrange=True, tickformat=".1f"),
        yaxis4=dict(title="R3 · GVZ", overlaying="y", side="right", anchor="free", position=0.98, showgrid=False, fixedrange=True, tickformat=".1f"),
    )
    return fig
'''

if 'def build_fig10(' not in text:
    marker = '\nPARAM_DESCRIPTIONS = ['
    if marker not in text:
        raise RuntimeError('PARAM_DESCRIPTIONS anchor not found')
    text = text.replace(marker, metals_builder + marker, 1)

metals_description = r'''\n\nPRECIOUS_METALS_DESCRIPTION = '<b>参数概念：</b><br>1. Gold：COMEX 黄金连续近月期货 GC=F 日收盘价，单位 USD/oz。<br>2. Silver：COMEX 白银连续近月期货 SI=F 日收盘价，单位 USD/oz。<br>3. Gold/Silver Ratio：金价 ÷ 银价；上升表示黄金相对白银更强，下降表示白银相对更强。<br>4. Gold Volatility / GVZ：Cboe Gold ETF Volatility Index，反映黄金相关期权的隐含波动率。<br><br><b>读取提示：</b>默认 Rebased 100 用于比较金银相对强弱；Raw 模式保留金银绝对价格，并为 Silver、金银比和 GVZ 使用独立右轴，避免不同量纲互相压缩。'\n'''
if 'PRECIOUS_METALS_DESCRIPTION =' not in text:
    marker = '\ncompact_mode = False'
    if marker not in text:
        raise RuntimeError('compact_mode anchor not found')
    text = text.replace(marker, metals_description + marker, 1)

# Insert Chart 10 after Chart 9 sources, before the divider closing the macro block.
if '10. Precious Metals' not in text:
    anchor = '''    add_sources([\n        ("Cboe VIX", "https://www.cboe.com/tradable-products/vix/"),\n        ("Cboe VIXEQ / Dispersion", "https://www.cboe.com/us/indices/dispersion/"),\n        ("FRED VIX3M (VXVCLS)", "https://fred.stlouisfed.org/series/VXVCLS"),\n        ("FRED S&P 500 (SP500)", "https://fred.stlouisfed.org/series/SP500"),\n    ])\n    st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)'''
    insert = '''    add_sources([\n        ("Cboe VIX", "https://www.cboe.com/tradable-products/vix/"),\n        ("Cboe VIXEQ / Dispersion", "https://www.cboe.com/us/indices/dispersion/"),\n        ("FRED VIX3M (VXVCLS)", "https://fred.stlouisfed.org/series/VXVCLS"),\n        ("FRED S&P 500 (SP500)", "https://fred.stlouisfed.org/series/SP500"),\n    ])\n    st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)\n\n    st.markdown(\n        '<div class="section-kicker">PRECIOUS METALS</div>'\n        '<div class="section-title">10. Precious Metals</div>'\n        '<div class="section-description">Gold / Silver · Gold/Silver Ratio (R1) · Gold Volatility GVZ (R2/R3)</div>',\n        unsafe_allow_html=True,\n    )\n    metals_range = st.radio(\n        "时间范围", RANGES, horizontal=True, index=1,\n        key="precious_metals_range", label_visibility="collapsed",\n    )\n    metals_mode = st.radio(\n        "市场显示", ["Rebased 100", "Raw"], horizontal=True, index=0,\n        key="precious_metals_mode", label_visibility="collapsed",\n    )\n    st.plotly_chart(build_fig10(metals_range, metals_mode), use_container_width=True, config=PLOTLY_CONFIG)\n    st.markdown(f'<div class="mini-description">{PRECIOUS_METALS_DESCRIPTION}</div>', unsafe_allow_html=True)\n    add_sources([\n        ("Yahoo Finance · Gold Futures GC=F", "https://finance.yahoo.com/quote/GC=F/history/"),\n        ("Yahoo Finance · Silver Futures SI=F", "https://finance.yahoo.com/quote/SI=F/history/"),\n        ("FRED · Cboe Gold ETF Volatility Index (GVZCLS)", "https://fred.stlouisfed.org/series/GVZCLS"),\n        ("Cboe · Gold Volatility", "https://www.cboe.com/tradable_products/vix/vix_historical_data/"),\n    ])\n    st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)'''
    if anchor not in text:
        raise RuntimeError('chart9 render anchor not found')
    text = text.replace(anchor, insert, 1)

APP.write_text(text, encoding='utf-8')
print('Applied Chart 4 multi-axis readability fix and added Chart 10 precious metals.')
