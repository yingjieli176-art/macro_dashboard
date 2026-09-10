from pathlib import Path


APP = Path("app.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count == 0:
        if new in text:
            return text
        raise RuntimeError(f"patch target missing: {label}")
    if count != 1:
        raise RuntimeError(f"patch target not unique ({count}): {label}")
    return text.replace(old, new, 1)


text = APP.read_text(encoding="utf-8")

text = replace_once(
    text,
    '.chart-divider { margin: 0.65rem 0 1rem; border-top: 1px solid #e5e7eb; }',
    '.chart-divider { margin: 0.30rem 0 0.55rem; border-top: 1px solid #e5e7eb; }',
    "chart divider spacing",
)

text = replace_once(
    text,
    '.section-kicker { color: #9ca3af; font-size: 0.66rem; font-weight: 700; letter-spacing: 0.12em; margin-top: 0.4rem; margin-bottom: -0.35rem; }',
    '.section-kicker { color: #9ca3af; font-size: 0.66rem; font-weight: 700; letter-spacing: 0.12em; margin-top: 0.12rem; margin-bottom: 0.04rem; line-height: 1.1; }',
    "section kicker spacing",
)

text = replace_once(
    text,
    '        margin=dict(l=62, r=144, t=124, b=44, pad=2),\n        xaxis=dict(domain=[0.0, 0.84]),',
    '        margin=dict(l=62, r=144, t=72, b=44, pad=2),\n        legend=dict(y=1.095),\n        xaxis=dict(domain=[0.0, 0.84]),',
    "figure 9 top margin",
)

text = replace_once(
    text,
    '''        add_sources(sources)\n        st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)\n\n\n    st.markdown('<div class="section-kicker">US EQUITY RISK</div>', unsafe_allow_html=True)\n    st.markdown('<div class="section-title">9. US Equity Risk & Volatility Structure</div>', unsafe_allow_html=True)\n    st.markdown('<div class="section-description">VIX · VIXEQ · S&P 500 (R1) · VIX3M−VIX (R2)</div>', unsafe_allow_html=True)\n''',
    '''        add_sources(sources)\n        if hk_index < len(hk_configs) - 1:\n            st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)\n\n    st.markdown(\n        '<div class="section-kicker">US EQUITY RISK</div>'\n        '<div class="section-title">9. US Equity Risk & Volatility Structure</div>'\n        '<div class="section-description">VIX · VIXEQ · S&P 500 (R1) · VIX3M−VIX (R2)</div>',\n        unsafe_allow_html=True,\n    )\n''',
    "HK-to-US risk section transition",
)

APP.write_text(text, encoding="utf-8")
print("equity risk layout tightened")
