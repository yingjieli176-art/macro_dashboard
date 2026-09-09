from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import requests
from plotly.subplots import make_subplots

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_PATH = ROOT / "data_snapshots" / "hkma_monetary_statistics.json"
RANGE_OFFSETS = {
    "5Y": pd.DateOffset(years=5),
    "1Y": pd.DateOffset(years=1),
    "6M": pd.DateOffset(months=6),
    "3M": pd.DateOffset(months=3),
    "1M": pd.DateOffset(months=1),
}

OUTPUT_COLUMNS = [
    "observation_date",
    "M2 MoM",
    "M3 MoM",
    "Monetary Base MoM",
    "M2 YoY",
    "M3 YoY",
    "Monetary Base YoY",
    "Aggregate Balance",
    "HIBOR O/N",
    "HIBOR 3M",
    "HKMA Base Rate",
    "O/N-3M Spread",
    "USD/HKD",
    "Strong-side CU",
    "Weak-side CU",
]

COLORS = {
    "m2": "#2563eb",
    "m3": "#7c3aed",
    "base": "#64748b",
    "balance": "#0f766e",
    "on": "#ea580c",
    "h3m": "#dc2626",
    "policy": "#475569",
    "spread": "#9333ea",
    "fx": "#2563eb",
    "strong": "#16a34a",
    "weak": "#dc2626",
}


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=OUTPUT_COLUMNS)


def _read_snapshot() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not SNAPSHOT_PATH.exists():
        return [], {"status": "missing", "source": "HKMA"}
    try:
        payload = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        return [], {"status": "invalid", "source": "HKMA", "error": str(exc)}

    if isinstance(payload, list):
        return payload, {"status": "ok", "source": "HKMA"}
    if not isinstance(payload, dict):
        return [], {"status": "invalid", "source": "HKMA"}
    rows = payload.get("records") or []
    meta = {
        "status": "ok" if rows else "empty",
        "source": payload.get("source", "HKMA Monetary Statistics"),
        "updated_at": payload.get("updated_at"),
        "record_count": len(rows),
    }
    return rows, meta


def load_hk_liquidity() -> pd.DataFrame:
    rows, _ = _read_snapshot()
    frame = pd.DataFrame(rows)
    if frame.empty or "end_of_month" not in frame.columns:
        return _empty_frame()

    period = frame["end_of_month"].astype(str)
    frame = frame[period.str.match(r"^\d{4}-(0[1-9]|1[0-2])$")].copy()
    frame["observation_date"] = pd.to_datetime(
        frame["end_of_month"], format="%Y-%m", errors="coerce"
    )
    frame = (
        frame.dropna(subset=["observation_date"])
        .sort_values("observation_date")
        .drop_duplicates("observation_date", keep="last")
    )
    if frame.empty:
        return _empty_frame()

    numeric = [
        "m2_hkd",
        "m3_hkd",
        "monetary_base_total",
        "aggr_balance",
        "hibor_fixing_overnight",
        "hibor_fixing_3m",
        "discount_window_base_rate",
        "exrate_hkd_usd",
    ]
    for col in numeric:
        if col not in frame.columns:
            frame[col] = pd.NA
        frame[col] = pd.to_numeric(frame[col], errors="coerce")

    # Reindex to a true monthly grid before growth-rate calculations.
    monthly = frame.set_index("observation_date").sort_index()
    full_index = pd.date_range(monthly.index.min(), monthly.index.max(), freq="MS")
    monthly = monthly.reindex(full_index)
    monthly.index.name = "observation_date"

    # MoM is the primary dashboard signal because it reacts faster to marginal liquidity changes.
    monthly["M2 MoM"] = monthly["m2_hkd"].pct_change(1, fill_method=None) * 100.0
    monthly["M3 MoM"] = monthly["m3_hkd"].pct_change(1, fill_method=None) * 100.0
    monthly["Monetary Base MoM"] = (
        monthly["monetary_base_total"].pct_change(1, fill_method=None) * 100.0
    )

    # Keep YoY in the data model for context / future switchable views, but do not use it as the primary chart signal.
    monthly["M2 YoY"] = monthly["m2_hkd"].pct_change(12, fill_method=None) * 100.0
    monthly["M3 YoY"] = monthly["m3_hkd"].pct_change(12, fill_method=None) * 100.0
    monthly["Monetary Base YoY"] = (
        monthly["monetary_base_total"].pct_change(12, fill_method=None) * 100.0
    )

    monthly["Aggregate Balance"] = monthly["aggr_balance"] / 1000.0
    monthly["HIBOR O/N"] = monthly["hibor_fixing_overnight"]
    monthly["HIBOR 3M"] = monthly["hibor_fixing_3m"]
    monthly["HKMA Base Rate"] = monthly["discount_window_base_rate"]
    monthly["O/N-3M Spread"] = (monthly["HIBOR O/N"] - monthly["HIBOR 3M"]) * 100.0
    monthly["USD/HKD"] = monthly["exrate_hkd_usd"]
    monthly["Strong-side CU"] = 7.75
    monthly["Weak-side CU"] = 7.85
    return monthly.reset_index()[OUTPUT_COLUMNS]


