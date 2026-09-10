from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"
HK = ROOT / "macro_platform" / "hk_liquidity.py"


def replace_required(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise RuntimeError(f"{label}: expected source block not found")
    return text.replace(old, new, 1)


def patch_app() -> None:
    text = APP.read_text(encoding="utf-8")

    css_replacements = [
        (".block-container { padding-top: 0.85rem; padding-bottom: 3rem; max-width: 1760px; }",
         ".block-container { padding-top: 0.70rem; padding-bottom: 2rem; max-width: 1760px; }"),
        (".section-title { font-size: 1.35rem; font-weight: 650; letter-spacing: -0.01em; margin-top: 0.7rem; margin-bottom: 0.15rem; min-height: 32px; display: flex; align-items: center; }",
         ".section-title { font-size: 1.30rem; font-weight: 650; letter-spacing: -0.01em; margin-top: 0.45rem; margin-bottom: 0.08rem; min-height: 28px; display: flex; align-items: center; }"),
        (".section-description { color: #6b7280; font-size: 0.86rem; margin-bottom: 0.35rem; min-height: 22px; display: flex; align-items: center; }",
         ".section-description { color: #6b7280; font-size: 0.84rem; margin-bottom: 0.18rem; min-height: 18px; display: flex; align-items: center; }"),
        (".mini-description { color: #6b7280; font-size: 0.76rem; line-height: 1.5; margin: 2px 0 8px; }",
         ".mini-description { color: #6b7280; font-size: 0.74rem; line-height: 1.42; margin: 1px 0 5px; }"),
        (".source-text { color: #6b7280; font-size: 0.74rem; margin: 3px 0 10px; line-height: 1.45; }",
         ".source-text { color: #6b7280; font-size: 0.72rem; margin: 2px 0 6px; line-height: 1.35; }"),
        (".chart-divider { margin: 0.30rem 0 0.55rem; border-top: 1px solid #e5e7eb; }",
         ".chart-divider { margin: 0.18rem 0 0.38rem; border-top: 1px solid #e5e7eb; }"),
        (".dashboard-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; padding: 4px 0 14px; margin-bottom: 14px; border-bottom: 1px solid #e5e7eb; }",
         ".dashboard-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; padding: 3px 0 10px; margin-bottom: 10px; border-bottom: 1px solid #e5e7eb; }"),
    ]
    for idx, (old, new) in enumerate(css_replacements, start=1):
        text = replace_required(text, old, new, f"app css {idx}")

    health_css_anchor = '.source-text a:hover { color: #374151; text-decoration: underline !important; }\n'
    health_css = health_css_anchor + '.data-health-warning { color:#991b1b; background:rgba(254,242,242,.94); border:1px solid #fecaca; border-radius:6px; padding:3px 6px; font-size:.68rem; line-height:1.25; }\n'
    text = replace_required(text, health_css_anchor, health_css, "data health css")

    old_add_line = '''def add_line(fig, data, column, name, width=2.5, dash=None, yaxis=None, unit="%"):\n    if column not in data.columns or data[column].notna().sum() == 0: return\n    line = {"width": width}\n    if dash: line["dash"] = dash\n    trace = go.Scatter(x=data["observation_date"], y=data[column], name=name, mode="lines", line=line, hovertemplate=f"{name}: %{{y:.3f}}{unit}<extra></extra>")\n    if yaxis: trace.update(yaxis=yaxis)\n    fig.add_trace(trace)\n'''
    new_add_line = '''def _mark_missing_series(fig, name):\n    meta = fig.layout.meta if isinstance(fig.layout.meta, dict) else {}\n    meta = dict(meta or {})\n    missing = list(meta.get("missing_series") or [])\n    if name not in missing:\n        missing.append(name)\n    meta["missing_series"] = missing\n    fig.update_layout(meta=meta)\n\n\ndef add_line(fig, data, column, name, width=2.5, dash=None, yaxis=None, unit="%"):\n    if column not in data.columns or data[column].notna().sum() == 0:\n        _mark_missing_series(fig, name)\n        return\n    line = {"width": width}\n    if dash: line["dash"] = dash\n    trace = go.Scatter(x=data["observation_date"], y=data[column], name=name, mode="lines", line=line, hovertemplate=f"{name}: %{{y:.3f}}{unit}<extra></extra>")\n    if yaxis: trace.update(yaxis=yaxis)\n    fig.add_trace(trace)\n'''
    text = replace_required(text, old_add_line, new_add_line, "missing series tracker")

    text = replace_required(
        text,
        'base_top = 128 if compact_mode else 124\n    base_bottom = 40',
        'base_top = 88 if compact_mode else 92\n    base_bottom = 34',
        "US chart margins",
    )
    text = replace_required(
        text,
        'orientation="h", yanchor="bottom", y=1.17, xanchor="left", x=0,',
        'orientation="h", yanchor="bottom", y=1.105, xanchor="left", x=0,',
        "US legend position",
    )

    old_style_return = '''    # Shared adaptive lower axis + centered upper year axis for charts 1-4.\n    return apply_time_axis(fig, date_range)\n'''
    new_style_return = '''    # Shared adaptive lower axis + centered upper year axis. Missing traces are\n    # surfaced inside the plot instead of disappearing silently.\n    fig = apply_time_axis(fig, date_range)\n    meta = fig.layout.meta if isinstance(fig.layout.meta, dict) else {}\n    missing = list((meta or {}).get("missing_series") or [])\n    if missing:\n        fig.add_annotation(\n            text="⚠ 数据缺失：" + " · ".join(missing),\n            x=0.006, y=0.988, xref="paper", yref="paper",\n            xanchor="left", yanchor="top", showarrow=False,\n            font=dict(size=10, color="#991b1b"),\n            bgcolor="rgba(254,242,242,0.94)", bordercolor="#fecaca", borderwidth=1, borderpad=3,\n        )\n    return fig\n'''
    text = replace_required(text, old_style_return, new_style_return, "chart health annotation")

    old_fig2 = '''def build_fig2(date_range):\n    data = get_dgs10().merge(get_dfii10(), on="observation_date", how="outer").merge(get_fred_series("T10YIE"), on="observation_date", how="outer").sort_values("observation_date"); data = filter_range(data, date_range); fig = go.Figure()\n    for column, name, width, dash, yaxis in [("DGS10", "10Y Nominal", 2.8, None, None), ("DFII10", "10Y Real (R)", 2.6, None, "y2"), ("T10YIE", "10Y Breakeven (R)", 2.5, "dot", "y2")]: add_line(fig, data, column, name, width, dash, yaxis)\n    fig.update_layout(yaxis_title="Nominal Yield (%)", yaxis2=dict(title="Real / Breakeven (%)", overlaying="y", side="right", anchor="free", position=1.0, showgrid=False, zeroline=False, fixedrange=True, automargin=True, tickfont=dict(size=9))); return apply_chart_style(fig, chart_height(340, 500), date_range)\n'''
    new_fig2 = '''def build_fig2(date_range):\n    data = get_dgs10().merge(get_dfii10(), on="observation_date", how="outer").merge(get_fred_series("T10YIE"), on="observation_date", how="outer").sort_values("observation_date")\n    for column in ("DGS10", "DFII10", "T10YIE"):\n        data[column] = pd.to_numeric(data.get(column), errors="coerce")\n    # Treasury identity: Nominal ≈ Real + Breakeven. Preserve observed values\n    # first and synthesize only a missing leg when the other two are present.\n    data["DGS10"] = data["DGS10"].combine_first(data["DFII10"] + data["T10YIE"])\n    data["DFII10"] = data["DFII10"].combine_first(data["DGS10"] - data["T10YIE"])\n    data["T10YIE"] = data["T10YIE"].combine_first(data["DGS10"] - data["DFII10"])\n    data = filter_range(data, date_range); fig = go.Figure()\n    for column, name, width, dash, yaxis in [("DGS10", "10Y Nominal", 2.8, None, None), ("DFII10", "10Y Real (R)", 2.6, None, "y2"), ("T10YIE", "10Y Breakeven (R)", 2.5, "dot", "y2")]: add_line(fig, data, column, name, width, dash, yaxis)\n    fig.update_layout(yaxis_title="Nominal Yield (%)", yaxis2=dict(title="Real / Breakeven (%)", overlaying="y", side="right", anchor="free", position=1.0, showgrid=False, zeroline=False, fixedrange=True, automargin=True, tickfont=dict(size=9))); return apply_chart_style(fig, chart_height(310, 420), date_range)\n'''
    text = replace_required(text, old_fig2, new_fig2, "Chart 2 triangular backfill")

    old_fig3 = '''def build_fig3(date_range):\n    data = get_dgs3mo().merge(get_dgs2(), on="observation_date", how="outer").merge(get_dgs10(), on="observation_date", how="outer").merge(get_fred_series("T10Y2Y"), on="observation_date", how="outer").merge(get_fred_series("T10Y3M"), on="observation_date", how="outer").sort_values("observation_date"); data = filter_range(data, date_range); fig = go.Figure()\n    for column, name, width in [("DGS3MO", "3M", 2.2), ("DGS2", "2Y", 2.4), ("DGS10", "10Y", 2.8)]: add_line(fig, data, column, name, width)\n    add_line(fig, data, "T10Y2Y", "10Y−2Y (R)", 2.2, "dot", "y2", "%"); add_line(fig, data, "T10Y3M", "10Y−3M (R)", 2.2, "dash", "y2", "%")\n    fig.update_traces(selector=dict(name="10Y−2Y (R)"), hovertemplate="10Y−2Y (R): %{y:.3f}%<extra></extra>"); fig.update_traces(selector=dict(name="10Y−3M (R)"), hovertemplate="10Y−3M (R): %{y:.3f}%<extra></extra>")\n    fig.update_layout(yaxis=dict(title="Yield (%)", fixedrange=True), yaxis2=dict(title="Spread (%)", overlaying="y", side="right", anchor="free", position=1.0, showgrid=False, zeroline=True, zerolinecolor="#9ca3af", fixedrange=True, automargin=True, tickfont=dict(size=9))); return apply_chart_style(fig, chart_height(340, 500), date_range)\n'''
    new_fig3 = '''def build_fig3(date_range):\n    data = get_dgs3mo().merge(get_dgs2(), on="observation_date", how="outer").merge(get_dgs10(), on="observation_date", how="outer").sort_values("observation_date")\n    for column in ("DGS3MO", "DGS2", "DGS10"):\n        data[column] = pd.to_numeric(data.get(column), errors="coerce")\n    # Derive curve spreads locally from the displayed yields. This removes two\n    # redundant FRED requests and guarantees spread/yield internal consistency.\n    data["T10Y2Y"] = data["DGS10"] - data["DGS2"]\n    data["T10Y3M"] = data["DGS10"] - data["DGS3MO"]\n    data = filter_range(data, date_range); fig = go.Figure()\n    for column, name, width in [("DGS3MO", "3M", 2.2), ("DGS2", "2Y", 2.4), ("DGS10", "10Y", 2.8)]: add_line(fig, data, column, name, width)\n    add_line(fig, data, "T10Y2Y", "10Y−2Y (R)", 2.2, "dot", "y2", "%"); add_line(fig, data, "T10Y3M", "10Y−3M (R)", 2.2, "dash", "y2", "%")\n    fig.update_traces(selector=dict(name="10Y−2Y (R)"), hovertemplate="10Y−2Y (R): %{y:.3f}%<extra></extra>"); fig.update_traces(selector=dict(name="10Y−3M (R)"), hovertemplate="10Y−3M (R): %{y:.3f}%<extra></extra>")\n    fig.update_layout(yaxis=dict(title="Yield (%)", fixedrange=True), yaxis2=dict(title="Spread (%)", overlaying="y", side="right", anchor="free", position=1.0, showgrid=False, zeroline=True, zerolinecolor="#9ca3af", fixedrange=True, automargin=True, tickfont=dict(size=9))); return apply_chart_style(fig, chart_height(310, 420), date_range)\n'''
    text = replace_required(text, old_fig3, new_fig3, "Chart 3 local spreads")

    # Compress the remaining US panels consistently.
    text = text.replace('chart_height(340, 500)', 'chart_height(310, 420)')
    text = text.replace('chart_height(360, 520)', 'chart_height(320, 440)')
    text = text.replace('margin=dict(l=62, r=144, t=72, b=44, pad=2)', 'margin=dict(l=62, r=144, t=68, b=36, pad=2)')

    old_empty_fig4 = '''    if not raw_series:\n        return apply_chart_style(go.Figure(), chart_height(310, 420), date_range)\n'''
    new_empty_fig4 = '''    if not raw_series:\n        fig = go.Figure()\n        for name in ("Net Liquidity Proxy", "Reserve Balances · Weekly", "TGA", "ON RRP · Daily"):\n            _mark_missing_series(fig, name)\n        return apply_chart_style(fig, chart_height(310, 420), date_range)\n'''
    text = replace_required(text, old_empty_fig4, new_empty_fig4, "Chart 4 empty health")

    old_partial_fig4 = '''        frame = raw_series.get(column)\n        if frame is None:\n            continue\n        add_line(fig, filter_range(frame, date_range), column, observed_names[column], width_map[column], dash_map[column], unit=" T")\n'''
    new_partial_fig4 = '''        frame = raw_series.get(column)\n        if frame is None:\n            _mark_missing_series(fig, observed_names[column])\n            continue\n        add_line(fig, filter_range(frame, date_range), column, observed_names[column], width_map[column], dash_map[column], unit=" T")\n'''
    text = replace_required(text, old_partial_fig4, new_partial_fig4, "Chart 4 partial health")

    old_empty_fig9 = '''    if not frames:\n        return apply_chart_style(go.Figure(), chart_height(310, 420), date_range)\n'''
    new_empty_fig9 = '''    if not frames:\n        fig = go.Figure()\n        for name in ("VIX", "VIXEQ", "S&P 500 (R1)", "VIX3M−VIX (R2)"):\n            _mark_missing_series(fig, name)\n        return apply_chart_style(fig, chart_height(320, 440), date_range)\n'''
    text = replace_required(text, old_empty_fig9, new_empty_fig9, "Chart 9 empty health")

    APP.write_text(text, encoding="utf-8")


def patch_hk() -> None:
    text = HK.read_text(encoding="utf-8")

    old_meta = '''def snapshot_metadata() -> dict[str, Any]:\n    _, meta = _read_snapshot()\n    data = load_hk_liquidity()\n    if not data.empty:\n        meta["latest_observation"] = data["observation_date"].max().strftime("%Y-%m")\n    return meta\n'''
    new_meta = '''def snapshot_metadata() -> dict[str, Any]:\n    _, meta = _read_snapshot()\n    data = load_hk_liquidity()\n    if not data.empty:\n        meta["latest_observation"] = data["observation_date"].max().strftime("%Y-%m")\n        money_cols = [c for c in ("M2 YoY", "M3 YoY") if c in data.columns]\n        if money_cols:\n            money_rows = data.loc[data[money_cols].notna().any(axis=1), "observation_date"].dropna()\n            if not money_rows.empty:\n                meta["latest_money_observation"] = money_rows.max().strftime("%Y-%m")\n    return meta\n'''
    text = replace_required(text, old_meta, new_meta, "HKMA money freshness metadata")

    old_market_sort = '''    if not market_data.empty:\n        market_data = market_data.sort_values("observation_date")\n    raw_market = str(market_mode).strip().lower() == "raw"\n'''
    new_market_sort = '''    if not market_data.empty:\n        market_data = market_data.sort_values("observation_date")\n        # Cross-market comparisons must share the same last completed\n        # observation. Never compare a same-day partial HSI/HKEX print against\n        # a prior-day HSTECH close at the right edge of the chart.\n        market_ends = [\n            pd.to_datetime(frame["observation_date"], errors="coerce").max()\n            for frame in (tencent_price, hkex_price, hstech_index, hsi_index)\n            if frame is not None and not frame.empty and "observation_date" in frame.columns\n        ]\n        market_ends = [value for value in market_ends if pd.notna(value)]\n        if market_ends:\n            common_market_end = min(market_ends)\n            market_data = market_data.loc[market_data["observation_date"] <= common_market_end].copy()\n    raw_market = str(market_mode).strip().lower() == "raw"\n'''
    text = replace_required(text, old_market_sort, new_market_sort, "HK market common as-of date")

    text = replace_required(
        text,
        'def style(fig: go.Figure, title: str, height: int = 430, right_axis: bool = False) -> go.Figure:',
        'def style(fig: go.Figure, title: str, height: int = 380, right_axis: bool = False) -> go.Figure:',
        "HK default chart height",
    )
    text = replace_required(
        text,
        'margin=dict(l=62, r=82 if right_axis else 28, t=124, b=54, pad=2),',
        'margin=dict(l=62, r=82 if right_axis else 28, t=96, b=40, pad=2),',
        "HK chart margins",
    )
    text = replace_required(
        text,
        'orientation="h", yanchor="bottom", y=1.17, xanchor="left", x=0,',
        'orientation="h", yanchor="bottom", y=1.105, xanchor="left", x=0,',
        "HK legend position",
    )
    text = text.replace('margin=dict(l=62, r=142, t=124, b=54, pad=2)', 'margin=dict(l=62, r=142, t=96, b=40, pad=2)')
    text = text.replace('margin=dict(l=62, r=94, t=124, b=54, pad=2)', 'margin=dict(l=62, r=94, t=96, b=40, pad=2)')
    text = text.replace('height=450, right_axis=True', 'height=400, right_axis=True')
    text = text.replace('height=470, right_axis=True', 'height=410, right_axis=True')

    old_balance_style = '''    banking_frequency_label = "Daily" if banking_is_daily else ("Monthly" if date_range == "5Y" else "Monthly fallback")\n    style(balance, f"6. Banking-system Liquidity · {banking_frequency_label}", height=400, right_axis=True)\n'''
    new_balance_style = '''    banking_frequency_label = "Daily" if banking_is_daily else ("Monthly" if date_range == "5Y" else "Monthly fallback")\n    style(balance, f"6. Banking-system Liquidity · {banking_frequency_label}", height=400, right_axis=True)\n    if date_range != "5Y" and not banking_is_daily:\n        balance.add_annotation(\n            text="⚠ HKMA 日频流动性快照不可用 · 当前使用月频回退",\n            x=0.006, y=0.988, xref="paper", yref="paper", xanchor="left", yanchor="top",\n            showarrow=False, font=dict(size=10, color="#991b1b"),\n            bgcolor="rgba(254,242,242,0.94)", bordercolor="#fecaca", borderwidth=1, borderpad=3,\n        )\n'''
    text = replace_required(text, old_balance_style, new_balance_style, "HK banking fallback warning")

    old_funding_style = '''    funding_frequency_label = "Daily" if funding_is_daily else ("Monthly" if date_range == "5Y" else "Monthly fallback")\n    style(funding, f"7. HKD Funding · {funding_frequency_label}", right_axis=True)\n'''
    new_funding_style = '''    funding_frequency_label = "Daily" if funding_is_daily else ("Monthly" if date_range == "5Y" else "Monthly fallback")\n    style(funding, f"7. HKD Funding · {funding_frequency_label}", right_axis=True)\n    if date_range != "5Y" and not funding_is_daily:\n        funding.add_annotation(\n            text="⚠ HKMA 日频 HIBOR 快照不可用 · 当前使用月频回退",\n            x=0.006, y=0.988, xref="paper", yref="paper", xanchor="left", yanchor="top",\n            showarrow=False, font=dict(size=10, color="#991b1b"),\n            bgcolor="rgba(254,242,242,0.94)", bordercolor="#fecaca", borderwidth=1, borderpad=3,\n        )\n'''
    text = replace_required(text, old_funding_style, new_funding_style, "HK funding fallback warning")

    old_status = '''    latest = meta.get("latest_observation", "--")\n\n    m2 = _latest_value(data, "M2 MoM")'''
    new_status = '''    latest = meta.get("latest_observation", "--")\n    latest_money = meta.get("latest_money_observation", latest)\n\n    m2 = _latest_value(data, "M2 MoM")'''
    text = replace_required(text, old_status, new_status, "HK status money freshness variable")
    text = replace_required(
        text,
        '<div><span>HKMA monthly through</span><strong>{latest}</strong></div>',
        '<div><span>M2/M3 through</span><strong>{latest_money}</strong></div>',
        "HK status money freshness label",
    )

    HK.write_text(text, encoding="utf-8")


def validate() -> None:
    app = APP.read_text(encoding="utf-8")
    hk = HK.read_text(encoding="utf-8")
    checks = {
        "triangular Treasury backfill": 'data["DFII10"] = data["DFII10"].combine_first' in app,
        "local 10Y-2Y spread": 'data["T10Y2Y"] = data["DGS10"] - data["DGS2"]' in app,
        "missing-series health": '⚠ 数据缺失：' in app,
        "compressed US chart": 'chart_height(310, 420)' in app,
        "HK common as-of": 'common_market_end = min(market_ends)' in hk,
        "HK daily fallback warning": 'HKMA 日频流动性快照不可用' in hk,
        "compressed HK chart": 'height: int = 380' in hk,
        "money freshness": 'latest_money_observation' in hk,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise RuntimeError("validation failed: " + ", ".join(failed))


if __name__ == "__main__":
    patch_app()
    patch_hk()
    validate()
    print("Applied data-health hardening, cross-source alignment, and compact chart layout.")
