from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import requests
from plotly.subplots import make_subplots

from macro_platform.chart_axes import apply_time_axis

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_PATH = ROOT / "data_snapshots" / "hkma_monetary_statistics.json"
DAILY_BANKING_SNAPSHOT_PATH = ROOT / "data_snapshots" / "hkma_banking_liquidity_daily.json"
HSTECH_SNAPSHOT_PATH = ROOT / "data_snapshots" / "hstech_monthly.json"
HK_MARKET_DAILY_SNAPSHOT_PATH = ROOT / "data_snapshots" / "hk_market_daily.json"
USDHKD_SNAPSHOT_PATH = ROOT / "data_snapshots" / "usdhkd_daily.json"
HIBOR_SNAPSHOT_PATH = ROOT / "data_snapshots" / "hkd_hibor_monthly.json"
BASE_RATE_SNAPSHOT_PATH = ROOT / "data_snapshots" / "hkma_base_rate_monthly.json"
DAILY_BANKING_COLUMNS = [
    "observation_date",
    "Opening Aggregate Balance",
    "Closing Aggregate Balance",
    "Forecast Aggregate Balance T+1",
    "Outstanding EFBN",
    "EFBN Held by Licensed Banks",
]
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
    "Outstanding EFBN",
    "EFBN Held by Licensed Banks",
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
    "m2_mom": "#0ea5e9",
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
        "ef_bills_notes",
        "outstanding_efbn",
        "ow_lb_bf_disc_win",
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

    # MoM remains the fast signal used by the liquidity-state logic because it reacts quickly to marginal changes.
    monthly["M2 MoM"] = monthly["m2_hkd"].pct_change(1, fill_method=None) * 100.0
    monthly["M3 MoM"] = monthly["m3_hkd"].pct_change(1, fill_method=None) * 100.0
    monthly["Monetary Base MoM"] = (
        monthly["monetary_base_total"].pct_change(1, fill_method=None) * 100.0
    )

    # YoY is the primary Chart 5 display because it is smoother and better suited to medium-term money-growth trends.
    monthly["M2 YoY"] = monthly["m2_hkd"].pct_change(12, fill_method=None) * 100.0
    monthly["M3 YoY"] = monthly["m3_hkd"].pct_change(12, fill_method=None) * 100.0
    monthly["Monetary Base YoY"] = (
        monthly["monetary_base_total"].pct_change(12, fill_method=None) * 100.0
    )

    monthly["Aggregate Balance"] = monthly["aggr_balance"] / 1000.0
    # Monetary-base structure is stored in HK$ million by HKMA.
    # Prefer the dedicated end-period field and fall back to the equivalent
    # monetary-statistics EF Bills & Notes field if needed.
    monthly["Outstanding EFBN"] = monthly["outstanding_efbn"].combine_first(
        monthly["ef_bills_notes"]
    ) / 1000.0
    monthly["EFBN Held by Licensed Banks"] = monthly["ow_lb_bf_disc_win"] / 1000.0
    monthly["HIBOR O/N"] = monthly["hibor_fixing_overnight"]
    monthly["HIBOR 3M"] = monthly["hibor_fixing_3m"]
    monthly["HKMA Base Rate"] = monthly["discount_window_base_rate"]
    monthly["O/N-3M Spread"] = (monthly["HIBOR O/N"] - monthly["HIBOR 3M"]) * 100.0
    monthly["USD/HKD"] = monthly["exrate_hkd_usd"]
    monthly["Strong-side CU"] = 7.75
    monthly["Weak-side CU"] = 7.85
    return monthly.reset_index()[OUTPUT_COLUMNS]



def load_hk_banking_liquidity_monthly() -> pd.DataFrame:
    """Return real monthly HKMA banking-liquidity history for long windows."""
    monthly = load_hk_liquidity()
    if monthly.empty:
        return pd.DataFrame(columns=DAILY_BANKING_COLUMNS)
    fallback = monthly[[
        "observation_date",
        "Aggregate Balance",
        "Outstanding EFBN",
        "EFBN Held by Licensed Banks",
    ]].copy()
    fallback = fallback.rename(columns={"Aggregate Balance": "Closing Aggregate Balance"})
    # HKMA monthly history does not publish the daily opening balance or T+1
    # forecast. Keep them empty rather than cloning the closing balance.
    fallback["Opening Aggregate Balance"] = pd.NA
    fallback["Forecast Aggregate Balance T+1"] = pd.NA
    value_cols = [
        "Closing Aggregate Balance",
        "Outstanding EFBN",
        "EFBN Held by Licensed Banks",
    ]
    fallback = fallback.dropna(how="all", subset=value_cols)
    return fallback[DAILY_BANKING_COLUMNS]