def snapshot_metadata() -> dict[str, Any]:
    _, meta = _read_snapshot()
    data = load_hk_liquidity()
    if not data.empty:
        meta["latest_observation"] = data["observation_date"].max().strftime("%Y-%m")
    return meta


def _latest_value(data: pd.DataFrame, column: str) -> float | None:
    if column not in data.columns:
        return None
    series = pd.to_numeric(data[column], errors="coerce").dropna()
    return float(series.iloc[-1]) if not series.empty else None


def _recent_money_momentum(data: pd.DataFrame) -> float | None:
    if data.empty:
        return None
    candidates = []
    for column in ("M2 MoM", "M3 MoM"):
        series = pd.to_numeric(data[column], errors="coerce").dropna().tail(3)
        if not series.empty:
            candidates.append(float(series.mean()))
    if not candidates:
        return None
    return sum(candidates) / len(candidates)


def liquidity_state(data: pd.DataFrame | None = None) -> dict[str, Any]:
    data = load_hk_liquidity() if data is None else data.copy()
    if data.empty:
        return {
            "label": "数据不可用",
            "tone": "neutral",
            "score": 0,
            "components": {},
        }

    money_momentum = _recent_money_momentum(data)
    balance = _latest_value(data, "Aggregate Balance")
    on = _latest_value(data, "HIBOR O/N")
    h3m = _latest_value(data, "HIBOR 3M")
    fx = _latest_value(data, "USD/HKD")

    components: dict[str, dict[str, Any]] = {}
    score = 0

    if money_momentum is not None:
        # 3M average of monthly M2/M3 growth: faster than YoY, but less noisy than a single MoM print.
        money_score = 1 if money_momentum >= 0.30 else (-1 if money_momentum <= -0.30 else 0)
        score += money_score
        components["money"] = {"value": money_momentum, "score": money_score}

    balance_series = pd.to_numeric(data["Aggregate Balance"], errors="coerce").dropna()
    if balance is not None and len(balance_series) >= 6:
        median = float(balance_series.tail(36).median())
        balance_score = 1 if balance > median * 1.25 else (-1 if balance < median * 0.75 else 0)
        score += balance_score
        components["balance"] = {
            "value": balance,
            "median": median,
            "score": balance_score,
        }

    if on is not None and h3m is not None:
        spread = on - h3m
        funding_score = -1 if spread > 0.50 else (1 if spread < -0.50 else 0)
        score += funding_score
        components["funding"] = {
            "overnight": on,
            "three_month": h3m,
            "spread": spread,
            "score": funding_score,
        }

    if fx is not None:
        # 7.80 is the center of the convertibility band; proximity to 7.85 indicates weaker HKD / tighter HKD funding pressure.
        fx_score = -1 if fx >= 7.835 else (1 if fx <= 7.765 else 0)
        score += fx_score
        components["fx"] = {"value": fx, "score": fx_score}

    if score >= 2:
        label, tone = "偏宽松", "positive"
    elif score <= -2:
        label, tone = "偏紧", "negative"
    else:
        label, tone = "中性", "neutral"
    return {"label": label, "tone": tone, "score": score, "components": components}


def _slice_range(data: pd.DataFrame, date_range: str) -> pd.DataFrame:
    if data.empty:
        return data
    latest = data.loc[
        data.drop(columns=["observation_date"]).notna().any(axis=1), "observation_date"
    ].max()
    if pd.isna(latest):
        latest = data["observation_date"].max()
    offset = RANGE_OFFSETS.get(date_range, RANGE_OFFSETS["1Y"])
    start = latest - offset
    return data[data["observation_date"] >= start].copy()


