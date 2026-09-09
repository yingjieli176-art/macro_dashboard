from pathlib import Path

APP = Path("app.py")
HK = Path("macro_platform/hk_liquidity.py")

app = APP.read_text(encoding="utf-8")
original_app = app

# Add four Chart 5-specific explanation blocks next to the existing helper.
anchor = 'def show_parameter_description(index): st.markdown(f\'<div class="mini-description">{PARAM_DESCRIPTIONS[index]}</div>\', unsafe_allow_html=True)\n'
if anchor not in app:
    raise RuntimeError("show_parameter_description helper not found")

if "HK_PARAMETER_DESCRIPTIONS = [" not in app:
    hk_desc = '''\nHK_PARAMETER_DESCRIPTIONS = [\n    '<b>参数概念：</b><br>1. HKD M2 MoM：港元 M2 月环比增速，用来观察广义港元货币的边际扩张或收缩；主图采用月环比以提高对当前流动性变化的敏感度。<br>2. HKD M3 MoM：港元 M3 月环比增速，统计口径较 M2 更广，用于交叉确认广义货币边际变化。<br>3. Monetary Base MoM：香港货币基础总量月环比变化，用于观察基础货币层面的边际扩张与收缩。',\n    '<b>参数概念：</b><br>1. Aggregate Balance：银行体系总结余，单位 HK$ billion；总结余下降通常代表银行体系可用港元流动性趋紧，上升则通常代表即时银行体系流动性较充裕。',\n    '<b>参数概念：</b><br>1. O/N HIBOR：隔夜港元银行同业拆息，反映最短端港元资金价格。<br>2. 3M HIBOR：3 个月港元银行同业拆息，用来观察更持续的港元融资成本。<br>3. HKMA Base Rate：香港金管局基本利率，是港元利率体系的重要政策参考。<br>4. O/N−3M Spread（R）：隔夜 HIBOR 减 3M HIBOR，右轴单位 bp；显著转正通常代表短端资金压力上升。',\n    '<b>参数概念：</b><br>1. USD/HKD：每 1 美元对应的港元价格；向 7.85 上升表示港元转弱，向 7.75 下降表示港元转强。<br>2. Strong-side CU 7.75：联系汇率制度下强方兑换保证。<br>3. Weak-side CU 7.85：联系汇率制度下弱方兑换保证。<br><br><b>读取提示：</b>7.75–7.85 是联系汇率兑换保证区间，用于判断港元在强弱方边界附近的位置。',\n]\n\ndef show_hk_parameter_description(index):\n    st.markdown(f'<div class="mini-description">{HK_PARAMETER_DESCRIPTIONS[index]}</div>', unsafe_allow_html=True)\n'''
    app = app.replace(anchor, anchor + hk_desc, 1)

old_render = '''    st.markdown(liquidity_status_html(), unsafe_allow_html=True)\n    for hk_figure in build_fig5(hk_range):\n        st.plotly_chart(hk_figure, use_container_width=True, config=PLOTLY_CONFIG)\n    show_parameter_description(4)\n    add_sources([\n'''
new_render = '''    st.markdown(liquidity_status_html(), unsafe_allow_html=True)\n    hk_figures = build_fig5(hk_range)\n    for hk_index, hk_figure in enumerate(hk_figures):\n        st.plotly_chart(hk_figure, use_container_width=True, config=PLOTLY_CONFIG)\n        show_hk_parameter_description(hk_index)\n        if hk_index < len(hk_figures) - 1:\n            st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)\n    add_sources([\n'''
if old_render not in app:
    raise RuntimeError("current Chart 5 render block not found")
app = app.replace(old_render, new_render, 1)

if app != original_app:
    APP.write_text(app, encoding="utf-8")
    print("app.py: Chart 5 explanations split by figure")
else:
    print("app.py already updated")

hk = HK.read_text(encoding="utf-8")
original_hk = hk
replacements = {
    'style(money, "HK Money Supply")': 'style(money, "5-1. HK Money Supply")',
    'style(balance, "Banking-system Liquidity")': 'style(balance, "5-2. Banking-system Liquidity")',
    'style(funding, "HKD Funding", height=430, right_axis=True)': 'style(funding, "5-3. HKD Funding", height=430, right_axis=True)',
    'style(fx, "USD/HKD Convertibility Band")': 'style(fx, "5-4. USD/HKD Convertibility Band")',
}
for old, new in replacements.items():
    if old in hk:
        hk = hk.replace(old, new, 1)
    elif new not in hk:
        raise RuntimeError(f"Chart title anchor missing: {old}")

if hk != original_hk:
    HK.write_text(hk, encoding="utf-8")
    print("hk_liquidity.py: split figures numbered 5-1 through 5-4")
else:
    print("hk_liquidity.py titles already numbered")
