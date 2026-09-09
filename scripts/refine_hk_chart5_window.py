from pathlib import Path

APP = Path("app.py")
text = APP.read_text(encoding="utf-8")
original = text

old_window = '''def build_fig5(date_range):
    data = filter_range(get_hk_liquidity(), date_range).copy()'''
new_window = '''def build_fig5(date_range):
    all_data = get_hk_liquidity().copy()
    if all_data.empty:
        data = all_data
    else:
        latest_published = all_data["observation_date"].max()
        offsets = {
            "5Y": pd.DateOffset(years=5),
            "1Y": pd.DateOffset(years=1),
            "6M": pd.DateOffset(months=6),
            "3M": pd.DateOffset(months=3),
            "1M": pd.DateOffset(months=1),
        }
        start = latest_published - offsets[date_range]
        data = all_data[all_data["observation_date"] >= start].copy()'''
if old_window in text:
    text = text.replace(old_window, new_window, 1)

# Replace the old Chart 5 explanatory block in normal mode.
normal_key = 'key="normal_hk_liquidity_range"'
normal_pos = text.find(normal_key)
if normal_pos != -1:
    desc_start = text.find("st.markdown('<div class=\"mini-description\"><b>参数概念：</b>", normal_pos)
    if desc_start != -1:
        desc_end_marker = "); add_sources(["
        desc_end = text.find(desc_end_marker, desc_start)
        if desc_end != -1:
            new_desc = '''st.markdown('<div class="mini-description"><b>参数概念：</b><br>1. HKD M2 YoY：港元 M2 相对 12 个月前的同比增速，用来观察广义港元货币扩张或收缩。<br>2. HKD M3 YoY：港元 M3 同比增速，统计口径较 M2 更广。<br>3. Monetary Base YoY：香港货币基础总量同比变化，用于观察基础货币层面的扩张与收缩。<br>4. Aggregate Balance：银行体系总结余，单位由 HK$ million 转为 HK$ billion；总结余下降通常代表银行体系可用港元流动性趋紧。<br>5. O/N HIBOR：隔夜港元银行同业拆息，反映最短端港元资金价格。<br>6. 3M HIBOR：3 个月港元银行同业拆息，用来观察更持续的港元融资成本。<br>7. HKMA Base Rate：香港金管局基本利率，是港元利率体系的重要政策参考。<br>8. USD/HKD：每 1 美元对应的港元价格；向 7.85 上升表示港元转弱，向 7.75 下降表示港元转强。<br>9. Strong-side CU 7.75：联系汇率制度下强方兑换保证。<br>10. Weak-side CU 7.85：联系汇率制度下弱方兑换保证。<br><br><b>读取提示：</b>M2/M3 为月度统计，公布存在时滞；最新月份如果尚未公布不会向前填充。图表时间范围以 HKMA 最新已发布月份为基准，避免 1M/3M 因发布时间滞后被错误过滤为空。</div>', unsafe_allow_html=True)'''
            text = text[:desc_start] + new_desc + text[desc_end:]

if text != original:
    APP.write_text(text, encoding="utf-8")
    print("refined HK Chart 5 publication window and explanation")
else:
    print("HK Chart 5 publication window already refined")