def load_hk_banking_liquidity_daily() -> pd.DataFrame:
    """Load daily HK banking-system liquidity from the repository snapshot.

    Values are converted from HK$ million to HK$ billion. If the daily snapshot
    is unavailable, fall back to the monthly Aggregate Balance so Chart 5-2
    remains usable instead of failing the entire Hong Kong liquidity section.
    """
    try:
        payload = json.loads(DAILY_BANKING_SNAPSHOT_PATH.read_text(encoding="utf-8"))
        rows = payload.get("records") if isinstance(payload, dict) else payload
        frame = pd.DataFrame(rows or [])
    except Exception:
        frame = pd.DataFrame()

    if frame.empty or "end_of_date" not in frame.columns:
        return load_hk_banking_liquidity_monthly()

    frame["observation_date"] = pd.to_datetime(frame["end_of_date"], errors="coerce")
    mapping = {
        "opening_balance": "Opening Aggregate Balance",
        "closing_balance": "Closing Aggregate Balance",
        "forecast_aggregate_bal_t1": "Forecast Aggregate Balance T+1",
        "outstanding_efbn": "Outstanding EFBN",
        "ow_lb_bf_disc_win": "EFBN Held by Licensed Banks",
    }
    for source, target in mapping.items():
        frame[target] = pd.to_numeric(frame.get(source), errors="coerce") / 1000.0
    frame = (
        frame.dropna(subset=["observation_date"])
        .sort_values("observation_date")
        .drop_duplicates("observation_date", keep="last")
    )
    return frame[DAILY_BANKING_COLUMNS]


def load_hk_funding_monthly() -> pd.DataFrame:
    """Build a continuous monthly HKD funding history from persisted official data.

    O/N and 3M HIBOR come from the C&SD monthly-digest snapshot (underlying
    HKAB/HKMA sources). The HKMA Base Rate comes from the dedicated HKMA
    Discount Window end-of-period snapshot. Recent values in the core HKMA
    monetary snapshot remain a fallback for months not yet present upstream.
    """
    columns = ["observation_date", "HIBOR O/N", "HIBOR 3M", "HKMA Base Rate", "O/N-3M Spread"]
    core = load_hk_liquidity()
    if core.empty:
        funding = pd.DataFrame(columns=columns[:-1]).set_index("observation_date")
    else:
        funding = core[["observation_date", "HIBOR O/N", "HIBOR 3M", "HKMA Base Rate"]].copy()
        funding = funding.set_index("observation_date").sort_index()

    try:
        payload = json.loads(HIBOR_SNAPSHOT_PATH.read_text(encoding="utf-8"))
        rows = payload.get("records") if isinstance(payload, dict) else payload
        hibor = pd.DataFrame(rows or [])
    except Exception:
        hibor = pd.DataFrame()
    if not hibor.empty and "end_of_month" in hibor.columns:
        hibor["observation_date"] = pd.to_datetime(hibor["end_of_month"], format="%Y-%m", errors="coerce")
        hibor["HIBOR O/N"] = pd.to_numeric(hibor.get("hibor_overnight"), errors="coerce")
        hibor["HIBOR 3M"] = pd.to_numeric(hibor.get("hibor_3m"), errors="coerce")
        hibor = hibor.dropna(subset=["observation_date"]).set_index("observation_date")[["HIBOR O/N", "HIBOR 3M"]]
        union = funding.index.union(hibor.index)
        funding = funding.reindex(union)
        for col in ("HIBOR O/N", "HIBOR 3M"):
            funding[col] = hibor[col].reindex(union).combine_first(funding[col])

    try:
        payload = json.loads(BASE_RATE_SNAPSHOT_PATH.read_text(encoding="utf-8"))
        rows = payload.get("records") if isinstance(payload, dict) else payload
        base_rate = pd.DataFrame(rows or [])
    except Exception:
        base_rate = pd.DataFrame()
    if not base_rate.empty and "end_of_month" in base_rate.columns:
        base_rate["observation_date"] = pd.to_datetime(base_rate["end_of_month"], format="%Y-%m", errors="coerce")
        base_rate["HKMA Base Rate"] = pd.to_numeric(base_rate.get("disc_win_base_rate"), errors="coerce")
        base_rate = base_rate.dropna(subset=["observation_date"]).set_index("observation_date")[["HKMA Base Rate"]]
        union = funding.index.union(base_rate.index)
        funding = funding.reindex(union)
        funding["HKMA Base Rate"] = base_rate["HKMA Base Rate"].reindex(union).combine_first(funding["HKMA Base Rate"])

    funding = funding.sort_index()
    funding["O/N-3M Spread"] = (funding["HIBOR O/N"] - funding["HIBOR 3M"]) * 100.0
    funding.index.name = "observation_date"
    return funding.reset_index()[columns]


