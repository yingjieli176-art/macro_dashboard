from pathlib import Path

APP = Path("app.py")
text = APP.read_text(encoding="utf-8")
original = text

# Add subplot support once.
needle = "import plotly.graph_objects as go\n"
replacement = "import plotly.graph_objects as go\nfrom plotly.subplots import make_subplots\n"
if replacement not in text:
    if needle not in text:
        raise RuntimeError("plotly import target not found")
    text = text.replace(needle, replacement, 1)

# Replace the HKMA pagination helper with a retrying implementation.
helper_start = text.index("@st.cache_data(ttl=3600, show_spinner=False)\ndef _hkma_get_all")
helper_end = text.index("\n@st.cache_data(ttl=3600, show_spinner=False)\ndef get_hk_liquidity", helper_start)
new_helper = '''@st.cache_data(ttl=3600, show_spinner=False)
def _hkma_get_all(url, params=None, page_size=250, max_pages=8):
    rows = []
    base_params = dict(params or {})
    for page in range(max_pages):
        batch = []
        query = {**base_params, "offset": page * page_size, "pagesize": page_size}
        for attempt in range(3):
            try:
                response = requests.get(url, params=query, timeout=(4, 20))
                response.raise_for_status()
                payload = response.json() or {}
                header = payload.get("header") or {}
                if header and header.get("success") is False:
                    raise RuntimeError(header.get("err_msg") or "HKMA API returned an error")
                result = payload.get("result") or {}
                batch = result.get("records") or result.get("data") or result.get("datas") or []
                if isinstance(batch, dict):
                    batch = batch.get("records") or batch.get("data") or batch.get("datas") or []
                break
            except Exception:
                if attempt == 2:
                    batch = []
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < page_size:
            break
    return rows
'''
text = text[:helper_start] + new_helper + text[helper_end:]

# Replace Chart 5 data collection. The chart now relies on the stable monthly monetary-statistics
# endpoint for the primary panel so a slow daily endpoint can no longer blank the entire chart.
data_start = text.index("@st.cache_data(ttl=3600, show_spinner=False)\ndef get_hk_liquidity")
data_end = text.index("\ndef build_fig5", data_start)
new_data = '''@st.cache_data(ttl=3600, show_spinner=False)
def get_hk_liquidity():
    columns = [
        "observation_date",
        "M2 YoY",
        "M3 YoY",
        "Monetary Base YoY",
        "Aggregate Balance",
        "HIBOR O/N",
        "HIBOR 3M",
        "HKMA Base Rate",
        "USD/HKD",
        "Strong-side CU",
        "Weak-side CU",
    ]
    url = "https://api.hkma.gov.hk/public/market-data-and-statistics/monthly-statistical-bulletin/financial/monetary-statistics"
    end_month = pd.Timestamp.today().strftime("%Y-%m")
    rows = _hkma_get_all(
        url,
        params={
            "choose": "end_of_month",
            "from": "2018-01",
            "to": end_month,
            "sortby": "end_of_month",
            "sortorder": "asc",
        },
        page_size=250,
        max_pages=2,
    )
    # Fallback for transient filter/query failures: the endpoint defaults to newest-first.
    if not rows:
        rows = _hkma_get_all(
            url,
            params={"sortby": "end_of_month", "sortorder": "desc"},
            page_size=250,
            max_pages=2,
        )
    frame = pd.DataFrame(rows)
    if frame.empty or "end_of_month" not in frame.columns:
        return pd.DataFrame(columns=columns)

    raw_period = frame["end_of_month"].astype(str)
    frame = frame[raw_period.str.match(r"^\\d{4}-(0[1-9]|1[0-2])$")].copy()
    frame["observation_date"] = pd.to_datetime(frame["end_of_month"], format="%Y-%m", errors="coerce")
    frame = frame.dropna(subset=["observation_date"]).sort_values("observation_date").drop_duplicates("observation_date")

    for col in [
        "m2_hkd", "m3_hkd", "monetary_base_total", "aggr_balance",
        "hibor_fixing_overnight", "hibor_fixing_3m",
        "discount_window_base_rate", "exrate_hkd_usd",
    ]:
        frame[col] = pd.to_numeric(frame.get(col), errors="coerce")

    frame["M2 YoY"] = frame["m2_hkd"].pct_change(12, fill_method=None) * 100.0
    frame["M3 YoY"] = frame["m3_hkd"].pct_change(12, fill_method=None) * 100.0
    frame["Monetary Base YoY"] = frame["monetary_base_total"].pct_change(12, fill_method=None) * 100.0
    frame["Aggregate Balance"] = frame["aggr_balance"] / 1000.0
    frame["HIBOR O/N"] = frame["hibor_fixing_overnight"]
    frame["HIBOR 3M"] = frame["hibor_fixing_3m"]
    frame["HKMA Base Rate"] = frame["discount_window_base_rate"]
    frame["USD/HKD"] = frame["exrate_hkd_usd"]
    frame["Strong-side CU"] = 7.75
    frame["Weak-side CU"] = 7.85
    return frame[columns]
'''
text = text[:data_start] + new_data + text[data_end:]

