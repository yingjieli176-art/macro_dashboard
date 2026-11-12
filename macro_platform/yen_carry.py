"""Observed carry incentives and FX pressure; no inferred positioning or P&L."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from macro_platform.chart_axes import RANGE_OFFSETS, apply_time_axis
from macro_platform.boj_policy import BOJ_POLICY_NAME, RATE_COLUMN
from macro_platform.fred_observations import TIC_JAPAN_SERIES

SPREAD_NAME = "US 10Y - Japan 10Y"
FX_NAME = "USD/JPY (R1)"
PRESSURE_NAME = "JPY 20-session appreciation (R2)"
POSITION_NAME = "CFTC JPY speculative net (R3)"
TOPIX_NAME = "TOPIX（东证指数） (R4)"
DXY_NAME = "美元指数 DXY (R5)"
JPY_3M_NAME = "JPY 3M"
JPY_10Y_NAME = "JPY 10Y"
JPY_CURVE_NAME = "JPY 10Y - JPY 3M"
DXY_SYMBOL = "DX-Y.NYB"
DXY_SNAPSHOT = Path(__file__).resolve().parents[1] / "data_snapshots/dxy_daily.json"
INSTITUTIONS_SNAPSHOT = DXY_SNAPSHOT.with_name("japan_institutions.json")


def _observations(frame, column):
    if frame is None or not {"observation_date", column}.issubset(frame.columns):
        return pd.DataFrame(columns=["observation_date", column])
    out = frame[["observation_date", column]].copy()
    out["observation_date"] = pd.to_datetime(out.observation_date, errors="coerce", utc=True).dt.tz_localize(None).dt.normalize()
    out[column] = pd.to_numeric(out[column], errors="coerce").replace([np.inf, -np.inf], np.nan)
    return out.dropna(subset=["observation_date"]).sort_values("observation_date", kind="stable").drop_duplicates("observation_date", keep="last").reset_index(drop=True)


def load_dxy_snapshot(path=DXY_SNAPSHOT):
    """Keep verified DXY closes available during a Yahoo outage."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload["symbol"] == DXY_SYMBOL:
            return _observations(pd.DataFrame(payload["records"]), "close")
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return _observations(None, "close")


def carry_observations(us, japan, fx):
    """Match yields by date only; calculate FX returns before viewport slicing.

    Twenty sessions means twenty intervals between valid observed FX closes.
    Null current quotes remain null. No forward fill across holiday calendars.
    """
    rates = _observations(us, "DGS10").merge(
        _observations(japan, "japan_10y"), on="observation_date", how="outer").sort_values("observation_date")
    rates["spread_pp"] = rates.DGS10 - rates.japan_10y
    exchange = _fx_observations(fx)
    valid = exchange.usd_jpy_close.dropna()
    exchange["yen_appreciation_pct"] = (valid.shift(20) / valid - 1) * 100
    return rates, exchange


def _fx_observations(fx):
    exchange = _observations(fx, "usd_jpy_close")
    exchange.loc[exchange.usd_jpy_close.le(0), "usd_jpy_close"] = np.nan
    return exchange


def build_yen_volatility_figure(date_range, *, fx, policy=None):
    """Use completed FX closes and full rolling windows before viewport slicing."""
    exchange = _fx_observations(fx)
    returns = np.log(exchange.usd_jpy_close.dropna().astype(float)).diff()
    fig = go.Figure()
    missing = []
    for sessions, color in ((20, "#a61e63"), (60, "#4e6cf5")):
        name = f"USD/JPY {sessions}日实际波动率"
        vol = returns.rolling(sessions).std() * np.sqrt(252) * 100
        if not vol.notna().any():
            missing.append(name)
            continue
        fig.add_scatter(x=exchange.observation_date, y=vol.reindex(exchange.index),
                        name=name, mode="lines", connectgaps=False,
                        line=dict(color=color, width=2.3),
                        hovertemplate="%{y:.2f}%<extra></extra>")
    fig.update_layout(template="plotly_white", hovermode="x unified",
                      yaxis=dict(title="年化波动率 · %", fixedrange=True),
                      meta={"missing_series": missing})
    if policy is not None:
        policy = _observations(policy, RATE_COLUMN).dropna(subset=[RATE_COLUMN])
        if policy.empty:
            fig.layout.meta["missing_series"].append(BOJ_POLICY_NAME)
        else:
            fig.add_scatter(x=policy.observation_date, y=policy[RATE_COLUMN],
                            name=BOJ_POLICY_NAME, yaxis="y2", mode="lines",
                            line=dict(color="#087c5a", width=2.5, shape="hv"),
                            hovertemplate="%{y:.2f}%<extra></extra>")
            fig.update_layout(yaxis2=dict(title="BOJ 政策利率 · %", overlaying="y",
                                          side="right", showgrid=False, fixedrange=True),
                              meta={"preserve_axis_titles": ["y", "y2"]})
    return apply_time_axis(fig, date_range)


