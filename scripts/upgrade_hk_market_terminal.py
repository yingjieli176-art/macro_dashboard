from __future__ import annotations

from pathlib import Path

HK = Path("macro_platform/hk_liquidity.py")
APP = Path("app.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"missing patch anchor: {label}")
    return text.replace(old, new, 1)


def main() -> None:
    hk = HK.read_text(encoding="utf-8")

    hk = replace_once(
        hk,
        'HSTECH_SNAPSHOT_PATH = ROOT / "data_snapshots" / "hstech_monthly.json"\n',
        'HSTECH_SNAPSHOT_PATH = ROOT / "data_snapshots" / "hstech_monthly.json"\n'
        'HK_MARKET_DAILY_SNAPSHOT_PATH = ROOT / "data_snapshots" / "hk_market_daily.json"\n',
        "market snapshot constant",
    )

    market_helpers = '''\n\ndef _market_snapshot_history(symbol: str, label: str, date_range: str) -> pd.DataFrame:\n    """Load persisted daily Hong Kong market history and adapt density by window.\n\n    1M/3M/6M/1Y retain trading-day observations. 5Y is reduced to weekly\n    closes to keep Plotly responsive without destroying the shape of the cycle.\n    """\n    try:\n        payload = json.loads(HK_MARKET_DAILY_SNAPSHOT_PATH.read_text(encoding="utf-8"))\n        node = ((payload.get("series") or {}).get(symbol) or {})\n        frame = pd.DataFrame(node.get("records") or [])\n    except Exception:\n        return pd.DataFrame(columns=["observation_date", label])\n    if frame.empty or "observation_date" not in frame.columns or "close" not in frame.columns:\n        return pd.DataFrame(columns=["observation_date", label])\n    frame["observation_date"] = pd.to_datetime(frame["observation_date"], errors="coerce")\n    frame[label] = pd.to_numeric(frame["close"], errors="coerce")\n    frame = (\n        frame.dropna(subset=["observation_date", label])\n        .sort_values("observation_date")\n        .drop_duplicates("observation_date", keep="last")\n    )\n    if frame.empty:\n        return pd.DataFrame(columns=["observation_date", label])\n    start = frame["observation_date"].max() - RANGE_OFFSETS.get(date_range, RANGE_OFFSETS["1Y"])\n    frame = frame.loc[frame["observation_date"] >= start, ["observation_date", label]].copy()\n    if date_range == "5Y" and not frame.empty:\n        frame = (\n            frame.set_index("observation_date")[label]\n            .resample("W-FRI")\n            .last()\n            .dropna()\n            .rename(label)\n            .reset_index()\n        )\n    return frame\n\n\ndef _market_history(symbol: str, label: str, date_range: str) -> pd.DataFrame:\n    snapshot_symbol = "HSTECH" if str(symbol).upper() in {"HSTECH", "HSTECH.HK", "^HSTECH"} else symbol\n    snapshot = _market_snapshot_history(snapshot_symbol, label, date_range)\n    minimum = 200 if date_range == "5Y" else 10\n    if len(snapshot) >= minimum:\n        return snapshot\n    # Emergency fallback only. Normal dashboard renders should never need live\n    # history because GitHub Actions maintains the last-known-good snapshot.\n    monthly = _market_monthly_close(symbol, label)\n    if monthly.empty:\n        return monthly\n    return _slice_range(monthly, date_range)\n\n\ndef _rebase_market_data(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:\n    rebased = frame.copy()\n    for column in columns:\n        if column not in rebased.columns:\n            continue\n        valid = pd.to_numeric(rebased[column], errors="coerce").dropna()\n        if valid.empty or float(valid.iloc[0]) == 0:\n            continue\n        rebased[column] = pd.to_numeric(rebased[column], errors="coerce") / float(valid.iloc[0]) * 100.0\n    return rebased\n'''
    hk = replace_once(
        hk,
        '\n\ndef _market_monthly_close(symbol: str, label: str) -> pd.DataFrame:\n',
        market_helpers + '\n\ndef _market_monthly_close(symbol: str, label: str) -> pd.DataFrame:\n',
        "market helper insertion",
    )

    hk = replace_once(
        hk,
        'def build_hk_liquidity_figures(date_range: str, compact_mode: bool = False) -> list[go.Figure]:\n    """Build four independent Hong Kong liquidity charts for the dashboard."""',
        'def build_hk_liquidity_figures(\n    date_range: str, compact_mode: bool = False, market_mode: str = "Raw"\n) -> list[go.Figure]:\n    """Build four independent Hong Kong liquidity charts for the dashboard."""',
        "builder signature",
    )

    old_market = '''    # Market overlays use month-end price/index levels. No percentage transformation is applied.\n    hkex_price = _market_monthly_close("0388.HK", "HKEX Price")\n    hstech_index = _market_monthly_close("HSTECH.HK", "HSTECH Index")\n    hsi_index = _market_monthly_close("^HSI", "HSI Index")\n    market_data = pd.DataFrame(columns=["observation_date"])\n    for frame in (hkex_price, hstech_index, hsi_index):\n        if frame.empty:\n            continue\n        if market_data.empty:\n            market_data = frame.copy()\n        else:\n            market_data = market_data.merge(frame, on="observation_date", how="outer")\n    if not market_data.empty:\n        market_data = market_data.sort_values("observation_date")\n'''
    new_market = '''    # Market overlays are persisted as daily last-known-good history. Short\n    # windows retain daily detail; the 5Y view is sampled to weekly closes.\n    tencent_price = _market_history("0700.HK", "Tencent Price", date_range)\n    hkex_price = _market_history("0388.HK", "HKEX Price", date_range)\n    hstech_index = _market_history("HSTECH", "HSTECH Index", date_range)\n    hsi_index = _market_history("^HSI", "HSI Index", date_range)\n    market_columns = ["Tencent Price", "HKEX Price", "HSTECH Index", "HSI Index"]\n    market_data = pd.DataFrame(columns=["observation_date"])\n    for frame in (tencent_price, hkex_price, hstech_index, hsi_index):\n        if frame.empty:\n            continue\n        if market_data.empty:\n            market_data = frame.copy()\n        else:\n            market_data = market_data.merge(frame, on="observation_date", how="outer")\n    if not market_data.empty:\n        market_data = market_data.sort_values("observation_date")\n    raw_market = str(market_mode).strip().lower() == "raw"\n    if not raw_market and not market_data.empty:\n        market_data = _rebase_market_data(market_data, market_columns)\n'''
    hk = replace_once(hk, old_market, new_market, "market source block")

    hk = replace_once(
        hk,
        '        secondary_y: bool | None = None,\n    ) -> None:\n',
        '        secondary_y: bool | None = None,\n        axis: str | None = None,\n    ) -> None:\n',
        "add_line axis signature",
    )
    hk = replace_once(
        hk,
        '        if secondary_y is None:\n            fig.add_trace(trace)\n        else:\n            fig.add_trace(trace, secondary_y=secondary_y)\n',
        '        if axis is not None:\n            trace.update(yaxis=axis)\n            fig.add_trace(trace)\n        elif secondary_y is None:\n            fig.add_trace(trace)\n        else:\n            fig.add_trace(trace, secondary_y=secondary_y)\n',
        "add_line axis routing",
    )

    old_money_start = hk.index('    # 5-1 · Money supply + Hong Kong equity market monthly changes.\n')
    old_money_end = hk.index('    # 5-2 · Daily banking-system liquidity and monetary-base structure.\n')
    new_money = '''    # 5 · Money supply + Hong Kong equity market. Raw mode separates stock\n    # prices (R1) from index levels (R2); Rebased 100 puts all market assets\n    # onto one comparable relative-performance axis.\n    money = make_subplots(specs=[[{"secondary_y": True}]])\n    add_line(money, data, "M2 MoM", "M2 MoM", COLORS["m2"], 2.8, secondary_y=False)\n    add_line(money, data, "M3 MoM", "M3 MoM", COLORS["m3"], 2.3, "dash", secondary_y=False)\n    add_line(money, data, "Monetary Base MoM", "Monetary Base MoM", COLORS["base"], 1.8, "dot", secondary_y=False)\n    if raw_market:\n        add_line(money, market_data, "Tencent Price", "Tencent Price (R1)", "#111827", 2.3, unit=" HKD", secondary_y=True)\n        add_line(money, market_data, "HKEX Price", "HKEX Price (R1)", "#0891b2", 2.0, "dash", unit=" HKD", secondary_y=True)\n        add_line(money, market_data, "HSTECH Index", "HSTECH Index (R2)", "#db2777", 2.1, "dash", unit=" pts", axis="y3")\n        add_line(money, market_data, "HSI Index", "HSI Index (R2)", "#d97706", 2.0, "dot", unit=" pts", axis="y3")\n    else:\n        add_line(money, market_data, "Tencent Price", "Tencent (R)", "#111827", 2.3, unit="", secondary_y=True)\n        add_line(money, market_data, "HKEX Price", "HKEX (R)", "#0891b2", 2.0, "dash", unit="", secondary_y=True)\n        add_line(money, market_data, "HSTECH Index", "HSTECH (R)", "#db2777", 2.1, "dash", unit="", secondary_y=True)\n        add_line(money, market_data, "HSI Index", "HSI (R)", "#d97706", 2.0, "dot", unit="", secondary_y=True)\n    money.update_yaxes(\n        title_text="Money MoM (%)", secondary_y=False,\n        showgrid=True, gridcolor="#e5e7eb", griddash="dot",\n        zeroline=True, zerolinecolor="#cbd5e1", fixedrange=True,\n    )\n    money.update_yaxes(\n        title_text="R1 · HKD Price" if raw_market else "Market · Rebased 100", secondary_y=True,\n        showgrid=False, zeroline=False, fixedrange=True,\n    )\n    style(money, "5. HK Money Supply & Market Pulse", right_axis=True)\n    if raw_market:\n        money.update_layout(\n            margin=dict(l=62, r=142, t=124, b=54, pad=2),\n            xaxis=dict(domain=[0.0, 0.84]),\n            yaxis2=dict(overlaying="y", side="right", anchor="free", position=0.86, title="R1 · HKD Price", showgrid=False, fixedrange=True, tickfont=dict(size=10)),\n            yaxis3=dict(overlaying="y", side="right", anchor="free", position=0.97, title="R2 · Index Level", showgrid=False, fixedrange=True, tickfont=dict(size=10)),\n        )\n    else:\n        money.update_layout(\n            margin=dict(l=62, r=94, t=124, b=54, pad=2),\n            xaxis=dict(domain=[0.0, 0.91]),\n            yaxis2=dict(title="Market · Rebased 100", showgrid=False, fixedrange=True),\n        )\n    if not market_data.empty:\n        market_latest = market_data["observation_date"].max().strftime("%Y-%m-%d")\n\n'''
    hk = hk[:old_money_start] + new_money + hk[old_money_end:]

    old_fx_start = hk.index('    # 5-4 · Convertibility band + market reaction.\n')
    old_fx_end = hk.index('    return [money, balance, funding, fx]\n')
    new_fx = '''    # 8 · Convertibility band + market reaction.\n    fx = make_subplots(specs=[[{"secondary_y": True}]])\n    fx_source = fx_daily if not fx_daily.empty else data[["observation_date", "USD/HKD"]].dropna().copy()\n    add_line(fx, fx_source, "USD/HKD", "USD/HKD", COLORS["fx"], 2.6, unit="", secondary_y=False)\n    add_constant(fx, 7.75, "Strong-side CU 7.75", COLORS["strong"], "dot", 1.4, secondary_y=False, x_frame=fx_source)\n    add_constant(fx, 7.80, "Linked Rate Center 7.80", "#64748b", "dash", 1.5, secondary_y=False, x_frame=fx_source)\n    add_constant(fx, 7.85, "Weak-side CU 7.85", COLORS["weak"], "dot", 1.4, secondary_y=False, x_frame=fx_source)\n    if raw_market:\n        add_line(fx, market_data, "Tencent Price", "Tencent Price (R1)", "#111827", 2.3, unit=" HKD", secondary_y=True)\n        add_line(fx, market_data, "HKEX Price", "HKEX Price (R1)", "#0891b2", 2.0, "dash", unit=" HKD", secondary_y=True)\n        add_line(fx, market_data, "HSTECH Index", "HSTECH Index (R2)", "#db2777", 2.1, "dash", unit=" pts", axis="y3")\n        add_line(fx, market_data, "HSI Index", "HSI Index (R2)", "#d97706", 2.0, "dot", unit=" pts", axis="y3")\n    else:\n        add_line(fx, market_data, "Tencent Price", "Tencent (R)", "#111827", 2.3, unit="", secondary_y=True)\n        add_line(fx, market_data, "HKEX Price", "HKEX (R)", "#0891b2", 2.0, "dash", unit="", secondary_y=True)\n        add_line(fx, market_data, "HSTECH Index", "HSTECH (R)", "#db2777", 2.1, "dash", unit="", secondary_y=True)\n        add_line(fx, market_data, "HSI Index", "HSI (R)", "#d97706", 2.0, "dot", unit="", secondary_y=True)\n    fx.add_hrect(\n        y0=7.75, y1=7.85,\n        fillcolor="rgba(148,163,184,0.08)",\n        line_width=0, layer="below",\n        annotation_text="7.75–7.85 LERS band",\n        annotation_position="top left",\n    )\n    fx.add_hrect(\n        y0=7.84, y1=7.85,\n        fillcolor="rgba(220,38,38,0.09)",\n        line_width=0, layer="below",\n        annotation_text="Weak-side Pressure 7.84–7.85",\n        annotation_position="bottom left",\n    )\n    fx.update_yaxes(\n        title_text="USD/HKD · Strong ↑ / Weak ↓", secondary_y=False, range=[7.87, 7.73],\n        showgrid=True, gridcolor="#e5e7eb", griddash="dot",\n        zeroline=False, fixedrange=True,\n    )\n    fx.update_yaxes(\n        title_text="R1 · HKD Price" if raw_market else "Market · Rebased 100", secondary_y=True,\n        showgrid=False, zeroline=False, fixedrange=True,\n    )\n    style(fx, "8. USD/HKD Convertibility Band & Market", height=470, right_axis=True)\n    if raw_market:\n        fx.update_layout(\n            margin=dict(l=62, r=142, t=124, b=54, pad=2),\n            xaxis=dict(domain=[0.0, 0.84]),\n            yaxis2=dict(overlaying="y", side="right", anchor="free", position=0.86, title="R1 · HKD Price", showgrid=False, fixedrange=True, tickfont=dict(size=10)),\n            yaxis3=dict(overlaying="y", side="right", anchor="free", position=0.97, title="R2 · Index Level", showgrid=False, fixedrange=True, tickfont=dict(size=10)),\n        )\n    else:\n        fx.update_layout(\n            margin=dict(l=62, r=94, t=124, b=54, pad=2),\n            xaxis=dict(domain=[0.0, 0.91]),\n            yaxis2=dict(title="Market · Rebased 100", showgrid=False, fixedrange=True),\n        )\n    if not fx_source.empty:\n        fx_latest = fx_source["observation_date"].max().strftime("%Y-%m-%d")\n\n'''
    hk = hk[:old_fx_start] + new_fx + hk[old_fx_end:]

    HK.write_text(hk, encoding="utf-8")

    app = APP.read_text(encoding="utf-8")
    app = replace_once(
        app,
        'def build_fig5(date_range):\n    return build_hk_liquidity_figures(date_range, compact_mode=False)\n',
        'def build_fig5(date_range, market_mode="Raw"):\n    return build_hk_liquidity_figures(date_range, compact_mode=False, market_mode=market_mode)\n',
        "app builder signature",
    )
    app = app.replace('    hk_figures = build_fig5("5Y")\n', '', 1)
    app = app.replace(
        'HKD M2 / M3 / Monetary Base MoM · HKEX Price (R) · HSTECH Index (R) · HSI Index (R)',
        'HKD M2 / M3 / Monetary Base MoM · Tencent / HKEX (R1) · HSTECH / HSI (R2)',
        1,
    )
    app = app.replace(
        'USD/HKD · Strong-side 7.75 · Center 7.80 · Weak-side 7.85 · HKEX / HSTECH / HSI (R)',
        'USD/HKD · Weak-side pressure 7.84–7.85 · Tencent / HKEX (R1) · HSTECH / HSI (R2)',
        1,
    )

    app = app.replace('HKEX Price（R）', 'HKEX Price（R1）')
    app = app.replace('HSTECH Index（R）', 'HSTECH Index（R2）')
    app = app.replace('HSI Index（R）', 'HSI Index（R2）')
    app = app.replace(
        '用于对照香港大盘与流动性变化。',
        '用于对照香港大盘与流动性变化。<br>7. Tencent Price（R1）：腾讯控股 0700.HK 股价，Raw 模式与港交所共用 R1 港元价格轴；Rebased 100 模式把可视区间首个有效值归一到 100，便于比较相对弹性。<br><br><b>市场显示：</b>Raw 模式把股票价格放在 R1、指数点位放在 R2；Rebased 100 模式把 Tencent / HKEX / HSTECH / HSI 统一归一化，用于比较涨跌幅而不是绝对点位。',
        1,
    )
    app = app.replace(
        '7. HSI Index（R2）：恒生指数月末指数点位，右轴单位 points。',
        '7. HSI Index（R2）：恒生指数点位，Raw 模式对应 R2。<br>8. Tencent Price（R1）：腾讯控股 0700.HK 股价，Raw 模式对应 R1 港元价格轴。<br><br><b>市场显示：</b>Raw 模式保留真实价格/点位；Rebased 100 模式把四条市场资产在可视区间首个有效值归一到 100，用来比较谁更强、谁更弱。',
        1,
    )
    app = app.replace(
        '灰色区域仍表示 7.75–7.85 联系汇率区间；',
        '灰色区域表示 7.75–7.85 联系汇率区间；其中 7.84–7.85 的淡红区域为 Weak-side Pressure Zone，用于提示接近弱方兑换保证的压力阶段；',
        1,
    )

    old_plot = '''        st.plotly_chart(\n            apply_hk_chart_range(hk_figures[hk_index], hk_range),\n            use_container_width=True,\n            config=PLOTLY_CONFIG,\n        )\n'''
    new_plot = '''        hk_market_mode = "Raw"\n        if hk_index in (0, 3):\n            hk_market_mode = st.radio(\n                "市场显示",\n                ["Raw", "Rebased 100"],\n                horizontal=True,\n                index=0,\n                key=f"{key}_market_mode",\n                label_visibility="collapsed",\n            )\n        hk_figure = build_fig5(hk_range, market_mode=hk_market_mode)[hk_index]\n        st.plotly_chart(\n            hk_figure,\n            use_container_width=True,\n            config=PLOTLY_CONFIG,\n        )\n'''
    app = replace_once(app, old_plot, new_plot, "HK chart render")
    APP.write_text(app, encoding="utf-8")
    print("upgraded HK market terminal: durable daily history, adaptive sampling, R1/R2, rebased mode, weak-side zone")


if __name__ == "__main__":
    main()
