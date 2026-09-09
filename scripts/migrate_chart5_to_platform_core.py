from pathlib import Path

APP = Path("app.py")
text = APP.read_text(encoding="utf-8")
original = text

IMPORT = "from macro_platform.hk_liquidity import build_hk_liquidity_figure, liquidity_status_html, load_hk_liquidity\n"
if IMPORT not in text:
    anchor = "import streamlit as st\n"
    if anchor not in text:
        raise RuntimeError("streamlit import anchor not found")
    text = text.replace(anchor, anchor + IMPORT, 1)

start_marker = "# === HK LIQUIDITY CHART 5 ==="
end_marker = "\ndef build_fig1"
start = text.index(start_marker)
end = text.index(end_marker, start)
new_block = '''# === HK LIQUIDITY CHART 5 ===
def get_hk_liquidity():
    return load_hk_liquidity()


def build_fig5(date_range):
    return build_hk_liquidity_figure(date_range, compact_mode=compact_mode)
'''
text = text[:start] + new_block + text[end:]

css = '''
.hk-liquidity-strip { display:grid; grid-template-columns:repeat(7,minmax(0,1fr)); gap:6px; margin:5px 0 10px; }
.hk-liquidity-strip > div { border:1px solid #e5e7eb; border-radius:9px; background:#fff; padding:7px 9px; min-width:0; }
.hk-liquidity-strip span { display:block; color:#9ca3af; font-size:.66rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.hk-liquidity-strip strong { display:block; color:#111827; font-size:.82rem; font-weight:650; margin-top:2px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
@media (max-width:1100px) { .hk-liquidity-strip { grid-template-columns:repeat(4,minmax(0,1fr)); } }
@media (max-width:700px) { .hk-liquidity-strip { grid-template-columns:repeat(2,minmax(0,1fr)); } }
'''
if ".hk-liquidity-strip" not in text:
    style_end = "</style>\n\"\"\", unsafe_allow_html=True)"
    if style_end not in text:
        raise RuntimeError("style end anchor not found")
    text = text.replace(style_end, css + "\n</style>\n\"\"\", unsafe_allow_html=True)", 1)

chart_call = 'st.plotly_chart(build_fig5(hk_range), use_container_width=True, config=PLOTLY_CONFIG);'
status_call = chart_call + ' st.markdown(liquidity_status_html(), unsafe_allow_html=True);'
if status_call not in text:
    count = text.count(chart_call)
    if count < 2:
        raise RuntimeError(f"expected two Chart 5 render calls, found {count}")
    text = text.replace(chart_call, status_call)

# Chart 5 copy follows the faster monthly signal design. YoY remains in the data model only as context.
replacements = {
    "HKD M2/M3 / Monetary Base / Aggregate Balance / HIBOR / HKMA Base Rate / USD-HKD / 7.75-7.85 CU":
        "HKD M2/M3 MoM / Monetary Base MoM / Aggregate Balance / HIBOR / O/N−3M Spread (R) / USD-HKD / 7.75-7.85 CU",
    "HKD M2/M3、货币基础、银行体系总结余、HIBOR、HKMA Base Rate 与 USD/HKD 强弱方兑换保证":
        "HKD M2/M3 月环比、货币基础月环比、银行体系总结余、HIBOR、O/N−3M 利差（R）与 USD/HKD 强弱方兑换保证",
    "HKD M2 YoY：港元 M2 相对 12 个月前的同比增速，用来观察广义港元货币扩张或收缩。":
        "HKD M2 MoM：港元 M2 月环比增速，用来观察广义港元货币的边际扩张或收缩；比同比变化更适合判断当前流动性方向。",
    "HKD M3 YoY：港元 M3 同比增速，统计口径较 M2 更广。":
        "HKD M3 MoM：港元 M3 月环比增速，统计口径较 M2 更广，用于交叉确认广义货币边际变化。",
    "Monetary Base YoY：香港货币基础总量同比变化，用于观察基础货币层面的扩张与收缩。":
        "Monetary Base MoM：香港货币基础总量月环比变化，用于观察基础货币层面的边际扩张与收缩。",
    "7. HKMA Base Rate：香港金管局基本利率，是港元利率体系的重要政策参考。<br>8. USD/HKD":
        "7. HKMA Base Rate：香港金管局基本利率，是港元利率体系的重要政策参考。<br>8. O/N−3M Spread（R）：隔夜 HIBOR 减 3M HIBOR，右轴单位 bp；显著转正通常代表短端资金压力上升。<br>9. USD/HKD",
    "<br>9. Strong-side CU 7.75": "<br>10. Strong-side CU 7.75",
    "<br>10. Weak-side CU 7.85": "<br>11. Weak-side CU 7.85",
    "<b>读取提示：</b>M2/M3 为月度统计，公布存在时滞；最新月份如果尚未公布不会向前填充。":
        "<b>读取提示：</b>M2/M3 为月度统计，公布存在时滞；最新月份如果尚未公布不会向前填充。主图使用 MoM 观察边际变化，流动性评分使用最近 3 个月 M2/M3 MoM 均值降低单月噪声。",
}
for old, new in replacements.items():
    if old in text:
        text = text.replace(old, new)

if text != original:
    APP.write_text(text, encoding="utf-8")
    print("migrated Chart 5 to macro_platform core and aligned monthly signal copy")
else:
    print("Chart 5 already uses macro_platform core and monthly copy")
