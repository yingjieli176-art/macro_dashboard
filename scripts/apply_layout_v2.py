from pathlib import Path

APP = Path("app.py")
text = APP.read_text(encoding="utf-8")
original = text


def replace_once(old: str, new: str, label: str) -> None:
    global text
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f"layout patch target not found: {label}")
    text = text.replace(old, new, 1)


# 1) Repository link used by the top navigation.
replace_once(
    'WATCHLIST_PARAM = "watchlist"\n',
    'WATCHLIST_PARAM = "watchlist"\nREPO_URL = "https://github.com/yingjieli176-art/macro_dashboard"\n',
    "repo url",
)

# 2) Tighten the overall canvas and add reusable layout/navigation styles.
replace_once(
    '.block-container { padding-top: 1.05rem; padding-bottom: 2.5rem; max-width: 1900px; }',
    '.block-container { padding-top: 0.85rem; padding-bottom: 3rem; max-width: 1760px; }',
    "page width",
)

extra_css = r'''
html { scroll-behavior: smooth; }
.dashboard-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; padding: 4px 0 14px; margin-bottom: 14px; border-bottom: 1px solid #e5e7eb; }
.dashboard-heading { min-width: 0; }
.dashboard-eyebrow { color: #9ca3af; font-size: 0.68rem; font-weight: 700; letter-spacing: 0.14em; margin-bottom: 2px; }
.dashboard-subtitle { color: #6b7280; font-size: 0.82rem; line-height: 1.5; margin-top: 2px; }
.dashboard-links { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 6px; max-width: 620px; padding-top: 4px; }
.dashboard-links a { color: #374151 !important; text-decoration: none !important; font-size: 0.76rem; line-height: 1; padding: 7px 10px; border: 1px solid #e5e7eb; border-radius: 999px; background: #fff; white-space: nowrap; }
.dashboard-links a:hover { border-color: #9ca3af; background: #f9fafb; color: #111827 !important; }
.dashboard-links a.external { font-weight: 650; }
.section-anchor { height: 0; visibility: hidden; scroll-margin-top: 18px; }
.section-kicker { color: #9ca3af; font-size: 0.66rem; font-weight: 700; letter-spacing: 0.12em; margin-top: 0.4rem; margin-bottom: -0.35rem; }
.section-toolbar-note { color: #9ca3af; font-size: 0.72rem; margin-top: -0.15rem; margin-bottom: 0.5rem; }
div[data-testid="stVerticalBlockBorderWrapper"] { border-color: #e5e7eb !important; border-radius: 12px !important; }
div[data-testid="stPlotlyChart"] { border: 1px solid #eef2f7; border-radius: 12px; padding: 2px 4px 0; background: #fff; overflow: hidden; }
.stButton > button { border-radius: 8px; }
.source-text a { display: inline-block; padding: 1px 0; }
.market-group { border-radius: 12px; padding: 9px 10px 8px; }
.news-box { border-radius: 12px; padding: 8px 12px; }
@media (max-width: 1100px) {
  .dashboard-header { display: block; }
  .dashboard-links { justify-content: flex-start; max-width: none; margin-top: 10px; }
}
@media (max-width: 700px) {
  .block-container { padding-left: 0.75rem; padding-right: 0.75rem; }
  .dashboard-links a { font-size: 0.72rem; padding: 6px 8px; }
  .dashboard-title { font-size: 1.55rem; }
  .section-title { font-size: 1.12rem; }
}
'''

style_end = '</style>\n""", unsafe_allow_html=True)'
if extra_css.strip() not in text:
    if style_end not in text:
        raise RuntimeError("layout patch target not found: style end")
    text = text.replace(style_end, extra_css + '\n</style>\n""", unsafe_allow_html=True)', 1)