def _legend_text(items: list[tuple[str, str]]) -> str:
    return " &nbsp; ".join(
        f"<span style='color:{color}'>●</span> {label}" for label, color in items
    )


def build_hk_liquidity_figure(date_range: str, compact_mode: bool = False) -> go.Figure:
    all_data = load_hk_liquidity()
    data = _slice_range(all_data, date_range)

    fig = make_subplots(
        rows=4,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.085,
        row_heights=[0.27, 0.18, 0.29, 0.26],
        specs=[[{}], [{}], [{"secondary_y": True}], [{}]],
    )

    if data.empty:
        fig.add_annotation(
            text="HKMA snapshot unavailable · data pipeline needs refresh",
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
            font=dict(size=14),
        )
        fig.update_layout(height=900, template="plotly_white")
        return fig

    legend_map = {1: "legend", 2: "legend2", 3: "legend3", 4: "legend4"}

    def add_trace(
        row: int,
        column: str,
        name: str,
        color: str,
        width: float = 2.3,
        dash: str | None = None,
        unit: str = "%",
        secondary_y: bool = False,
    ) -> None:
        if column not in data.columns or data[column].notna().sum() == 0:
            return
        line: dict[str, Any] = {"width": width, "color": color}
        if dash:
            line["dash"] = dash
        fig.add_trace(
            go.Scatter(
                x=data["observation_date"],
                y=data[column],
                name=name,
                mode="lines",
                line=line,
                connectgaps=False,
                showlegend=True,
                legend=legend_map[row],
                legendrank=100 + row,
                hovertemplate=f"{name}: %{{y:.3f}}{unit}<extra></extra>",
            ),
            row=row,
            col=1,
            secondary_y=secondary_y,
        )

    # Order is analytical reading order and is mirrored by each local legend.
    add_trace(1, "M2 MoM", "M2 MoM", COLORS["m2"], 2.8)
    add_trace(1, "M3 MoM", "M3 MoM", COLORS["m3"], 2.3, "dash")
    add_trace(1, "Monetary Base MoM", "Monetary Base MoM", COLORS["base"], 1.8, "dot")

    add_trace(2, "Aggregate Balance", "Aggregate Balance", COLORS["balance"], 2.8, unit=" HK$ bn")

    add_trace(3, "HIBOR O/N", "O/N HIBOR", COLORS["on"], 2.0)
    add_trace(3, "HIBOR 3M", "3M HIBOR", COLORS["h3m"], 2.3, "dash")
    add_trace(3, "HKMA Base Rate", "HKMA Base Rate", COLORS["policy"], 2.0, "dot")
    add_trace(3, "O/N-3M Spread", "O/N−3M Spread (R)", COLORS["spread"], 1.7, "dashdot", " bp", secondary_y=True)

    add_trace(4, "USD/HKD", "USD/HKD", COLORS["fx"], 2.6, unit="")
    add_trace(4, "Strong-side CU", "Strong-side 7.75", COLORS["strong"], 1.4, "dot", unit="")
    add_trace(4, "Weak-side CU", "Weak-side 7.85", COLORS["weak"], 1.4, "dot", unit="")

    state = liquidity_state(all_data)
    meta = snapshot_metadata()
    latest_text = meta.get("latest_observation") or "--"
    fig.update_layout(
        height=960,
        template="plotly_white",
        hovermode="x unified",
        dragmode=False,
        margin=dict(l=62, r=70, t=74, b=42, pad=2),
        title=dict(
            text=f"Hong Kong Liquidity · {state['label']} · latest {latest_text}",
            x=0.01,
            xanchor="left",
            font=dict(size=16),
        ),
        hoverlabel=dict(bgcolor="white", font_size=11, bordercolor="#e5e7eb"),
        font=dict(size=11),
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        legend=dict(traceorder="normal", groupclick="toggleitem", itemclick="toggle", itemdoubleclick="toggleothers"),
    )

    grid = dict(showgrid=True, gridcolor="#e5e7eb", griddash="dot", fixedrange=True)
    fig.update_yaxes(title_text="MoM (%)", row=1, col=1, zeroline=True, zerolinecolor="#cbd5e1", **grid)
    fig.update_yaxes(title_text="HK$ bn", row=2, col=1, zeroline=False, **grid)
    fig.update_yaxes(title_text="Rate (%)", row=3, col=1, secondary_y=False, zeroline=True, zerolinecolor="#cbd5e1", **grid)
    fig.update_yaxes(title_text="Spread (bp)", row=3, col=1, secondary_y=True, showgrid=False, zeroline=True, zerolinecolor="#cbd5e1", fixedrange=True)
    fig.update_yaxes(title_text="USD/HKD", row=4, col=1, range=[7.73, 7.87], zeroline=False, **grid)
    fig.update_xaxes(showgrid=True, gridcolor="#eef2f7", griddash="dot", fixedrange=True, tickformat="%Y-%m", row=4, col=1)

    legend_style = dict(
        orientation="h",
        x=0.0,
        xanchor="left",
        yanchor="bottom",
        bgcolor="rgba(255,255,255,0.88)",
        borderwidth=0,
        font=dict(size=10, color="#374151"),
        itemsizing="constant",
        traceorder="normal",
    )
    # Multiple Plotly legends keep each parameter selector next to its own subplot.
    domains = [fig.layout.yaxis.domain, fig.layout.yaxis2.domain, fig.layout.yaxis3.domain, fig.layout.yaxis5.domain]
    for idx, domain in enumerate(domains, start=1):
        key = "legend" if idx == 1 else f"legend{idx}"
        cfg = dict(legend_style)
        cfg["y"] = min(0.995, float(domain[1]) + 0.012)
        fig.layout[key] = cfg

    return fig