def load_hk_funding_daily() -> pd.DataFrame:
    """Load O/N HIBOR, 3M HIBOR and Base Rate from the daily HKMA snapshot.

    If the daily snapshot is unavailable, use the monthly official series. The
    chart title separately labels this as a monthly fallback so freshness is
    never overstated.
    """
    columns = ["observation_date", "HIBOR O/N", "HIBOR 3M", "HKMA Base Rate", "O/N-3M Spread"]
    try:
        payload = json.loads(DAILY_BANKING_SNAPSHOT_PATH.read_text(encoding="utf-8"))
        rows = payload.get("records") if isinstance(payload, dict) else payload
        frame = pd.DataFrame(rows or [])
    except Exception:
        frame = pd.DataFrame()
    if not frame.empty and "end_of_date" in frame.columns:
        frame["observation_date"] = pd.to_datetime(frame["end_of_date"], errors="coerce")
        frame["HIBOR O/N"] = pd.to_numeric(frame.get("hibor_overnight"), errors="coerce")
        frame["HIBOR 3M"] = pd.to_numeric(frame.get("hibor_3m"), errors="coerce")
        frame["HKMA Base Rate"] = pd.to_numeric(frame.get("disc_win_base_rate"), errors="coerce")
        frame["O/N-3M Spread"] = (frame["HIBOR O/N"] - frame["HIBOR 3M"]) * 100.0
        frame = frame.dropna(subset=["observation_date"]).sort_values("observation_date").drop_duplicates("observation_date", keep="last")
        if frame[["HIBOR O/N", "HIBOR 3M", "HKMA Base Rate"]].notna().any(axis=1).sum() >= 10:
            return frame[columns]
    return load_hk_funding_monthly()


def _daily_snapshot_available() -> bool:
    try:
        payload = json.loads(DAILY_BANKING_SNAPSHOT_PATH.read_text(encoding="utf-8"))
        rows = payload.get("records") if isinstance(payload, dict) else payload
        return isinstance(rows, list) and len(rows) >= 10
    except Exception:
        return False


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
    add_trace(1, "M2 YoY", "M2 YoY", COLORS["m2"], 2.8)
    add_trace(1, "M2 MoM", "M2 MoM", COLORS["m2_mom"], 2.1, "dash")
    add_trace(1, "Monetary Base YoY", "Monetary Base YoY", COLORS["base"], 1.8, "dot")

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
            text=f"Hong Kong Liquidity · monthly signal {state['label']} · through {latest_text}",
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
    fig.update_yaxes(title_text="Money Growth (%)", row=1, col=1, zeroline=True, zerolinecolor="#cbd5e1", **grid)
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


def _hstech_snapshot_monthly(label: str) -> pd.DataFrame:
    try:
        payload = json.loads(HSTECH_SNAPSHOT_PATH.read_text(encoding="utf-8"))
        rows = payload.get("records") if isinstance(payload, dict) else payload
        frame = pd.DataFrame(rows or [])
    except Exception:
        return pd.DataFrame(columns=["observation_date", label])
    if frame.empty or "observation_date" not in frame.columns or "close" not in frame.columns:
        return pd.DataFrame(columns=["observation_date", label])
    frame["observation_date"] = pd.to_datetime(frame["observation_date"], errors="coerce")
    frame[label] = pd.to_numeric(frame["close"], errors="coerce")
    frame = frame.dropna(subset=["observation_date", label]).sort_values("observation_date")
    return frame[["observation_date", label]].drop_duplicates("observation_date", keep="last")