# 3) Replace the bare title with a real header and navigation links.
old_title = 'st.markdown(\'<div class="dashboard-title">Macro Dashboard</div>\', unsafe_allow_html=True)'
new_title = '''st.markdown(
    f\"\"\"
    <div class=\"dashboard-header\">
      <div class=\"dashboard-heading\">
        <div class=\"dashboard-eyebrow\">MACRO · LIQUIDITY · RATES</div>
        <div class=\"dashboard-title\">Macro Dashboard</div>
        <div class=\"dashboard-subtitle\">跨市场行情、利率、流动性与 7×24 财经信息面板</div>
      </div>
      <div class=\"dashboard-links\">
        <a href=\"#market-overview\">市场概览</a>
        <a href=\"#watchlist\">自选观察</a>
        <a href=\"#macro-charts\">宏观图表</a>
        <a href=\"#news\">财经快讯</a>
        <a class=\"external\" href=\"{REPO_URL}\" target=\"_blank\" rel=\"noopener noreferrer\">GitHub ↗</a>
      </div>
    </div>
    \"\"\",
    unsafe_allow_html=True,
)'''
replace_once(old_title, new_title, "dashboard header")

# 4) Give the major regions stable anchors and clearer visual hierarchy.
replace_once(
    'render_market_groups()\nst.caption(f"行情数据刷新时间：{time.strftime(\'%Y-%m-%d %H:%M:%S\', time.localtime())}")',
    'st.markdown(\'<div id="market-overview" class="section-anchor"></div><div class="section-kicker">MARKET OVERVIEW</div>\', unsafe_allow_html=True)\n'
    'st.markdown(\'<div class="section-title">市场概览</div><div class="section-description">美股、港股与 A 股主要指数 · 行情模块每 60 秒刷新</div>\', unsafe_allow_html=True)\n'
    'render_market_groups()\n'
    'st.caption(f"行情数据刷新时间：{time.strftime(\'%Y-%m-%d %H:%M:%S\', time.localtime())}")',
    "market section",
)

replace_once(
    'render_watchlist_refresh_control()\n\n@st.fragment(run_every="60s")',
    'st.markdown(\'<div id="watchlist" class="section-anchor"></div><div class="section-kicker">WATCHLIST</div>\', unsafe_allow_html=True)\n'
    'st.markdown(\'<div class="section-title">自选观察</div><div class="section-description">按市场添加股票模块；刷新、搜索与删除操作集中在本区域</div>\', unsafe_allow_html=True)\n'
    'render_watchlist_refresh_control()\n\n@st.fragment(run_every="60s")',
    "watchlist section",
)

# Put watchlist and news actions on the right so content aligns vertically.
replace_once(
    'def render_watchlist_refresh_control():\n    refresh_col, _, _ = st.columns([1.2, 3.8, 1], vertical_alignment="top")\n    with refresh_col:',
    'def render_watchlist_refresh_control():\n    _, refresh_col = st.columns([5, 1], vertical_alignment="top")\n    with refresh_col:',
    "watchlist refresh alignment",
)

replace_once(
    'render_core_charts()\nst.markdown(\'<div class="chart-divider"></div>\', unsafe_allow_html=True)',
    'st.markdown(\'<div id="macro-charts" class="section-anchor"></div><div class="section-kicker">MACRO CHARTS</div>\', unsafe_allow_html=True)\n'
    'render_core_charts()\n'
    'st.markdown(\'<div class="chart-divider"></div>\', unsafe_allow_html=True)',
    "macro anchor",
)

replace_once(
    'st.markdown(\'<div class="section-title">📰 7×24 重点财经快讯</div>\', unsafe_allow_html=True)',
    'st.markdown(\'<div id="news" class="section-anchor"></div><div class="section-kicker">NEWS</div>\', unsafe_allow_html=True)\n'
    'st.markdown(\'<div class="section-title">📰 7×24 重点财经快讯</div>\', unsafe_allow_html=True)',
    "news anchor",
)

replace_once(
    'def render_news_panel():\n    col1, col2 = st.columns([1, 5])\n    with col1:',
    'def render_news_panel():\n    _, action_col = st.columns([5, 1])\n    with action_col:',
    "news refresh alignment",
)

# Avoid creating a noisy empty commit when the patch is already present.
if text != original:
    APP.write_text(text, encoding="utf-8")
    print("applied dashboard layout v2")
else:
    print("dashboard layout v2 already applied")