def build_japan_institution_figure(date_range, *, metric, path=INSTITUTIONS_SNAPSHOT):
    """Compare only published disclosure dates and preserve each scope."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    life = pd.DataFrame(payload["boj_life_insurers"]["records"])
    if metric == "holdings":
        gpif = pd.DataFrame(payload["gpif"]["records"])
        gpif["market_value_jpy_trillion"] = gpif.market_value_jpy / 1e12
        lines = (
            (gpif, "market_value_jpy_trillion", "GPIF 美债票据与长期债券", "#4e6cf5"),
            (life, "foreign_bonds_jpy_trillion", "九家主要寿险 · 外债（多币种）", "#a61e63"),
        )
        title, fmt, unit = "持仓 · 万亿日元", ",.2f", " 万亿日元"
    else:
        postal = pd.DataFrame(payload["japan_post_insurance"]["records"])
        postal["hedge_pct"] = postal.hedged_jpy_trillion / postal.foreign_currency_bonds_jpy_trillion * 100
        lines = (
            (life, "hedge_pct", "九家主要寿险 · 外债对冲率", "#a61e63"),
            (postal, "hedge_pct", "日本邮政保险 · 单列外币债券对冲率", "#087c5a"),
        )
        title, fmt, unit = "汇率对冲率 · %", ".0f", "%"
    fig = go.Figure()
    for frame, column, name, color in lines:
        rows = _observations(frame, column)
        fig.add_scatter(x=rows.observation_date, y=rows[column], name=name,
                        mode="lines+markers", marker_size=6, connectgaps=False,
                        line=dict(color=color, width=2.3),
                        hovertemplate=f"%{{y:{fmt}}}{unit}<extra></extra>")
    fig.update_layout(template="plotly_white", hovermode="closest",
                      yaxis=dict(title=title, fixedrange=True),
                      meta={"preserve_axis_titles": ["y"]})
    return apply_time_axis(fig, date_range)


def build_japan_tic_figure(date_range, *, series):
    """Keep stocks and signed monthly changes on independent axes."""
    total, long, net, valuation = TIC_JAPAN_SERIES
    frames = {key: _observations(series.get(key), key) for key in TIC_JAPAN_SERIES}
    holdings = frames[total].merge(frames[long], on="observation_date", how="outer")
    holdings["short"] = (holdings[total] - holdings[long]).where(holdings[total].ge(holdings[long]))
    traces = (
        (holdings, total, "日本美债总持仓", "y", "#4e6cf5"),
        (holdings, long, "长期美债持仓", "y", "#087c5a"),
        (holdings, "short", "短期美债持仓（总额减长期）", "y", "#64748b"),
        (frames[net], net, "长期美债净买入（右轴）", "y2", "#a61e63"),
        (frames[valuation], valuation, "长期美债估值变动（右轴）", "y2", "#e88939"),
    )
    fig = go.Figure()
    missing = []
    for frame, column, name, axis, color in traces:
        rows = frame.dropna(subset=[column]).sort_values("observation_date")
        if rows.empty:
            missing.append(name)
            continue
        # FRED labels monthly records with the first day. TIC measures
        # positions at month end and transactions over that same month.
        common = dict(x=rows.observation_date + pd.offsets.MonthEnd(0),
                      y=rows[column] / 1000, name=name, yaxis=axis,
                      meta={"observation_cadence": "monthly"},
                      hovertemplate="%{y:,.2f} 十亿美元<extra></extra>")
        if axis == "y2":
            fig.add_bar(**common, marker_color=color, opacity=0.72)
        else:
            fig.add_scatter(**common, mode="lines+markers", connectgaps=False,
                            line=dict(color=color, width=2.2), marker_size=4)
    fig.update_layout(template="plotly_white", hovermode="x unified", barmode="group",
                      yaxis=dict(title="月末持仓 · 十亿美元", fixedrange=True),
                      yaxis2=dict(title="当月变动 · 十亿美元", overlaying="y", side="right",
                                  showgrid=False, zeroline=True, fixedrange=True),
                      meta={"missing_series": missing, "preserve_axis_titles": ["y", "y2"]})
    return apply_time_axis(fig, date_range)


def build_yen_carry_figure(date_range, *, us, japan, fx, positions=None, topix=None, dxy=None,
                           japan_short=None):
    rates, exchange = carry_observations(us, japan, fx)
    positioning = _observations(positions, "net_contracts")
    positioning["net_10k_contracts"] = positioning.net_contracts / 10000
    sources = ((rates, "spread_pp", SPREAD_NAME, "y", "#536178", "solid", " pp"),
               (exchange, "usd_jpy_close", FX_NAME, "y2", "#4e6cf5", "solid", " JPY/USD"),
               (exchange, "yen_appreciation_pct", PRESSURE_NAME, "y3", "#e88939", "dash", "%"),
               (positioning, "net_10k_contracts", POSITION_NAME, "y4", "#8a61c4", "dot", " 万张"))
    if topix is not None:
        index = _observations(topix, "topix_close")
        index.loc[index.topix_close.le(0), "topix_close"] = np.nan
        sources += ((index, "topix_close", TOPIX_NAME, "y5", "#087c5a", "solid", " pts"),)
    if dxy is not None:
        dollar = _observations(dxy, "close")
        dollar.loc[dollar.close.le(0), "close"] = np.nan
        sources += ((dollar, "close", DXY_NAME, "y6", "#a61e63", "solid", " pts"),)
    if japan_short is not None:
        long = _observations(japan, "japan_10y")
        short = _observations(japan_short, "japan_3m")
        curve = short.merge(long, on="observation_date", how="left")
        curve["japan_curve_pp"] = curve.japan_10y - curve.japan_3m
        sources += (
            (short, "japan_3m", JPY_3M_NAME, "y", "#009e73", "dot", "%"),
            (long, "japan_10y", JPY_10Y_NAME, "y", "#0072b2", "solid", "%"),
            (curve, "japan_curve_pp", JPY_CURVE_NAME, "y", "#d55e00", "dash", " pp"),
        )
    latest_dates = [frame.loc[frame[column].notna(), "observation_date"].max()
                    for frame, column, *_ in sources if frame[column].notna().any()]
    latest = max(latest_dates) if latest_dates else None
    start = latest - RANGE_OFFSETS.get(date_range, RANGE_OFFSETS["1Y"]) if latest is not None else None
    fig = go.Figure()
    missing = []
    for frame, column, name, axis, color, dash, suffix in sources:
        view = frame.loc[frame.observation_date.ge(start)] if start is not None else frame
        if not view[column].notna().any():
            missing.append(name)
            continue
        common = dict(x=view.observation_date, y=view[column], name=name, yaxis=axis,
                      hovertemplate=f"{name}: %{{y:.2f}}{suffix}<extra></extra>")
        if name == POSITION_NAME:
            fig.add_trace(go.Bar(**common, marker=dict(color=color, opacity=0.6), width=4*86400000))
        else:
            fig.add_trace(go.Scatter(**common, mode="lines", connectgaps=False,
                                     line=dict(color=color, width=2.3, dash=dash)))
    fig.update_layout(
        template="plotly_white", height=470, hovermode="x unified", dragmode=False,
        margin=dict(l=64, r=160, t=74, b=36),
        legend=dict(orientation="h", yanchor="bottom", y=1.09, font=dict(size=10)),
        xaxis=dict(domain=[0, 0.81]),
        yaxis=dict(title=f"{SPREAD_NAME} · pp", fixedrange=True, tickformat=".2f", zeroline=True),
        yaxis2=dict(title="R1 · USD/JPY · 阳轴", overlaying="y", side="right", anchor="free",
                    position=0.83, showgrid=False, fixedrange=True, tickformat=".1f"),
        yaxis3=dict(title="R2 · % · 阳轴", overlaying="y", side="right", anchor="free",
                    position=0.91, showgrid=False, fixedrange=True, tickformat=".1f", zeroline=True),
        yaxis4=dict(title="R3 · 万张", overlaying="y", side="right", anchor="free",
                    position=0.995, showgrid=False, fixedrange=True, tickformat=".1f", zeroline=True),
        meta={"missing_series": missing, "preserve_axis_titles": ["y2", "y3", "y6"]},
    )
    if japan_short is not None:
        fig.update_layout(yaxis_title="左轴 · 收益率 % / 利差 pp")
        fig.layout.meta["preserve_axis_titles"].append("y")
    has_topix = any(trace.name == TOPIX_NAME for trace in fig.data)
    if has_topix:
        fig.update_layout(
            xaxis_domain=[0, 0.63], yaxis2_position=0.65,
            yaxis3_position=0.75, yaxis4_position=0.85,
            yaxis5=dict(title="R4 · TOPIX · pts", overlaying="y", side="right", anchor="free",
                        position=0.95, showgrid=False, fixedrange=True, tickformat=",.0f"),
        )
    if any(trace.name == DXY_NAME for trace in fig.data):
        fig.update_layout(
            xaxis_domain=[0, 0.55], yaxis2_position=0.57,
            yaxis3_position=0.67, yaxis4_position=0.77,
            yaxis6=dict(title="R5 · DXY · pts", overlaying="y", side="right", anchor="free",
                        position=0.98, showgrid=False, fixedrange=True, tickformat=".1f"),
        )
        if has_topix:
            fig.update_layout(yaxis5_position=0.87)
    if latest is None:
        fig.add_annotation(text="数据暂不可用", x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False)
        return fig
    return apply_time_axis(fig, date_range, latest=latest)


def _append_overlay_traces(fig, sources):
    missing = list((fig.layout.meta or {}).get("missing_series", []))
    for source, axis_map in sources:
        missing.extend((source.layout.meta or {}).get("missing_series", []))
        for trace in source.data:
            trace = trace.to_plotly_json()
            trace["yaxis"] = axis_map[trace.get("yaxis", "y")]
            if trace.get("type") == "bar":
                color = trace.get("marker", {}).get("color", "#64748b")
                trace = {key: trace[key] for key in ("x", "y", "name", "yaxis", "meta", "hovertemplate") if key in trace}
                trace.update(type="scatter", mode="lines+markers", line=dict(color=color, width=2))
            fig.add_trace(trace)
    return list(dict.fromkeys(missing))


def combine_yen_carry_figures(base, *, volatility):
    """Keep funding and market prices; omit retired appreciation/realized vol."""
    fig = go.Figure(base)
    fig.data = tuple(t for t in fig.data if t.name != PRESSURE_NAME)
    remap = {"y4": "y3", "y5": "y4", "y6": "y5"}
    for trace in fig.data:
        trace.yaxis = remap.get(trace.yaxis, trace.yaxis)
        trace.name = {POSITION_NAME: POSITION_NAME.replace("(R3)", "(R2)"),
                      TOPIX_NAME: TOPIX_NAME.replace("(R4)", "(R3)"),
                      DXY_NAME: DXY_NAME.replace("(R5)", "(R4)")}.get(trace.name, trace.name)
    # Policy remains plotted, while both realized-volatility series are retired.
    policy = go.Figure(volatility)
    policy.data = tuple(t for t in policy.data if t.name == BOJ_POLICY_NAME)
    policy.update_layout(meta={"missing_series": [name for name in
        (volatility.layout.meta or {}).get("missing_series", []) if name == BOJ_POLICY_NAME]})
    missing = _append_overlay_traces(fig, [(policy, {"y2": "y", "y": "y"})])
    missing = [name for name in missing if name != PRESSURE_NAME]
    for key in ("yaxis3", "yaxis4", "yaxis5", "yaxis6"):
        fig.layout[key] = None
    titles = {
        "y": "收益率 % / 利差 pp / BOJ %", "y2": "USD/JPY · 阳轴",
        "y3": "CFTC · 万张", "y4": "TOPIX · pts", "y5": "DXY · pts",
    }
    for index, (ref, title) in enumerate(titles.items()):
        key = "yaxis" + (ref[1:] if ref != "y" else "")
        axis = dict(title=title, fixedrange=True, zeroline=True)
        if index:
            axis.update(overlaying="y", side="right", anchor="free",
                        position=min(.995, .58 + index * .075), showgrid=False)
        fig.update_layout(**{key: axis})
    fig.update_layout(height=680, margin=dict(l=75, r=300, t=150, b=70),
                      xaxis_domain=[0, .58], hovermode="x unified",
                      meta={"missing_series": missing,
                            "preserve_axis_titles": list(titles), "yen_combined": True})
    return fig


def combine_japan_holdings_figures(tic, *, holdings, hedging, date_range="5Y"):
    """Preserve the nine disclosed series, dates and units on four axes."""
    fig = go.Figure()
    missing = _append_overlay_traces(fig, [
        (tic, {"y": "y", "y2": "y2"}),
        (holdings, {"y": "y3"}), (hedging, {"y": "y4"}),
    ])
    titles = {"y": "TIC持仓 · 十亿美元", "y2": "TIC当月变动 · 十亿美元",
              "y3": "机构持仓 · 万亿日元", "y4": "汇率对冲率 · %"}
    for index, (ref, title) in enumerate(titles.items()):
        key = "yaxis" + (ref[1:] if ref != "y" else "")
        axis = dict(title=title, fixedrange=True, zeroline=True)
        if index:
            axis.update(overlaying="y", side="right", anchor="free",
                        position=.70 + index * .09, showgrid=False)
        fig.update_layout(**{key: axis})
    fig.update_layout(template="plotly_white", height=620,
                      margin=dict(l=75, r=230, t=150, b=70), xaxis_domain=[0, .70],
                      hovermode="x unified", meta={"missing_series": missing,
                      "preserve_axis_titles": list(titles)})
    return apply_time_axis(fig, date_range)
