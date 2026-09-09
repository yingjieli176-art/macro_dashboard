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

if text != original:
    APP.write_text(text, encoding="utf-8")
    print("migrated Chart 5 to macro_platform core")
else:
    print("Chart 5 already uses macro_platform core")
