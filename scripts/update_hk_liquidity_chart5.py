from pathlib import Path

APP = Path('app.py')
text = APP.read_text(encoding='utf-8')
start = text.index('# === HK LIQUIDITY CHART 5 ===')
end = text.index('def build_fig1(date_range):', start)
new_block = '''# === HK LIQUIDITY CHART 5 ===
@st.cache_data(ttl=3600, show_spinner=False)
def _hkma_get_all(url, page_size=100, max_pages=60):
    rows = []
    for page in range(max_pages):
        try:
            response = requests.get(url, params={"offset": page * page_size}, timeout=8)
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
    interbank_url = "https://api.hkma.gov.hk/public/market-data-and-statistics/daily-monetary-statistics/daily-figures-interbank-liquidity"
    rows = _hkma_get_all(interbank_url)
    if not rows:
        return pd.DataFrame(columns=["observation_date", "Aggregate Balance", "HIBOR O/N", "HIBOR 1M", "HIBOR 3M", "HKMA Base Rate", "M2 YoY", "M3 YoY", "USD/HKD", "Strong-side CU", "Linked Rate", "Weak-side CU"])
    frame = pd.DataFrame(rows)
    frame["observation_date"] = pd.to_datetime(frame.get("end_of_date"), errors="coerce")
    frame["Aggregate Balance"] = pd.to_numeric(frame.get("closing_balance"), errors="coerce") / 1000.0
    frame["HIBOR O/N"] = pd.to_numeric(frame.get("hibor_overnight"), errors="coerce")
    frame["HIBOR 1M"] = pd.to_numeric(frame.get("hibor_fixing_1m"), errors="coerce")
    frame["HKMA Base Rate"] = pd.to_numeric(frame.get("disc_win_base_rate"), errors="coerce")
    frame["Strong-side CU"] = pd.to_numeric(frame.get("cu_strongside"), errors="coerce")
    frame["Weak-side CU"] = pd.to_numeric(frame.get("cu_weakside"), errors="coerce")
    frame["Linked Rate"] = 7.80

    money_url = "https://api.hkma.gov.hk/public/market-data-and-statistics/monthly-statistical-bulletin/financial/monetary-statistics"
    money_rows = _hkma_get_all(money_url)
    money = pd.DataFrame(money_rows)
    if not money.empty:
        money["observation_date"] = pd.to_datetime(money.get("end_of_month"), errors="coerce")
        money["HIBOR 3M"] = pd.to_numeric(money.get("hibor_fixing_3m"), errors="coerce")
        money["M2"] = pd.to_numeric(money.get("m2_hkd"), errors="coerce")
        money["M3"] = pd.to_numeric(money.get("m3_hkd"), errors="coerce")
        money["USD/HKD"] = pd.to_numeric(money.get("exrate_hkd_usd"), errors="coerce")
        money = money[["observation_date", "HIBOR 3M", "M2", "M3", "USD/HKD"]].dropna(subset=["observation_date"]).sort_values("observation_date")
        money["M2 YoY"] = money["M2"].pct_change(12) * 100.0
        money["M3 YoY"] = money["M3"].pct_change(12) * 100.0
        frame = pd.merge_asof(frame.sort_values("observation_date"), money[["observation_date", "HIBOR 3M", "M2 YoY", "M3 YoY", "USD/HKD"]], on="observation_date", direction="backward")
    else:
        frame["HIBOR 3M"] = pd.NA; frame["M2 YoY"] = pd.NA; frame["M3 YoY"] = pd.NA; frame["USD/HKD"] = pd.NA
    cols = ["observation_date", "Aggregate Balance", "HIBOR O/N", "HIBOR 1M", "HIBOR 3M", "HKMA Base Rate", "M2 YoY", "M3 YoY", "USD/HKD", "Strong-side CU", "Linked Rate", "Weak-side CU"]
    return frame[cols].dropna(subset=["observation_date"]).sort_values("observation_date").drop_duplicates("observation_date")

def build_fig5(date_range):
    data = filter_range(get_hk_liquidity(), date_range)
    fig = go.Figure()
    add_line(fig, data, "M2 YoY", "M2 YoY", 3.0)
    add_line(fig, data, "M3 YoY", "M3 YoY", 3.0, "dash")
    add_line(fig, data, "HIBOR O/N", "O/N HIBOR", 1.8, "dot")
    add_line(fig, data, "HIBOR 1M", "1M HIBOR", 1.8, "dashdot")
    add_line(fig, data, "HIBOR 3M", "3M HIBOR", 1.8, "longdash")
    add_line(fig, data, "HKMA Base Rate", "HKMA Base Rate", 2.2, "solid")
    add_line(fig, data, "Aggregate Balance", "Aggregate Balance", 2.8, "solid", "y2", unit=" HK$ bn")
    add_line(fig, data, "USD/HKD", "USD/HKD (monthly)", 2.0, "solid", "y3")
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
text = text.replace('Aggregate Balance / Overnight HIBOR / 1M HIBOR', 'HK M2/M3 / Aggregate Balance / HIBOR / HKMA Base Rate / USD-HKD', 1)
text = text.replace('Aggregate Balance、隔夜 HIBOR 与 1M HIBOR', 'HK M2/M3、银行体系流动性、HIBOR、HKMA Base Rate 与 USD/HKD', 1)
text = text.replace('Aggregate Balance 是香港银行在金管局结算账户的总余额，用于观察香港银行体系流动性；HIBOR 用于观察港元银行间资金价格。', 'M2/M3 观察货币供应增长；Aggregate Balance 观察银行体系结算流动性；O/N、1M、3M HIBOR 与 HKMA Base Rate 观察港元资金价格；USD/HKD 同时标出 7.75 强方兑换保证、7.80 联系汇率与 7.85 弱方兑换保证。', 1)
APP.write_text(text, encoding='utf-8')
print('updated HK liquidity chart 5')