def _market_snapshot_history(symbol: str, label: str, date_range: str) -> pd.DataFrame:
    """Load persisted daily Hong Kong market history and adapt density by window.

    1M/3M/6M/1Y retain trading-day observations. 5Y is reduced to weekly
    closes to keep Plotly responsive without destroying the shape of the cycle.
    """
    try:
        payload = json.loads(HK_MARKET_DAILY_SNAPSHOT_PATH.read_text(encoding="utf-8"))
        node = ((payload.get("series") or {}).get(symbol) or {})
        frame = pd.DataFrame(node.get("records") or [])
    except Exception:
        return pd.DataFrame(columns=["observation_date", label])
    if frame.empty or "observation_date" not in frame.columns or "close" not in frame.columns:
        return pd.DataFrame(columns=["observation_date", label])
    frame["observation_date"] = pd.to_datetime(frame["observation_date"], errors="coerce")
    frame[label] = pd.to_numeric(frame["close"], errors="coerce")
    frame = (
        frame.dropna(subset=["observation_date", label])
        .sort_values("observation_date")
        .drop_duplicates("observation_date", keep="last")
    )
    if frame.empty:
        return pd.DataFrame(columns=["observation_date", label])
    start = frame["observation_date"].max() - RANGE_OFFSETS.get(date_range, RANGE_OFFSETS["1Y"])
    frame = frame.loc[frame["observation_date"] >= start, ["observation_date", label]].copy()
    if date_range == "5Y" and not frame.empty:
        frame = (
            frame.set_index("observation_date")[label]
            .resample("W-FRI")
            .last()
            .dropna()
            .rename(label)
            .reset_index()
        )
    return frame


def _market_history(symbol: str, label: str, date_range: str) -> pd.DataFrame:
    snapshot_symbol = "HSTECH" if str(symbol).upper() in {"HSTECH", "HSTECH.HK", "^HSTECH"} else symbol
    snapshot = _market_snapshot_history(snapshot_symbol, label, date_range)
    minimum = 200 if date_range == "5Y" else 10
    if len(snapshot) >= minimum:
        return snapshot
    # Emergency fallback only. Normal dashboard renders should never need live
    # history because GitHub Actions maintains the last-known-good snapshot.
    monthly = _market_monthly_close(symbol, label)
    if monthly.empty:
        return monthly
    return _slice_range(monthly, date_range)


