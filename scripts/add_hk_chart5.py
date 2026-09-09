from pathlib import Path

APP = Path("app.py")
text = APP.read_text(encoding="utf-8")

if "# === HK LIQUIDITY CHART 5 ===" in text:
    raise SystemExit("HK chart 5 already installed")

marker = "# === HK LIQUIDITY CHART 5 ==="

insert_before_fig1 = '''\n\n# === HK LIQUIDITY CHART 5 ===\n@st.cache_data(ttl=3600, show_spinner=False)\ndef get_hk_liquidity():\n    url = "https://api.hkma.gov.hk/public/market-data-and-statistics/daily-monetary-statistics/daily-figures-interbank-liquidity"\n    rows = []\n    for offset in range(0, 5000, 100):\n        try:\n            response = requests.get(url, params={"offset": offset}, timeout=8)\n            response.raise_for_status()\n            payload = response.json()\n            result = payload.get("result") or {}\n            batch = result.get("records") or result.get("data") or result.get("datas") or []\n            if isinstance(batch, dict):\n                batch = batch.get("records") or batch.get("data") or batch.get("datas") or []\n            if not batch:\n                break\n            rows.extend(batch)\n            if len(batch) < 100:\n                break\n        except Exception:\n            break\n    if not rows:\n        return pd.DataFrame(columns=["observation_date", "Aggregate Balance", "HIBOR O/N", "HIBOR 1M"])\n    frame = pd.DataFrame(rows)\n    date_col = next((c for c in ["end_of_date", "end_of_day", "date"] if c in frame.columns), None)\n    if date_col is None:\n        return pd.DataFrame(columns=["observation_date", "Aggregate Balance", "HIBOR O/N", "HIBOR 1M"])\n    frame["observation_date"] = pd.to_datetime(frame[date_col], errors="coerce")\n    frame["Aggregate Balance"] = pd.to_numeric(frame.get("closing_balance"), errors="coerce") / 1000.0\n    frame["HIBOR O/N"] = pd.to_numeric(frame.get("hibor_overnight"), errors="coerce")\n    frame["HIBOR 1M"] = pd.to_numeric(frame.get("hibor_fixing_1m"), errors="coerce")\n    return frame.dropna(subset=["observation_date"]).sort_values("observation_date").drop_duplicates("observation_date")[["observation_date", "Aggregate Balance", "HIBOR O/N", "HIBOR 1M"]]\n\ndef build_fig5(date_range):\n    data = filter_range(get_hk_liquidity(), date_range)\n    fig = go.Figure()\n    add_line(fig, data, "Aggregate Balance", "Aggregate Balance", 2.8, unit=" HK$ bn")\n    add_line(fig, data, "HIBOR O/N", "HIBOR O/N (R)", 2.2, "dot", "y2")\n    add_line(fig, data, "HIBOR 1M", "HIBOR 1M (R)", 2.2, "dash", "y2")\n    fig.update_layout(\n        yaxis=dict(title="Aggregate Balance (HK$ bn)", fixedrange=True),\n        yaxis2=dict(title="HIBOR (%)", overlaying="y", side="right", anchor="free", position=1.0, showgrid=False, zeroline=False, fixedrange=True, automargin=True, tickfont=dict(size=9)),\n    )\n    return apply_chart_style(fig, chart_height(340, 500), date_range)\n\n'''

needle = "def build_fig1(date_range):"
if needle not in text:
    raise SystemExit("build_fig1 marker not found")
text = text.replace(needle, insert_before_fig1 + needle, 1)

needle2 = '        configs = [(cols[0], \'<div class="compact-title">🏦 1. Fed Policy Rate</div>\''
# Insert compact chart 5 after chart 4 in the compact configs list by appending a separate render block.
compact_anchor = '                st.markdown(title, unsafe_allow_html=True); st.markdown(description, unsafe_allow_html=True); date_range = st.radio("时间范围", RANGES, horizontal=True, index=1, key=key, label_visibility="collapsed"); st.markdown(\'<div style="height:6px"></div>\', unsafe_allow_html=True); st.plotly_chart(builder(date_range), use_container_width=True, config=PLOTLY_CONFIG); show_parameter_description(desc_index); add_sources(sources)\n'
if compact_anchor not in text:
    raise SystemExit("compact render anchor not found")
text = text.replace(compact_anchor, compact_anchor + '        st.markdown(\'<div class="compact-title">5. Hong Kong Liquidity</div>\', unsafe_allow_html=True); st.markdown(\'<div class="compact-description">Aggregate Balance / Overnight HIBOR / 1M HIBOR</div>\', unsafe_allow_html=True); hk_range = st.radio("时间范围", RANGES, horizontal=True, index=1, key="compact_hk_liquidity_range", label_visibility="collapsed"); st.plotly_chart(build_fig5(hk_range), use_container_width=True, config=PLOTLY_CONFIG); add_sources([("HKMA Daily Figures of Interbank Liquidity", "https://www.hkma.gov.hk/eng/statistics/monetary-statistics/monetary-base/"), ("HKMA Open API", "https://apidocs.hkma.gov.hk/")])\n', 1)

normal_anchor = '            if divider: st.markdown(\'<div class="chart-divider"></div>\', unsafe_allow_html=True)\n\nrender_core_charts()'
if normal_anchor not in text:
    raise SystemExit("normal render anchor not found")
text = text.replace(normal_anchor, '            if divider: st.markdown(\'<div class="chart-divider"></div>\', unsafe_allow_html=True)\n        st.markdown(\'<div class="section-title">5. Hong Kong Liquidity</div>\', unsafe_allow_html=True); st.markdown(\'<div class="section-description">Aggregate Balance、隔夜 HIBOR 与 1M HIBOR</div>\', unsafe_allow_html=True); hk_range = st.radio("时间范围", RANGES, horizontal=True, index=1, key="normal_hk_liquidity_range", label_visibility="collapsed"); st.plotly_chart(build_fig5(hk_range), use_container_width=True, config=PLOTLY_CONFIG); st.markdown(\'<div class="mini-description">Aggregate Balance 是香港银行在金管局结算账户的总余额，用于观察香港银行体系流动性；HIBOR 用于观察港元银行间资金价格。</div>\', unsafe_allow_html=True); add_sources([("HKMA Daily Figures of Interbank Liquidity", "https://apidocs.hkma.gov.hk/documentation/market-data-and-statistics/daily-monetary-statistics/daily-figures-interbank-liquidity/")])\n\nrender_core_charts()', 1)

APP.write_text(text, encoding="utf-8")
print("patched app.py")