def _market_monthly_close(symbol: str, label: str) -> pd.DataFrame:
    """Fetch monthly close-to-close percentage change from Yahoo Finance.

    Market overlays are enrichment only: a network/API failure returns an empty
    frame and must never prevent the HKMA liquidity charts from rendering.
    """
    try:
        response = requests.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
            params={
                "range": "5y",
                "interval": "1mo",
                "includeAdjustedClose": "true",
                "events": "div,splits",
            },
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=3.5,
        )
        response.raise_for_status()
        result = (((response.json() or {}).get("chart") or {}).get("result") or [])
        if not result:
            return pd.DataFrame(columns=["observation_date", label])
        node = result[0] or {}
        timestamps = node.get("timestamp") or []
        indicators = node.get("indicators") or {}
        adj = (indicators.get("adjclose") or [{}])[0].get("adjclose") or []
        closes = adj if len(adj) == len(timestamps) else ((indicators.get("quote") or [{}])[0].get("close") or [])
        if len(closes) != len(timestamps):
            return pd.DataFrame(columns=["observation_date", label])
        frame = pd.DataFrame(
            {
                "observation_date": pd.to_datetime(timestamps, unit="s", utc=True, errors="coerce").tz_convert(None),
                "close": pd.to_numeric(closes, errors="coerce"),
            }
        ).dropna()
        if frame.empty:
            return pd.DataFrame(columns=["observation_date", label])
        frame["observation_date"] = frame["observation_date"].dt.to_period("M").dt.to_timestamp()
        frame = frame.sort_values("observation_date").drop_duplicates("observation_date", keep="last")
        frame[label] = frame["close"]
        return frame[["observation_date", label]].dropna(subset=[label])
    except Exception:
        return pd.DataFrame(columns=["observation_date", label])


