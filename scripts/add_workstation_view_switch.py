from pathlib import Path

APP = Path("app.py")
text = APP.read_text(encoding="utf-8")

switch_block = r'''

# Workstation view mode: desktop is the deliberate default; mobile is an
# explicit compact workspace rather than a browser-width guess.
_view_left, _view_right = st.columns([5, 2])
with _view_right:
    workstation_view = st.segmented_control(
        "视图模式",
        options=["电脑", "手机"],
        default="电脑",
        selection_mode="single",
        key="workstation_view_mode",
        label_visibility="collapsed",
    ) or "电脑"
compact_mode = workstation_view == "手机"

st.markdown(
    f'<div class="view-mode-note">VIEW · {"MOBILE COMPACT" if compact_mode else "DESKTOP WORKSTATION"}</div>',
    unsafe_allow_html=True,
)

if compact_mode:
    st.markdown(
        """
        <style>
        .block-container {
            max-width: 760px !important;
            padding-top: .35rem !important;
            padding-left: .55rem !important;
            padding-right: .55rem !important;
            padding-bottom: 1.5rem !important;
        }
        .dashboard-header { padding: 2px 0 6px !important; margin-bottom: 6px !important; }
        .dashboard-links { display: none !important; }
        .dashboard-title { font-size: 1.42rem !important; }
        .dashboard-subtitle { font-size: .72rem !important; line-height: 1.35 !important; }
        .section-kicker { font-size: .58rem !important; }
        .section-title { font-size: 1.02rem !important; min-height: 23px !important; margin-top: .26rem !important; }
        .section-description { font-size: .70rem !important; min-height: 16px !important; margin-bottom: .08rem !important; }
        .mini-description { font-size: .66rem !important; line-height: 1.35 !important; }
        .source-text { font-size: .64rem !important; }
        .chart-divider { margin: .08rem 0 .22rem !important; }
        div[data-testid="stPlotlyChart"] { border-radius: 7px !important; padding: 0 !important; }
        div[data-testid="stRadio"] label, div[data-testid="stSegmentedControl"] label { font-size: .72rem !important; }
        .market-groups { grid-template-columns: 1fr !important; gap: 5px !important; }
        .hk-liquidity-strip { grid-template-columns: repeat(2, minmax(0,1fr)) !important; gap: 4px !important; }
        .news-box { max-height: 520px !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )
'''

if 'key="workstation_view_mode"' not in text:
    anchor = "\ndef _load_watchlists():"
    if anchor not in text:
        raise RuntimeError("view switch anchor not found")
    text = text.replace(anchor, switch_block + anchor, 1)

# The view switch above owns compact_mode. Do not reset it later in the file.
text = text.replace("\ncompact_mode = False\n\ndef render_core_charts():", "\n# compact_mode is selected by the workstation view switch above.\n\ndef render_core_charts():", 1)

# Make multi-axis charts retain readable plotting area in the explicit mobile
# view while preserving the existing desktop workstation geometry.
text = text.replace(
    'margin=dict(l=64, r=164, t=72, b=34, pad=2),\n        legend=dict(y=1.09, x=0.01),\n        xaxis=dict(domain=[0.0, 0.82]),',
    'margin=dict(l=50 if compact_mode else 64, r=118 if compact_mode else 164, t=62 if compact_mode else 72, b=30 if compact_mode else 34, pad=2),\n        legend=dict(y=1.08 if compact_mode else 1.09, x=0.01),\n        xaxis=dict(domain=[0.0, 0.78 if compact_mode else 0.82]),',
    1,
)
text = text.replace(
    'margin=dict(l=62, r=150, t=72, b=34, pad=2),\n            legend=dict(y=1.09, x=0.01),\n            xaxis=dict(domain=[0.0, 0.84]),',
    'margin=dict(l=48 if compact_mode else 62, r=108 if compact_mode else 150, t=62 if compact_mode else 72, b=30 if compact_mode else 34, pad=2),\n            legend=dict(y=1.08 if compact_mode else 1.09, x=0.01),\n            xaxis=dict(domain=[0.0, 0.78 if compact_mode else 0.84]),',
    1,
)
text = text.replace(
    'margin=dict(l=68, r=220, t=72, b=34, pad=2),\n        legend=dict(y=1.09, x=0.01),\n        xaxis=dict(domain=[0.0, 0.75]),',
    'margin=dict(l=50 if compact_mode else 68, r=152 if compact_mode else 220, t=62 if compact_mode else 72, b=30 if compact_mode else 34, pad=2),\n        legend=dict(y=1.08 if compact_mode else 1.09, x=0.01),\n        xaxis=dict(domain=[0.0, 0.68 if compact_mode else 0.75]),',
    1,
)

# A small, terminal-like mode indicator; intentionally subdued on desktop.
if ".view-mode-note" not in text:
    css_anchor = '.section-toolbar-note { color: #9ca3af; font-size: 0.72rem; margin-top: -0.15rem; margin-bottom: 0.5rem; }'
    css_add = css_anchor + '\n.view-mode-note { color:#9ca3af; font-size:.60rem; letter-spacing:.11em; text-align:right; margin:-4px 2px 4px; }'
    if css_anchor not in text:
        raise RuntimeError("CSS anchor not found")
    text = text.replace(css_anchor, css_add, 1)

APP.write_text(text, encoding="utf-8")
print("Added desktop/mobile workstation view switch; desktop remains default.")
