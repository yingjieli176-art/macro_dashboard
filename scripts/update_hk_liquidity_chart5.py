from pathlib import Path

APP = Path('app.py')
text = APP.read_text(encoding='utf-8')
start = text.index('# === HK LIQUIDITY CHART 5 ===')
end = text.index('def build_fig1(date_range):', start)
new_block = '''# === HK LIQUIDITY CHART 5 ===
@st.cache_data(ttl=3600, show_spinner=False)
def _hkma_get_all(url, params=None, page_size=100, max_pages=60):
    rows = []
    base_params = dict(params or {})
    for page in range(max_pages):
        try:
            query = {**base_params, "offset": page * page_size, "pagesize": page_size}
            response = requests.get(url, params=query, timeout=10)
            response.raise_for_status()
            result = (response.json() or {}).get("result") or {}
            batch = result.get("records") or result.get("data") or result.get("datas") or []
            if isinstance(batch, dict):
                batch = batch.get("records") or batch.get("data") or batch.get("datas") or []
            if not batch:
                break
            rows.extend(batch)
            if len(batch) < page_size:
                break
        except Exception:
            break
    return rows

@st.cache_data(ttl=3600, show_spinner=False)
def get_hk_liquidity():
    empty_cols = ["observation_date", "Aggregate Balance", "HIBOR O/N", "HIBOR 1M", "HIBOR 3M", "HKMA Base Rate", "M2 YoY", "M3 YoY", "USD/HKD", "Strong-side CU", "Linked Rate", "Weak-side CU"]
    money_url = "https://api.hkma.gov.hk/public/market-data-and-statistics/monthly-statistical-bulletin/financial/monetary-statistics"
    # Use an explicit date window instead of relying on the endpoint's default page.
    # This avoids losing the older monthly records when the API default page is small.
    money_rows = _hkma_get_all(
        money_url,
        params={
            "choose": "end_of_month",
            "from": "2010-01",
            "to": "2099-12",
            "sortby": "end_of_month",
            "sortorder": "asc",
        },
        page_size=1000,
        max_pages=3,
    )
    money = pd.DataFrame(money_rows)
    if money.empty:
        return pd.DataFrame(columns=empty_cols)

    money["observation_date"] = pd.to_datetime(money.get("end_of_month"), format="%Y-%m", errors="coerce")
    # The API can include annual summary rows such as YYYY-00. They are not monthly observations.
    money = money[money["observation_date"].notna()]
    raw_period = money.get("end_of_month", pd.Series(index=money.index, dtype="object")).astype(str)
    money = money[raw_period.str.match(r"^\\d{4}-(0[1-9]|1[0-2])$")]
    money["Aggregate Balance"] = pd.to_numeric(money.get("aggr_balance"), errors="coerce") / 1000.0
    money["HIBOR O/N"] = pd.to_numeric(money.get("hibor_fixing_overnight"), errors="coerce")
    money["HIBOR 3M"] = pd.to_numeric(money.get("hibor_fixing_3m"), errors="coerce")
    money["HKMA Base Rate"] = pd.to_numeric(money.get("discount_window_base_rate"), errors="coerce")
    money["M2"] = pd.to_numeric(money.get("m2_hkd"), errors="coerce")
    money["M3"] = pd.to_numeric(money.get("m3_hkd"), errors="coerce")
    money["USD/HKD"] = pd.to_numeric(money.get("exrate_hkd_usd"), errors="coerce")
    money = money.sort_values("observation_date").drop_duplicates("observation_date")
    money["M2 YoY"] = money["M2"].pct_change(12) * 100.0
    money["M3 YoY"] = money["M3"].pct_change(12) * 100.0
    money["Strong-side CU"] = 7.75
    money["Linked Rate"] = 7.80
    money["Weak-side CU"] = 7.85
    money["HIBOR 1M"] = pd.NA

    # Daily interbank data is aggregated to calendar-month averages so the chart is genuinely monthly.
    interbank_url = "https://api.hkma.gov.hk/public/market-data-and-statistics/daily-monetary-statistics/daily-figures-interbank-liquidity"
    daily_rows = _hkma_get_all(
        interbank_url,
        params={
            "choose": "end_of_date",
            "from": "2010-01-01",
            "to": "2099-12-31",
            "sortby": "end_of_date",
            "sortorder": "asc",
        },
        page_size=1000,
        max_pages=8,
    )
    if daily_rows:
        daily = pd.DataFrame(daily_rows)
        daily["observation_date"] = pd.to_datetime(daily.get("end_of_date"), errors="coerce")
        daily = daily[daily["observation_date"].notna()].copy()
        daily["Aggregate Balance"] = pd.to_numeric(daily.get("closing_balance"), errors="coerce") / 1000.0
        daily["HIBOR O/N"] = pd.to_numeric(daily.get("hibor_overnight"), errors="coerce")
        daily["HIBOR 1M"] = pd.to_numeric(daily.get("hibor_fixing_1m"), errors="coerce")
        daily["HKMA Base Rate"] = pd.to_numeric(daily.get("disc_win_base_rate"), errors="coerce")
        daily["Strong-side CU"] = pd.to_numeric(daily.get("cu_strongside"), errors="coerce")
        daily["Weak-side CU"] = pd.to_numeric(daily.get("cu_weakside"), errors="coerce")
        daily["Linked Rate"] = 7.80
        daily["month"] = daily["observation_date"].dt.to_period("M").dt.to_timestamp()
        monthly_daily = daily.groupby("month", as_index=False).agg({
            "Aggregate Balance": "mean",
            "HIBOR O/N": "mean",
            "HIBOR 1M": "mean",
            "HKMA Base Rate": "last",
            "Strong-side CU": "last",
            "Linked Rate": "last",
            "Weak-side CU": "last",
        }).rename(columns={"month": "observation_date"})
        money = pd.merge(money, monthly_daily, on="observation_date", how="outer", suffixes=("_monthly", ""))
        for col in ["Aggregate Balance", "HIBOR O/N", "HIBOR 1M", "HKMA Base Rate", "Strong-side CU", "Linked Rate", "Weak-side CU"]:
            money[col] = money[col].combine_first(money.get(f"{col}_monthly"))

    money = money.sort_values("observation_date").drop_duplicates("observation_date")
    return money[empty_cols]

def build_fig5(date_range):
    data = filter_range(get_hk_liquidity(), date_range).copy()
    fig = go.Figure()
    # Chart 5 is intentionally monthly: Aggregate Balance is monthly-average and monetary aggregates are monthly.
    # A 3-month moving average gives a readable macro liquidity trend without inventing observations.
    smooth_cols = ["M2 YoY", "M3 YoY", "Aggregate Balance", "HIBOR O/N", "HIBOR 1M", "HIBOR 3M", "HKMA Base Rate", "USD/HKD"]
    for col in smooth_cols:
        if col in data.columns:
            data[col] = pd.to_numeric(data[col], errors="coerce").rolling(3, min_periods=1).mean()

    for col, name, width, dash in [
        ("M2 YoY", "M2 YoY · 3M MA", 3.0, None),
        ("M3 YoY", "M3 YoY · 3M MA", 2.6, "dash"),
        ("HIBOR O/N", "O/N HIBOR · 3M MA", 1.8, "dot"),
        ("HIBOR 1M", "1M HIBOR · 3M MA", 1.8, "dashdot"),
        ("HIBOR 3M", "3M HIBOR · 3M MA", 1.8, "longdash"),
        ("HKMA Base Rate", "HKMA Base Rate · 3M MA", 2.2, "solid"),
    ]:
        add_line(fig, data, col, name, width, dash)
    add_line(fig, data, "Aggregate Balance", "Aggregate Balance · monthly avg · 3M MA", 3.0, "solid", "y2", unit=" HK$ bn")
    add_line(fig, data, "USD/HKD", "USD/HKD · 3M MA", 2.0, "solid", "y3")
    add_line(fig, data, "Strong-side CU", "Strong-side CU 7.75", 1.2, "dot", "y3")
    add_line(fig, data, "Linked Rate", "Linked Rate 7.80", 1.2, "dash", "y3")
    add_line(fig, data, "Weak-side CU", "Weak-side CU 7.85", 1.2, "dot", "y3")
    fig.update_layout(
        yaxis=dict(title="M2/M3 YoY & Interest Rate (%)", fixedrange=True),
        yaxis2=dict(title="Aggregate Balance (HK$ bn)", overlaying="y", side="right", anchor="free", position=1.0, showgrid=False, zeroline=False, fixedrange=True, automargin=True, tickfont=dict(size=9)),
        yaxis3=dict(title="USD/HKD", overlaying="y", side="right", anchor="free", position=0.94, showgrid=False, zeroline=False, fixedrange=True, automargin=True, tickfont=dict(size=9)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    return apply_chart_style(fig, chart_height(430, 650), date_range)

'''
text = text[:start] + new_block + text[end:]