def build_hk_liquidity_figures(date_range: str, compact_mode: bool = False) -> list[go.Figure]:
    """Build four independent Hong Kong liquidity charts for the dashboard."""
    all_data = load_hk_liquidity()
    data = _slice_range(all_data, date_range)
    meta = snapshot_metadata()
    latest_text = meta.get("latest_observation") or "--"

    if data.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="HKMA snapshot unavailable · data pipeline needs refresh",
            x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False,
            font=dict(size=14),
        )
        fig.update_layout(height=420, template="plotly_white")
        return [fig]

    # Market overlays use month-end price/index levels. No percentage transformation is applied.
    hkex_price = _market_monthly_close("0388.HK", "HKEX Price")
    hstech_index = _market_monthly_close("HSTECH.HK", "HSTECH Index")
    market_data = data[["observation_date"]].copy()
    for frame in (hkex_price, hstech_index):
        if not frame.empty:
            market_data = market_data.merge(frame, on="observation_date", how="left")

    def add_line(
        fig: go.Figure,
        frame: pd.DataFrame,
        column: str,
        name: str,
        color: str,
        width: float = 2.3,
        dash: str | None = None,
        unit: str = "%",
        secondary_y: bool | None = None,
    ) -> None:
        if column not in frame.columns or frame[column].notna().sum() == 0:
            return
        line: dict[str, Any] = {"width": width, "color": color}
        if dash:
            line["dash"] = dash
        trace = go.Scatter(
            x=frame["observation_date"], y=frame[column], name=name, mode="lines",
            line=line, connectgaps=False,
            hovertemplate=f"{name}: %{{y:.3f}}{unit}<extra></extra>",
        )
        if secondary_y is None:
            fig.add_trace(trace)
        else:
            fig.add_trace(trace, secondary_y=secondary_y)

    def add_constant(
        fig: go.Figure,
        value: float,
        name: str,
        color: str,
        dash: str = "dot",
        width: float = 1.4,
        secondary_y: bool | None = None,
    ) -> None:
        trace = go.Scatter(
            x=data["observation_date"], y=[value] * len(data), name=name, mode="lines",
            line=dict(width=width, color=color, dash=dash), connectgaps=True,
            hovertemplate=f"{name}: %{{y:.3f}}<extra></extra>",
        )
        if secondary_y is None:
            fig.add_trace(trace)
        else:
            fig.add_trace(trace, secondary_y=secondary_y)

    def style(fig: go.Figure, title: str, height: int = 430, right_axis: bool = False) -> go.Figure:
        fig.update_layout(
            height=height,
            template="plotly_white",
            hovermode="x unified",
            dragmode=False,
            margin=dict(l=62, r=82 if right_axis else 28, t=96, b=44, pad=2),
            title=dict(text=f"{title} · latest {latest_text}", x=0.01, xanchor="left", font=dict(size=16)),
            legend=dict(
                orientation="h", yanchor="bottom", y=1.08, xanchor="left", x=0,
                font=dict(size=11), traceorder="normal", itemwidth=30,
                bgcolor="rgba(255,255,255,0)", itemclick="toggle", itemdoubleclick="toggleothers",
            ),
            hoverlabel=dict(bgcolor="white", font_size=11, bordercolor="#e5e7eb"),
            font=dict(size=12), plot_bgcolor="#ffffff", paper_bgcolor="#ffffff",
        )
        fig.update_xaxes(
            showgrid=True, gridcolor="#eef2f7", griddash="dot",
            showline=True, linecolor="#9ca3af", linewidth=1,
            fixedrange=True, tickformat="%Y-%m", tickfont=dict(size=11), automargin=False,
        )
        return fig

    # 5-1 · Money supply + Hong Kong equity market monthly changes.
    money = make_subplots(specs=[[{"secondary_y": True}]])
    add_line(money, data, "M2 MoM", "M2 MoM", COLORS["m2"], 2.8, secondary_y=False)
    add_line(money, data, "M3 MoM", "M3 MoM", COLORS["m3"], 2.3, "dash", secondary_y=False)
    add_line(money, data, "Monetary Base MoM", "Monetary Base MoM", COLORS["base"], 1.8, "dot", secondary_y=False)
    add_line(money, market_data, "HKEX Price", "HKEX Price (R)", "#0891b2", 2.1, unit=" HKD", secondary_y=True)
    add_line(money, market_data, "HSTECH Index", "HSTECH Index (R)", "#db2777", 2.1, "dash", unit=" pts", secondary_y=True)
    money.update_yaxes(
        title_text="Money MoM (%)", secondary_y=False,
        showgrid=True, gridcolor="#e5e7eb", griddash="dot",
        zeroline=True, zerolinecolor="#cbd5e1", fixedrange=True,
    )
    money.update_yaxes(
        title_text="Market Price / Index Level", secondary_y=True,
        showgrid=False, zeroline=True, zerolinecolor="#cbd5e1", fixedrange=True,
    )
    style(money, "5-1. HK Money Supply & Market Pulse", right_axis=True)

    # 5-2 · Banking-system liquidity.
    balance = go.Figure()
    add_line(balance, data, "Aggregate Balance", "Aggregate Balance", COLORS["balance"], 2.8, unit=" HK$ bn")
    balance.update_yaxes(
        title_text="HK$ bn", showgrid=True, gridcolor="#e5e7eb", griddash="dot",
        zeroline=False, fixedrange=True,
    )
    style(balance, "5-2. Banking-system Liquidity")

    # 5-3 · HKD funding.
    funding = make_subplots(specs=[[{"secondary_y": True}]])
    add_line(funding, data, "HIBOR O/N", "O/N HIBOR", COLORS["on"], 2.0, secondary_y=False)
    add_line(funding, data, "HIBOR 3M", "3M HIBOR", COLORS["h3m"], 2.3, "dash", secondary_y=False)
    add_line(funding, data, "HKMA Base Rate", "HKMA Base Rate", COLORS["policy"], 2.0, "dot", secondary_y=False)
    add_line(funding, data, "O/N-3M Spread", "O/N−3M Spread (R)", COLORS["spread"], 1.7, "dashdot", " bp", secondary_y=True)
    funding.update_yaxes(
        title_text="Rate (%)", secondary_y=False,
        showgrid=True, gridcolor="#e5e7eb", griddash="dot",
        zeroline=True, zerolinecolor="#cbd5e1", fixedrange=True,
    )
    funding.update_yaxes(
        title_text="Spread (bp)", secondary_y=True,
        showgrid=False, zeroline=True, zerolinecolor="#cbd5e1", fixedrange=True,
    )
    style(funding, "5-3. HKD Funding", right_axis=True)

    # 5-4 · Convertibility band + market reaction.
    fx = make_subplots(specs=[[{"secondary_y": True}]])
    add_line(fx, data, "USD/HKD", "USD/HKD", COLORS["fx"], 2.6, unit="", secondary_y=False)
    add_constant(fx, 7.75, "Strong-side CU 7.75", COLORS["strong"], "dot", 1.4, secondary_y=False)
    add_constant(fx, 7.80, "Linked Rate Center 7.80", "#64748b", "dash", 1.5, secondary_y=False)
    add_constant(fx, 7.85, "Weak-side CU 7.85", COLORS["weak"], "dot", 1.4, secondary_y=False)
    add_line(fx, market_data, "HKEX Price", "HKEX Price (R)", "#0891b2", 2.1, unit=" HKD", secondary_y=True)
    add_line(fx, market_data, "HSTECH Index", "HSTECH Index (R)", "#db2777", 2.1, "dash", unit=" pts", secondary_y=True)
    fx.add_hrect(
        y0=7.75, y1=7.85,
        fillcolor="rgba(148,163,184,0.10)",
        line_width=0, layer="below",
        annotation_text="7.75–7.85 LERS band",
        annotation_position="top left",
    )
    fx.update_yaxes(
        title_text="USD/HKD", secondary_y=False, range=[7.73, 7.87],
        showgrid=True, gridcolor="#e5e7eb", griddash="dot",
        zeroline=False, fixedrange=True,
    )
    fx.update_yaxes(
        title_text="Market Price / Index Level", secondary_y=True,
        showgrid=False, zeroline=True, zerolinecolor="#cbd5e1", fixedrange=True,
    )
    style(fx, "5-4. USD/HKD Convertibility Band & Market", height=450, right_axis=True)

    return [money, balance, funding, fx]

