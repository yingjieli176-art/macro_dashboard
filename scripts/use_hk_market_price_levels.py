from pathlib import Path

HK = Path("macro_platform/hk_liquidity.py")
APP = Path("app.py")

# --- Hong Kong market overlays: use raw monthly close / index levels, not % changes ---
hk = HK.read_text(encoding="utf-8")
original_hk = hk

hk = hk.replace("def _market_monthly_change(", "def _market_monthly_close(", 1)
hk = hk.replace(
    '        frame[label] = frame["close"].pct_change(fill_method=None) * 100.0\n        return frame[["observation_date", label]].dropna(subset=[label])',
    '        frame[label] = frame["close"]\n        return frame[["observation_date", label]].dropna(subset=[label])',
    1,
)
hk = hk.replace(
    '# Market overlays use monthly close-to-close percentage changes so they are\n    # directly comparable with the monthly liquidity impulse in 5-1.\n    hkex_change = _market_monthly_change("0388.HK", "HKEX Price Change")\n    hstech_change = _market_monthly_change("HSTECH.HK", "HSTECH Change")\n    market_data = data[["observation_date"]].copy()\n    for frame in (hkex_change, hstech_change):',
    '# Market overlays use month-end price/index levels. No percentage transformation is applied.\n    hkex_price = _market_monthly_close("0388.HK", "HKEX Price")\n    hstech_index = _market_monthly_close("HSTECH.HK", "HSTECH Index")\n    market_data = data[["observation_date"]].copy()\n    for frame in (hkex_price, hstech_index):',
    1,
)

replacements = {
    'add_line(money, market_data, "HKEX Price Change", "HKEX Price Change (R)", "#0891b2", 2.1, secondary_y=True)':
        'add_line(money, market_data, "HKEX Price", "HKEX Price (R)", "#0891b2", 2.1, unit=" HKD", secondary_y=True)',
    'add_line(money, market_data, "HSTECH Change", "HSTECH Change (R)", "#db2777", 2.1, "dash", secondary_y=True)':
        'add_line(money, market_data, "HSTECH Index", "HSTECH Index (R)", "#db2777", 2.1, "dash", unit=" pts", secondary_y=True)',
    'title_text="Market Change (%)", secondary_y=True,':
        'title_text="Market Price / Index Level", secondary_y=True,',
    'add_line(fx, market_data, "HKEX Price Change", "HKEX Price Change (R)", "#0891b2", 2.1, secondary_y=True)':
        'add_line(fx, market_data, "HKEX Price", "HKEX Price (R)", "#0891b2", 2.1, unit=" HKD", secondary_y=True)',
    'add_line(fx, market_data, "HSTECH Change", "HSTECH Change (R)", "#db2777", 2.1, "dash", secondary_y=True)':
        'add_line(fx, market_data, "HSTECH Index", "HSTECH Index (R)", "#db2777", 2.1, "dash", unit=" pts", secondary_y=True)',
}
for old, new in replacements.items():
    hk = hk.replace(old, new)

if hk == original_hk:
    raise RuntimeError("No Hong Kong market-level changes were applied")
HK.write_text(hk, encoding="utf-8")
print("macro_platform/hk_liquidity.py updated to market price levels")

# --- app.py parameter descriptions and section copy ---
app = APP.read_text(encoding="utf-8")
original_app = app

app = app.replace(
    '4. HKEX Price Change（R）：港交所 0388.HK 月末收盘价相对上月的涨跌幅，右轴单位 %；用于观察香港市场交易活跃度与流动性环境的市场映射。<br>5. HSTECH Change（R）：恒生科技指数 HSTECH.HK 月度涨跌幅，右轴单位 %；用于观察高贝塔科技资产对香港流动性变化的反应。',
    '4. HKEX Price（R）：港交所 0388.HK 月末收盘价，右轴单位 HKD；用于观察香港交易所股价与货币流动性变化之间的市场映射。<br>5. HSTECH Index（R）：恒生科技指数 HSTECH.HK 月末指数点位，右轴单位 points；用于观察高贝塔科技资产价格水平与香港流动性环境的关系。',
    1,
)
app = app.replace(
    '5. HKEX Price Change（R）：港交所 0388.HK 月度涨跌幅，右轴单位 %。<br>6. HSTECH Change（R）：恒生科技指数 HSTECH.HK 月度涨跌幅，右轴单位 %。<br><br><b>读取提示：</b>灰色淡色区域表示 7.75–7.85 联系汇率兑换保证区间；7.80 为区间中点参考。市场涨跌幅用于对照汇率位置与香港风险资产表现。',
    '5. HKEX Price（R）：港交所 0388.HK 月末收盘价，右轴单位 HKD。<br>6. HSTECH Index（R）：恒生科技指数 HSTECH.HK 月末指数点位，右轴单位 points。<br><br><b>读取提示：</b>灰色淡色区域表示 7.75–7.85 联系汇率兑换保证区间；7.80 为区间中点参考。市场价格水平用于对照汇率位置与香港风险资产表现。',
    1,
)
app = app.replace(
    'Money supply / HKEX & HSTECH monthly change / Aggregate Balance / HIBOR / USD-HKD / 7.75–7.85 LERS band',
    'Money supply / HKEX price & HSTECH index / Aggregate Balance / HIBOR / USD-HKD / 7.75–7.85 LERS band',
    1,
)

# Add a market-data source once to the Hong Kong module source list.
needle = '        ("HKMA Open API", "https://apidocs.hkma.gov.hk/"),\n'
if needle in app and 'Yahoo Finance Market Data' not in app:
    app = app.replace(
        needle,
        needle + '        ("Yahoo Finance Market Data", "https://finance.yahoo.com/"),\n',
        1,
    )

if app == original_app:
    raise RuntimeError("No app.py market-level copy changes were applied")
APP.write_text(app, encoding="utf-8")
print("app.py updated to market price-level descriptions")