def _rebase_market_data(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    rebased = frame.copy()
    for column in columns:
        if column not in rebased.columns:
            continue
        valid = pd.to_numeric(rebased[column], errors="coerce").dropna()
        if valid.empty or float(valid.iloc[0]) == 0:
            continue
        rebased[column] = pd.to_numeric(rebased[column], errors="coerce") / float(valid.iloc[0]) * 100.0
    return rebased


def _market_monthly_close(symbol: str, label: str) -> pd.DataFrame:
    if str(symbol).upper() in {"HSTECH.HK", "^HSTECH", "HSTECH"}:
        snapshot = _hstech_snapshot_monthly(label)
        if len(snapshot) >= 48:
            return snapshot
    """Fetch up to five years of month-end market levels.

    Yahoo market history is enrichment only. Try both public chart hosts and,
    for Hang Seng TECH, a secondary symbol alias. A failure must never blank
    the HKMA liquidity charts.
    """
    symbols = [symbol]
    if str(symbol).upper() == "HSTECH.HK":
        symbols.append("^HSTECH")
    hosts = (
        "https://query1.finance.yahoo.com/v8/finance/chart/",
        "https://query2.finance.yahoo.com/v8/finance/chart/",
    )
    for market_symbol in symbols:
        for host in hosts:
            try:
                response = requests.get(
                    host + market_symbol,
                    params={
                        "range": "5y",
                        "interval": "1mo",
                        "includeAdjustedClose": "true",
                        "events": "div,splits",
                    },
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=4.0,
                )
                response.raise_for_status()
                result = (((response.json() or {}).get("chart") or {}).get("result") or [])
                if not result:
                    continue
                node = result[0] or {}
                timestamps = node.get("timestamp") or []
                indicators = node.get("indicators") or {}
                quote_close = (indicators.get("quote") or [{}])[0].get("close") or []
                adj_close = (indicators.get("adjclose") or [{}])[0].get("adjclose") or []
                closes = adj_close if len(adj_close) == len(timestamps) else quote_close
                if len(closes) != len(timestamps):
                    continue
                frame = pd.DataFrame(
                    {
                        "observation_date": pd.to_datetime(
                            timestamps, unit="s", utc=True, errors="coerce"
                        ).tz_convert(None),
                        label: pd.to_numeric(closes, errors="coerce"),
                    }
                ).dropna(subset=["observation_date", label])
                if frame.empty:
                    continue
                frame["observation_date"] = (
                    frame["observation_date"].dt.to_period("M").dt.to_timestamp()
                )
                return (
                    frame.sort_values("observation_date")
                    .drop_duplicates("observation_date", keep="last")
                    [["observation_date", label]]
                )
            except Exception:
                continue
    return pd.DataFrame(columns=["observation_date", label])


def _usdhkd_snapshot_daily(label: str) -> pd.DataFrame:
    """Load repository-persisted USD/HKD daily history.

    The snapshot is refreshed from Yahoo HKD=X by GitHub Actions so the chart
    does not depend on a live FRED request during a Streamlit page render.
    """
    try:
        payload = json.loads(USDHKD_SNAPSHOT_PATH.read_text(encoding="utf-8"))
        rows = payload.get("records") if isinstance(payload, dict) else payload
        frame = pd.DataFrame(rows or [])
    except Exception:
        return pd.DataFrame(columns=["observation_date", label])
    if frame.empty or "observation_date" not in frame.columns or "value" not in frame.columns:
        return pd.DataFrame(columns=["observation_date", label])
    frame["observation_date"] = pd.to_datetime(frame["observation_date"], errors="coerce")
    frame[label] = pd.to_numeric(frame["value"], errors="coerce")
    frame = (
        frame.dropna(subset=["observation_date", label])
        .sort_values("observation_date")
        .drop_duplicates("observation_date", keep="last")
    )
    return frame[["observation_date", label]]


def _fred_daily_series(series_id: str, label: str) -> pd.DataFrame:
    """Load a daily series, preferring a repository snapshot for USD/HKD."""
    if series_id == "DEXHKUS":
        snapshot = _usdhkd_snapshot_daily(label)
        if len(snapshot) >= 1000:
            cutoff = snapshot["observation_date"].max() - pd.DateOffset(years=5)
            return snapshot.loc[snapshot["observation_date"] >= cutoff].copy()
    try:
        response = requests.get(
            "https://fred.stlouisfed.org/graph/fredgraph.csv",
            params={"id": series_id},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=4.0,
        )
        response.raise_for_status()
        frame = pd.read_csv(StringIO(response.text))
        if frame.empty or len(frame.columns) < 2:
            return pd.DataFrame(columns=["observation_date", label])
        date_col = frame.columns[0]
        value_col = series_id if series_id in frame.columns else frame.columns[1]
        frame["observation_date"] = pd.to_datetime(frame[date_col], errors="coerce")
        frame[label] = pd.to_numeric(frame[value_col], errors="coerce")
        frame = frame.dropna(subset=["observation_date", label]).sort_values("observation_date")
        if frame.empty:
            return pd.DataFrame(columns=["observation_date", label])
        cutoff = frame["observation_date"].max() - pd.DateOffset(years=5)
        return frame.loc[frame["observation_date"] >= cutoff, ["observation_date", label]].copy()
    except Exception:
        return pd.DataFrame(columns=["observation_date", label])



def _frame_is_daily(frame: pd.DataFrame) -> bool:
    if frame is None or frame.empty or "observation_date" not in frame.columns:
        return False
    dates = pd.to_datetime(frame["observation_date"], errors="coerce").dropna().drop_duplicates().sort_values()
    if len(dates) < 3:
        return False
    gaps = dates.diff().dropna().dt.total_seconds() / 86400.0
    if gaps.empty:
        return False
    return float(gaps.median()) <= 7.0 and float((gaps <= 7.0).mean()) >= 0.60

def build_hk_liquidity_figures(
    date_range: str, compact_mode: bool = False, market_mode: str = "Raw"
) -> list[go.Figure]:
    """Build four independent Hong Kong liquidity charts for the dashboard."""
    all_data = load_hk_liquidity()
    data = _slice_range(all_data, date_range)
    banking_source = load_hk_banking_liquidity_monthly() if date_range == "5Y" else load_hk_banking_liquidity_daily()
    funding_source = load_hk_funding_monthly() if date_range == "5Y" else load_hk_funding_daily()
    banking_is_daily = _frame_is_daily(banking_source)
    funding_is_daily = _frame_is_daily(funding_source)
    banking_data = _slice_range(banking_source, date_range)
    funding_data = _slice_range(funding_source, date_range)
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

    # Market overlays are persisted as daily last-known-good history. Short
    # windows retain daily detail; the 5Y view is sampled to weekly closes.
    tencent_price = _market_history("0700.HK", "Tencent Price", date_range)
    hkex_price = _market_history("0388.HK", "HKEX Price", date_range)
    hstech_index = _market_history("HSTECH", "HSTECH Index", date_range)
    hsi_index = _market_history("^HSI", "HSI Index", date_range)
    market_columns = ["Tencent Price", "HKEX Price", "HSTECH Index", "HSI Index"]
    market_data = pd.DataFrame(columns=["observation_date"])
    for frame in (tencent_price, hkex_price, hstech_index, hsi_index):
        if frame.empty:
            continue
        if market_data.empty:
            market_data = frame.copy()
        else:
            market_data = market_data.merge(frame, on="observation_date", how="outer")
    if not market_data.empty:
        market_data = market_data.sort_values("observation_date")
    raw_market = str(market_mode).strip().lower() == "raw"
    if not raw_market and not market_data.empty:
        market_data = _rebase_market_data(market_data, market_columns)

    # Monthly HKMA FX is useful for consistency, but DEXHKUS gives a much fresher
    # daily five-year USD/HKD history for the convertibility-band panel.
    fx_daily = _fred_daily_series("DEXHKUS", "USD/HKD")

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
        axis: str | None = None,
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
        if axis is not None:
            trace.update(yaxis=axis)
            fig.add_trace(trace)
        elif secondary_y is None:
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
        x_frame: pd.DataFrame | None = None,
    ) -> None:
        base = data if x_frame is None or x_frame.empty else x_frame
        trace = go.Scatter(
            x=base["observation_date"], y=[value] * len(base), name=name, mode="lines",
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
            # Top margin has two dedicated rows: centered year labels, then legend.
            margin=dict(l=62, r=82 if right_axis else 28, t=124, b=54, pad=2),
            legend=dict(
                orientation="h", yanchor="bottom", y=1.17, xanchor="left", x=0,
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
        # Initialize charts 5-8 with the same two-level time axis as charts 1-4.
        return apply_time_axis(fig, date_range)

    # 5 · Money supply + Hong Kong equity market. Raw mode separates stock
    # prices (R1) from index levels (R2); Rebased 100 puts all market assets
    # onto one comparable relative-performance axis.
    money = make_subplots(specs=[[{"secondary_y": True}]])
    add_line(money, data, "M2 YoY", "M2 YoY", COLORS["m2"], 2.8, secondary_y=False)
    add_line(money, data, "M2 MoM", "M2 MoM", COLORS["m2_mom"], 2.1, "dash", secondary_y=False)
    add_line(money, data, "Monetary Base YoY", "Monetary Base YoY", COLORS["base"], 1.8, "dot", secondary_y=False)
    if raw_market:
        add_line(money, market_data, "Tencent Price", "Tencent Price (R1)", "#111827", 2.3, unit=" HKD", secondary_y=True)
        add_line(money, market_data, "HKEX Price", "HKEX Price (R1)", "#0891b2", 2.0, "dash", unit=" HKD", secondary_y=True)
        add_line(money, market_data, "HSTECH Index", "HSTECH Index (R2)", "#db2777", 2.1, "dash", unit=" pts", axis="y3")
        add_line(money, market_data, "HSI Index", "HSI Index (R2)", "#d97706", 2.0, "dot", unit=" pts", axis="y3")
    else:
        add_line(money, market_data, "Tencent Price", "Tencent (R)", "#111827", 2.3, unit="", secondary_y=True)
        add_line(money, market_data, "HKEX Price", "HKEX (R)", "#0891b2", 2.0, "dash", unit="", secondary_y=True)
        add_line(money, market_data, "HSTECH Index", "HSTECH (R)", "#db2777", 2.1, "dash", unit="", secondary_y=True)
        add_line(money, market_data, "HSI Index", "HSI (R)", "#d97706", 2.0, "dot", unit="", secondary_y=True)
    money.update_yaxes(
        title_text="Money Growth (%)", secondary_y=False,
        showgrid=True, gridcolor="#e5e7eb", griddash="dot",
        zeroline=True, zerolinecolor="#cbd5e1", fixedrange=True,
    )
    money.update_yaxes(
        title_text="R1 · HKD Price" if raw_market else "Market · Rebased 100", secondary_y=True,
        showgrid=False, zeroline=False, fixedrange=True,
    )
    style(money, "5. HK Money Supply & Market Pulse", right_axis=True)
    if raw_market:
        money.update_layout(
            margin=dict(l=62, r=142, t=124, b=54, pad=2),
            xaxis=dict(domain=[0.0, 0.84]),
            yaxis2=dict(overlaying="y", side="right", anchor="free", position=0.86, title="R1 · HKD Price", showgrid=False, fixedrange=True, tickfont=dict(size=10)),
            yaxis3=dict(overlaying="y", side="right", anchor="free", position=0.97, title="R2 · Index Level", showgrid=False, fixedrange=True, tickfont=dict(size=10)),
        )
    else:
        money.update_layout(
            margin=dict(l=62, r=94, t=124, b=54, pad=2),
            xaxis=dict(domain=[0.0, 0.91]),
            yaxis2=dict(title="Market · Rebased 100", showgrid=False, fixedrange=True),
        )
    if not market_data.empty:
        market_latest = market_data["observation_date"].max().strftime("%Y-%m-%d")

    # 5-2 · Daily banking-system liquidity and monetary-base structure.
    balance = make_subplots(specs=[[{"secondary_y": True}]])
    add_line(balance, banking_data, "Opening Aggregate Balance", "Opening Aggregate Balance", "#64748b", 1.7, "dot", unit=" HK$ bn", secondary_y=False)
    add_line(balance, banking_data, "Closing Aggregate Balance", "Closing Aggregate Balance", COLORS["balance"], 2.9, unit=" HK$ bn", secondary_y=False)
    add_line(balance, banking_data, "Forecast Aggregate Balance T+1", "Forecast Aggregate Balance T+1", "#0284c7", 2.0, "dash", unit=" HK$ bn", secondary_y=False)
    add_line(balance, banking_data, "Outstanding EFBN", "Outstanding EFBN (R)", "#7c3aed", 2.0, unit=" HK$ bn", secondary_y=True)
    add_line(balance, banking_data, "EFBN Held by Licensed Banks", "EFBN Held by Licensed Banks (R)", "#c026d3", 1.8, "dash", unit=" HK$ bn", secondary_y=True)
    balance.update_yaxes(
        title_text="Aggregate Balance (HK$ bn)", secondary_y=False,
        showgrid=True, gridcolor="#e5e7eb", griddash="dot",
        zeroline=False, fixedrange=True,
    )
    balance.update_yaxes(
        title_text="EFBN (HK$ bn)", secondary_y=True,
        showgrid=False, zeroline=False, fixedrange=True,
    )
    banking_frequency_label = "Daily" if banking_is_daily else ("Monthly" if date_range == "5Y" else "Monthly fallback")
    style(balance, f"6. Banking-system Liquidity · {banking_frequency_label}", height=450, right_axis=True)

    # 5-3 · HKD funding.
    funding = make_subplots(specs=[[{"secondary_y": True}]])
    add_line(funding, funding_data, "HIBOR O/N", "O/N HIBOR", COLORS["on"], 2.0, secondary_y=False)
    add_line(funding, funding_data, "HIBOR 3M", "3M HIBOR", COLORS["h3m"], 2.3, "dash", secondary_y=False)
    add_line(funding, funding_data, "HKMA Base Rate", "HKMA Base Rate", COLORS["policy"], 2.0, "dot", secondary_y=False)
    add_line(funding, funding_data, "O/N-3M Spread", "O/N−3M Spread (R)", COLORS["spread"], 1.7, "dashdot", " bp", secondary_y=True)
    funding.update_yaxes(
        title_text="Rate (%)", secondary_y=False,
        showgrid=True, gridcolor="#e5e7eb", griddash="dot",
        zeroline=True, zerolinecolor="#cbd5e1", fixedrange=True,
    )
    funding.update_yaxes(
        title_text="Spread (bp)", secondary_y=True,
        showgrid=False, zeroline=True, zerolinecolor="#cbd5e1", fixedrange=True,
    )
    funding_frequency_label = "Daily" if funding_is_daily else ("Monthly" if date_range == "5Y" else "Monthly fallback")
    style(funding, f"7. HKD Funding · {funding_frequency_label}", right_axis=True)

    # 8 · Convertibility band + market reaction.
    fx = make_subplots(specs=[[{"secondary_y": True}]])
    fx_source = fx_daily if not fx_daily.empty else data[["observation_date", "USD/HKD"]].dropna().copy()
    add_line(fx, fx_source, "USD/HKD", "USD/HKD", COLORS["fx"], 2.6, unit="", secondary_y=False)
    add_constant(fx, 7.75, "Strong-side CU 7.75", COLORS["strong"], "dot", 1.4, secondary_y=False, x_frame=fx_source)
    add_constant(fx, 7.80, "Linked Rate Center 7.80", "#64748b", "dash", 1.5, secondary_y=False, x_frame=fx_source)
    add_constant(fx, 7.85, "Weak-side CU 7.85", COLORS["weak"], "dot", 1.4, secondary_y=False, x_frame=fx_source)
    if raw_market:
        add_line(fx, market_data, "Tencent Price", "Tencent Price (R1)", "#111827", 2.3, unit=" HKD", secondary_y=True)
        add_line(fx, market_data, "HKEX Price", "HKEX Price (R1)", "#0891b2", 2.0, "dash", unit=" HKD", secondary_y=True)
        add_line(fx, market_data, "HSTECH Index", "HSTECH Index (R2)", "#db2777", 2.1, "dash", unit=" pts", axis="y3")
        add_line(fx, market_data, "HSI Index", "HSI Index (R2)", "#d97706", 2.0, "dot", unit=" pts", axis="y3")
    else:
        add_line(fx, market_data, "Tencent Price", "Tencent (R)", "#111827", 2.3, unit="", secondary_y=True)
        add_line(fx, market_data, "HKEX Price", "HKEX (R)", "#0891b2", 2.0, "dash", unit="", secondary_y=True)
        add_line(fx, market_data, "HSTECH Index", "HSTECH (R)", "#db2777", 2.1, "dash", unit="", secondary_y=True)
        add_line(fx, market_data, "HSI Index", "HSI (R)", "#d97706", 2.0, "dot", unit="", secondary_y=True)
    fx.add_hrect(
        y0=7.75, y1=7.85,
        fillcolor="rgba(148,163,184,0.08)",
        line_width=0, layer="below",
        annotation_text="7.75–7.85 LERS band",
        annotation_position="top left",
    )
    fx.add_hrect(
        y0=7.84, y1=7.85,
        fillcolor="rgba(220,38,38,0.09)",
        line_width=0, layer="below",
        annotation_text="Weak-side Pressure 7.84–7.85",
        annotation_position="bottom left",
    )
    fx.update_yaxes(
        title_text="USD/HKD · Strong ↑ / Weak ↓", secondary_y=False, range=[7.87, 7.73],
        showgrid=True, gridcolor="#e5e7eb", griddash="dot",
        zeroline=False, fixedrange=True,
    )
    fx.update_yaxes(
        title_text="R1 · HKD Price" if raw_market else "Market · Rebased 100", secondary_y=True,
        showgrid=False, zeroline=False, fixedrange=True,
    )
    style(fx, "8. USD/HKD Convertibility Band & Market", height=470, right_axis=True)
    if raw_market:
        fx.update_layout(
            margin=dict(l=62, r=142, t=124, b=54, pad=2),
            xaxis=dict(domain=[0.0, 0.84]),
            yaxis2=dict(overlaying="y", side="right", anchor="free", position=0.86, title="R1 · HKD Price", showgrid=False, fixedrange=True, tickfont=dict(size=10)),
            yaxis3=dict(overlaying="y", side="right", anchor="free", position=0.97, title="R2 · Index Level", showgrid=False, fixedrange=True, tickfont=dict(size=10)),
        )
    else:
        fx.update_layout(
            margin=dict(l=62, r=94, t=124, b=54, pad=2),
            xaxis=dict(domain=[0.0, 0.91]),
            yaxis2=dict(title="Market · Rebased 100", showgrid=False, fixedrange=True),
        )
    if not fx_source.empty:
        fx_latest = fx_source["observation_date"].max().strftime("%Y-%m-%d")

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
      <div><span>HKMA monthly through</span><strong>{latest}</strong></div>
    </div>'''