# Replace the Chart 5 explanation with actual conceptual definitions. HTML <br> is used because
# the existing mini-description container does not preserve literal newline characters.
hk_desc = '<div class="mini-description"><b>参数概念：</b><br>1. Aggregate Balance：香港银行体系在金管局的结算余额，单位为 HK$ million；图中转换为 HK$ billion，月度值取当月每日收市总结余的平均值。<br>2. M2：香港港元广义货币供应量，主要反映公众持有的现金及银行存款等货币性资产。<br>3. M3：香港港元货币供应量的更广口径，在 M2 基础上包含更广泛的货币性项目。<br>4. M2 YoY：M2 相对 12 个月前同月的增长率，用来描述货币供应量的年度变化速度。<br>5. M3 YoY：M3 相对 12 个月前同月的增长率，定义与 M2 YoY 相同，但统计口径更广。<br>6. O/N HIBOR：港元隔夜银行间拆借利率，即隔夜期限的港元银行间资金价格。<br>7. 1M HIBOR：港元 1 个月 HIBOR，表示 1 个月期限的港元银行间资金价格。<br>8. 3M HIBOR：港元 3 个月 HIBOR，表示 3 个月期限的港元银行间资金价格。<br>9. HKMA Base Rate：香港金管局贴现窗基本利率，是香港利率体系中的政策参考利率之一。<br>10. USD/HKD：每 1 美元对应的港元价格；数值越高表示港元相对美元越弱。<br>11. Strong-side CU / Linked Rate / Weak-side CU：联系汇率制度下的 7.75 / 7.80 / 7.85 参考水平，其中 7.75 和 7.85 是强方及弱方兑换保证，7.80 是联系汇率中间水平。<br>12. 3M MA：3 个月移动平均，即当前月与前两个月数据的平均值；用于平滑月度曲线，不会创造新的原始数据点。</div>'
old_normal = '<div class="mini-description">M2/M3 观察货币供应增长；Aggregate Balance 观察银行体系结算流动性；O/N、1M、3M HIBOR 与 HKMA Base Rate 观察港元资金价格及政策利率约束；USD/HKD 观察联系汇率压力。</div>'
text = text.replace(old_normal, hk_desc, 1)
compact_desc = '<div class="mini-description"><b>参数概念：</b><br>1. Aggregate Balance：银行体系在金管局的结算余额；图中为月度平均值。<br>2. M2/M3：香港广义货币供应量；YoY 表示相对去年同期的增长率。<br>3. HIBOR：不同期限的港元银行间拆借利率。<br>4. HKMA Base Rate：金管局贴现窗基本利率。<br>5. USD/HKD：美元兑港元汇率；7.75 / 7.80 / 7.85 为联系汇率制度的强方、中心及弱方参考水平。<br>6. 3M MA：3 个月移动平均，用于平滑月度趋势。</div>'
compact_anchor = 'st.markdown(\'<div class="compact-description">HK M2/M3 / Aggregate Balance / HIBOR / HKMA Rate Corridor / USD-HKD</div>\', unsafe_allow_html=True); hk_range = st.radio(\'时间范围\', RANGES, horizontal=True, index=1, key="compact_hk_liquidity_range", label_visibility=\'collapsed\'); st.plotly_chart(build_fig5(hk_range), use_container_width=True, config=PLOTLY_CONFIG); add_sources'
if compact_anchor in text:
    text = text.replace('st.plotly_chart(build_fig5(hk_range), use_container_width=True, config=PLOTLY_CONFIG); add_sources', 'st.plotly_chart(build_fig5(hk_range), use_container_width=True, config=PLOTLY_CONFIG); ' + compact_desc + '; add_sources', 1)

APP.write_text(text, encoding='utf-8')
print('updated HK liquidity chart 5')