# Replace Chart 5 with four readable liquidity panels instead of one overloaded multi-axis chart.
fig_start = text.index("def build_fig5")
fig_end = text.index("\ndef build_fig1", fig_start)
new_fig = '''def build_fig5(date_range):
    data = filter_range(get_hk_liquidity(), date_range).copy()
    fig = make_subplots(
        rows=4,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.055,
        row_heights=[0.28, 0.18, 0.28, 0.26],
        subplot_titles=(
            "Money supply growth",
            "Banking-system aggregate balance",
            "HKD funding rates",
            "USD/HKD and Convertibility Undertakings",
        ),
    )

    def add_trace(row, column, name, width=2.3, dash=None, unit="%"):
        if column not in data.columns or data[column].notna().sum() == 0:
            return
        line = {"width": width}
        if dash:
            line["dash"] = dash
        fig.add_trace(
            go.Scatter(
                x=data["observation_date"],
                y=data[column],
                name=name,
                mode="lines",
                line=line,
                hovertemplate=f"{name}: %{{y:.3f}}{unit}<extra></extra>",
            ),
            row=row,
            col=1,
        )

    add_trace(1, "M2 YoY", "HKD M2 YoY", 2.8)
    add_trace(1, "M3 YoY", "HKD M3 YoY", 2.3, "dash")
    add_trace(1, "Monetary Base YoY", "Monetary Base YoY", 1.8, "dot")

    add_trace(2, "Aggregate Balance", "Aggregate Balance", 2.8, unit=" HK$ bn")

    add_trace(3, "HIBOR O/N", "O/N HIBOR", 2.0)
    add_trace(3, "HIBOR 3M", "3M HIBOR", 2.3, "dash")
    add_trace(3, "HKMA Base Rate", "HKMA Base Rate", 2.0, "dot")

    add_trace(4, "USD/HKD", "USD/HKD", 2.6, unit="")
    add_trace(4, "Strong-side CU", "Strong-side CU 7.75", 1.4, "dot", unit="")
    add_trace(4, "Weak-side CU", "Weak-side CU 7.85", 1.4, "dot", unit="")

    height = chart_height(720, 900)
    fig.update_layout(
        height=height,
        template="plotly_white",
        hovermode="x unified",
        dragmode=False,
        margin=dict(l=60, r=25, t=72, b=42, pad=2),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.04,
            xanchor="left",
            x=0,
            font=dict(size=9 if compact_mode else 10),
            bgcolor="rgba(255,255,255,0)",
        ),
        hoverlabel=dict(bgcolor="white", font_size=11, bordercolor="#e5e7eb"),
        font=dict(size=10 if compact_mode else 11),
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
    )
    fig.update_yaxes(title_text="YoY (%)", row=1, col=1, showgrid=True, gridcolor="#e5e7eb", griddash="dot", zeroline=True, zerolinecolor="#cbd5e1", fixedrange=True)
    fig.update_yaxes(title_text="HK$ bn", row=2, col=1, showgrid=True, gridcolor="#e5e7eb", griddash="dot", zeroline=False, fixedrange=True)
    fig.update_yaxes(title_text="Rate (%)", row=3, col=1, showgrid=True, gridcolor="#e5e7eb", griddash="dot", zeroline=True, zerolinecolor="#cbd5e1", fixedrange=True)
    fig.update_yaxes(title_text="USD/HKD", row=4, col=1, range=[7.73, 7.87], showgrid=True, gridcolor="#e5e7eb", griddash="dot", zeroline=False, fixedrange=True)
    fig.update_xaxes(showgrid=True, gridcolor="#eef2f7", griddash="dot", fixedrange=True, tickformat="%Y-%m", row=4, col=1)
    return fig
'''
text = text[:fig_start] + new_fig + text[fig_end:]

# Update section descriptions/sources so the UI reflects the repaired data model.
text = text.replace(
    "HK M2/M3 / Aggregate Balance / HIBOR / HKMA Rate Corridor / USD-HKD",
    "HKD M2/M3 / Monetary Base / Aggregate Balance / HIBOR / HKMA Base Rate / USD-HKD / 7.75-7.85 CU",
)
text = text.replace(
    "HK M2/M3、银行体系流动性、HIBOR、HKMA 利率走廊与 USD/HKD",
    "HKD M2/M3、货币基础、银行体系总结余、HIBOR、HKMA Base Rate 与 USD/HKD 强弱方兑换保证",
)
text = text.replace(
    '("HKMA Daily Figures of Interbank Liquidity", "https://www.hkma.gov.hk/eng/statistics/monetary-statistics/monetary-base/"), ("HKMA Open API", "https://apidocs.hkma.gov.hk/")',
    '("HKMA Monetary Statistics", "https://apidocs.hkma.gov.hk/documentation/market-data-and-statistics/monthly-statistical-bulletin/financial/monetary-statistics/"), ("HKMA Open API", "https://apidocs.hkma.gov.hk/")',
)
text = text.replace(
    '[("HKMA Daily Figures of Interbank Liquidity", "https://apidocs.hkma.gov.hk/documentation/market-data-and-statistics/daily-monetary-statistics/daily-figures-interbank-liquidity/")]',
    '[("HKMA Monetary Statistics", "https://apidocs.hkma.gov.hk/documentation/market-data-and-statistics/monthly-statistical-bulletin/financial/monetary-statistics/")]',
)

if text != original:
    APP.write_text(text, encoding="utf-8")
    print("fixed HK liquidity chart 5 v2")
else:
    print("HK liquidity chart 5 v2 already applied")
