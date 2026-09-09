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
            response = requests.get(url, params=query, timeout=8)
            response.raise_for_status()
            result = (response.json() or {}).get("result") or {}
            batch = result.get("records") or result.get("data") or result.get("datas") or []
            if isinstance(batch, dict):
                batch = batch.get("records") or batch.get("data") or batch.get("datas") or []
            if not batch: break
            rows.extend(batch)
            if len(batch) < page_size: break
        except Exception:
            break
    return rows

@st.cache_data(ttl=3600, show_spinner=False)
def get_hk_liquidity():
    empty_cols = ["observation_date", "Aggregate Balance", "HIBOR O/N", "HIBOR 1M", "HIBOR 3M", "HKMA Base Rate", "M2 YoY", "M3 YoY", "USD/HKD", "Strong-side CU", "Linked Rate", "Weak-side CU"]
    money_url = "https://api.hkma.gov.hk/public/market-data-and-statistics/monthly-statistical-bulletin/financial/monetary-statistics"
    money_rows = _hkma_get_all(money_url, page_size=100, max_pages=5)
    money = pd.DataFrame(money_rows)
    if money.empty:
        return pd.DataFrame(columns=empty_cols)
    money["observation_date"] = pd.to_datetime(money.get("end_of_month"), format="%Y-%m", errors="coerce")
    money["Aggregate Balance"] = pd.to_numeric(money.get("aggr_balance"), errors="coerce") / 1000.0
    money["HIBOR O/N"] = pd.to_numeric(money.get("hibor_fixing_overnight"), errors="coerce")
    money["HIBOR 3M"] = pd.to_numeric(money.get("hibor_fixing_3m"), errors="coerce")
    money["HKMA Base Rate"] = pd.to_numeric(money.get("discount_window_base_rate"), errors="coerce")
    money["M2"] = pd.to_numeric(money.get("m2_hkd"), errors="coerce")
    money["M3"] = pd.to_numeric(money.get("m3_hkd"), errors="coerce")
    money["USD/HKD"] = pd.to_numeric(money.get("exrate_hkd_usd"), errors="coerce")
    money = money.dropna(subset=["observation_date"]).sort_values("observation_date").drop_duplicates("observation_date")
    money["M2 YoY"] = money["M2"].pct_change(12) * 100.0
    money["M3 YoY"] = money["M3"].pct_change(12) * 100.0
    money["Strong-side CU"] = 7.75
    money["Linked Rate"] = 7.80
    money["Weak-side CU"] = 7.85
    money["HIBOR 1M"] = pd.NA
    interbank_url = "https://api.hkma.gov.hk/public/market-data-and-statistics/daily-monetary-statistics/daily-figures-interbank-liquidity"
    daily_rows = _hkma_get_all(interbank_url, params={"sortby": "end_of_date", "sortorder": "desc"}, page_size=100, max_pages=1)
    if daily_rows:
        daily = pd.DataFrame(daily_rows)
        daily["observation_date"] = pd.to_datetime(daily.get("end_of_date"), errors="coerce")
        daily["Aggregate Balance"] = pd.to_numeric(daily.get("closing_balance"), errors="coerce") / 1000.0
        daily["HIBOR O/N"] = pd.to_numeric(daily.get("hibor_overnight"), errors="coerce")
        daily["HIBOR 1M"] = pd.to_numeric(daily.get("hibor_fixing_1m"), errors="coerce")
        daily["HKMA Base Rate"] = pd.to_numeric(daily.get("disc_win_base_rate"), errors="coerce")
        daily["Strong-side CU"] = pd.to_numeric(daily.get("cu_strongside"), errors="coerce")
        daily["Weak-side CU"] = pd.to_numeric(daily.get("cu_weakside"), errors="coerce")
        daily["Linked Rate"] = 7.80
        daily = daily.dropna(subset=["observation_date"]).sort_values("observation_date")
        daily_cols = ["observation_date", "Aggregate Balance", "HIBOR O/N", "HIBOR 1M", "HKMA Base Rate", "Strong-side CU", "Linked Rate", "Weak-side CU"]
        daily = daily[daily_cols].drop_duplicates("observation_date")
        money = pd.merge_asof(daily, money.sort_values("observation_date"), on="observation_date", direction="backward", suffixes=("", "_monthly"))
        for col in ["Aggregate Balance", "HIBOR O/N", "HKMA Base Rate", "Strong-side CU", "Weak-side CU", "Linked Rate"]:
            money[col] = money[col].combine_first(money.get(f"{col}_monthly"))
    return money[empty_cols].sort_values("observation_date").drop_duplicates("observation_date")