def liquidity_status_html() -> str:
    data = load_hk_liquidity()
    state = liquidity_state(data)
    meta = snapshot_metadata()
    latest = meta.get("latest_observation", "--")

    m2 = _latest_value(data, "M2 MoM")
    m3 = _latest_value(data, "M3 MoM")
    balance = _latest_value(data, "Aggregate Balance")
    on = _latest_value(data, "HIBOR O/N")
    h3m = _latest_value(data, "HIBOR 3M")
    fx = _latest_value(data, "USD/HKD")

    def fmt(value: float | None, suffix: str = "") -> str:
        return "--" if value is None else f"{value:,.2f}{suffix}"

    return f'''<div class="hk-liquidity-strip">
      <div><span>Liquidity</span><strong>{state['label']}</strong></div>
      <div><span>M2 MoM</span><strong>{fmt(m2, '%')}</strong></div>
      <div><span>M3 MoM</span><strong>{fmt(m3, '%')}</strong></div>
      <div><span>Aggregate Balance</span><strong>{fmt(balance, ' bn')}</strong></div>
      <div><span>O/N HIBOR</span><strong>{fmt(on, '%')}</strong></div>
      <div><span>USD/HKD</span><strong>{fmt(fx)}</strong></div>
      <div><span>Latest</span><strong>{latest}</strong></div>
    </div>'''