def build_fig5(date_range):
    data = filter_range(get_hk_liquidity(), date_range)
    fig = go.Figure()
    for col, name, width, dash in [("M2 YoY", "M2 YoY", 3.0, None), ("M3 YoY", "M3 YoY", 3.0, "dash"), ("HIBOR O/N", "O/N HIBOR", 1.8, "dot"), ("HIBOR 1M", "1M HIBOR", 1.8, "dashdot"), ("HIBOR 3M", "3M HIBOR", 1.8, "longdash"), ("HKMA Base Rate", "HKMA Base Rate", 2.2, "solid")]:
        add_line(fig, data, col, name, width, dash)
    add_line(fig, data, "Aggregate Balance", "Aggregate Balance", 2.8, "solid", "y2", unit=" HK$ bn")
    add_line(fig, data, "USD/HKD", "USD/HKD", 2.0, "solid", "y3")
    add_line(fig, data, "Strong-side CU", "Strong-side CU 7.75", 1.2, "dot", "y3")
    add_line(fig, data, "Linked Rate", "Linked Rate 7.80", 1.2, "dash", "y3")
    add_line(fig, data, "Weak-side CU", "Weak-side CU 7.85", 1.2, "dot", "y3")
    fig.update_layout(yaxis=dict(title="M2/M3 YoY & Interest Rate (%)", fixedrange=True), yaxis2=dict(title="Aggregate Balance (HK$ bn)", overlaying="y", side="right", anchor="free", position=1.0, showgrid=False, zeroline=False, fixedrange=True, automargin=True, tickfont=dict(size=9)), yaxis3=dict(title="USD/HKD", overlaying="y", side="right", anchor="free", position=0.94, showgrid=False, zeroline=False, fixedrange=True, automargin=True, tickfont=dict(size=9)), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0))
    return apply_chart_style(fig, chart_height(430, 650), date_range)

'''
text = text[:start] + new_block + text[end:]
text = text.replace('Aggregate Balance / Overnight HIBOR / 1M HIBOR', 'HK M2/M3 / Aggregate Balance / HIBOR / HKMA Base Rate / USD-HKD', 1)
text = text.replace('Aggregate Balance、隔夜 HIBOR 与 1M HIBOR', 'HK M2/M3、银行体系流动性、HIBOR、HKMA Base Rate 与 USD/HKD', 1)
old_desc = 'M2/M3 观察货币供应增长；Aggregate Balance 观察银行体系结算流动性；O/N、1M、3M HIBOR 与 HKMA Base Rate 观察港元资金价格；USD/HKD 同时标出 7.75 强方兑换保证、7.80 联系汇率与 7.85 弱方兑换保证。'
new_desc = '''1. M2 YoY：香港港元 M2 同比增速，观察银行体系广义货币供应扩张或收缩速度。\n2. M3 YoY：香港港元 M3 同比增速，口径较 M2 更广，用于观察整体货币与准货币扩张。\n3. Aggregate Balance：银行体系在 HKMA 的结算余额，反映银行体系即时结算流动性；下降通常意味着流动性收紧。\n4. O/N HIBOR：港元隔夜银行间拆借利率，反映最短期限的港元资金成本，对短期流动性变化最敏感。\n5. 1M HIBOR：港元 1 个月银行间拆借利率，观察短中期资金成本及市场对流动性状况的判断。\n6. 3M HIBOR：港元 3 个月银行间拆借利率，较 O/N 更能反映一段时期内的资金成本与利率预期。\n7. HKMA Base Rate：香港金管局 Base Rate，为贴现窗机制的重要政策利率参考，影响港元利率环境。\n8. USD/HKD：美元兑港元汇率；数值上升代表港元相对美元走弱，接近 7.85 时表示接近弱方兑换保证。\n9. Strong-side CU：强方兑换保证 7.75；当 USD/HKD 接近 7.75，通常对应港元偏强及资金流入压力。\n10. Linked Rate：联系汇率中点 7.80，用于作为 USD/HKD 观察的中轴参考。\n11. Weak-side CU：弱方兑换保证 7.85；当 USD/HKD 接近 7.85，通常对应港元偏弱及资金流出压力。\n12. 综合判断：M2/M3↑、Aggregate Balance↑、HIBOR↓ 通常对应流动性偏宽松；Aggregate Balance↓、HIBOR↑ 则通常对应港元短期流动性收紧。'''
text = text.replace(old_desc, new_desc, 1)
APP.write_text(text, encoding='utf-8')
print('updated HK liquidity chart 5')
