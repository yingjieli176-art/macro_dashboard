from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.graph_objects as go
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

    # Reindex monthly before pct_change so year-over-year means exactly 12 months.
    monthly = frame.set_index("observation_date").sort_index()
    full_index = pd.date_range(monthly.index.min(), monthly.index.max(), freq="MS")
    monthly = monthly.reindex(full_index)
    monthly.index.name = "observation_date"

    monthly["M2 YoY"] = monthly["m2_hkd"].pct_change(12, fill_method=None) * 100.0
    monthly["M3 YoY"] = monthly["m3_hkd"].pct_change(12, fill_method=None) * 100.0
    monthly["Monetary Base YoY"] = (
        monthly["monetary_base_total"].pct_change(12, fill_method=None) * 100.0
    )
    monthly["Aggregate Balance"] = monthly["aggr_balance"] / 1000.0
    monthly["HIBOR O/N"] = monthly["hibor_fixing_overnight"]
    monthly["HIBOR 3M"] = monthly["hibor_fixing_3m"]
    monthly["HKMA Base Rate"] = monthly["discount_window_base_rate"]
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


def liquidity_state(data: pd.DataFrame | None = None) -> dict[str, Any]:
    data = load_hk_liquidity() if data is None else data.copy()
    if data.empty:
        return {
            "label": "数据不可用",
            "tone": "neutral",
            "score": 0,
            "components": {},
        }

    m2 = _latest_value(data, "M2 YoY")
    balance = _latest_value(data, "Aggregate Balance")
    on = _latest_value(data, "HIBOR O/N")
    h3m = _latest_value(data, "HIBOR 3M")
    fx = _latest_value(data, "USD/HKD")

    components: dict[str, dict[str, Any]] = {}
    score = 0

    if m2 is not None:
        money_score = 1 if m2 >= 3 else (0 if m2 >= 0 else -1)
        score += money_score
        components["money"] = {"value": m2, "score": money_score}

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
        # 7.80 is neutral center; approaching 7.85 implies weaker HKD / tighter HKD funding pressure.
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
    latest = data.loc[data.drop(columns=["observation_date"]).notna().any(axis=1), "observation_date"].max()
    if pd.isna(latest):
        latest = data["observation_date"].max()
    offset = RANGE_OFFSETS.get(date_range, RANGE_OFFSETS["1Y"])
    start = latest - offset
    return data[data["observation_date"] >= start].copy()


def build_hk_liquidity_figure(date_range: str, compact_mode: bool = False) -> go.Figure:
    all_data = load_hk_liquidity()
    data = _slice_range(all_data, date_range)

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
        fig.update_layout(height=650 if compact_mode else 820, template="plotly_white")
        return fig

    def add_trace(row: int, column: str, name: str, width: float = 2.3, dash: str | None = None, unit: str = "%") -> None:
        if column not in data.columns or data[column].notna().sum() == 0:
            return
        line: dict[str, Any] = {"width": width}
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

    state = liquidity_state(all_data)
    meta = snapshot_metadata()
    latest_text = meta.get("latest_observation") or "--"
    fig.update_layout(
        height=720 if compact_mode else 900,
        template="plotly_white",
        hovermode="x unified",
        dragmode=False,
        margin=dict(l=60, r=25, t=88, b=42, pad=2),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.04,
            xanchor="left",
            x=0,
            font=dict(size=9 if compact_mode else 10),
            bgcolor="rgba(255,255,255,0)",
        ),
        title=dict(
            text=f"Hong Kong Liquidity · {state['label']} · latest {latest_text}",
            x=0.01,
            xanchor="left",
            font=dict(size=14 if compact_mode else 16),
        ),
        hoverlabel=dict(bgcolor="white", font_size=11, bordercolor="#e5e7eb"),
        font=dict(size=10 if compact_mode else 11),
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
    )
    grid = dict(showgrid=True, gridcolor="#e5e7eb", griddash="dot", fixedrange=True)
    fig.update_yaxes(title_text="YoY (%)", row=1, col=1, zeroline=True, zerolinecolor="#cbd5e1", **grid)
    fig.update_yaxes(title_text="HK$ bn", row=2, col=1, zeroline=False, **grid)
    fig.update_yaxes(title_text="Rate (%)", row=3, col=1, zeroline=True, zerolinecolor="#cbd5e1", **grid)
    fig.update_yaxes(title_text="USD/HKD", row=4, col=1, range=[7.73, 7.87], zeroline=False, **grid)
    fig.update_xaxes(showgrid=True, gridcolor="#eef2f7", griddash="dot", fixedrange=True, tickformat="%Y-%m", row=4, col=1)
    return fig


def liquidity_status_html() -> str:
    data = load_hk_liquidity()
    state = liquidity_state(data)
    meta = snapshot_metadata()
    latest = meta.get("latest_observation", "--")

    m2 = _latest_value(data, "M2 YoY")
    balance = _latest_value(data, "Aggregate Balance")
    on = _latest_value(data, "HIBOR O/N")
    h3m = _latest_value(data, "HIBOR 3M")
    fx = _latest_value(data, "USD/HKD")

    def fmt(value: float | None, suffix: str = "") -> str:
        return "--" if value is None else f"{value:,.2f}{suffix}"

    return f'''<div class="hk-liquidity-strip">
      <div><span>Liquidity</span><strong>{state['label']}</strong></div>
      <div><span>M2 YoY</span><strong>{fmt(m2, '%')}</strong></div>
      <div><span>Aggregate Balance</span><strong>{fmt(balance, ' bn')}</strong></div>
      <div><span>O/N HIBOR</span><strong>{fmt(on, '%')}</strong></div>
      <div><span>3M HIBOR</span><strong>{fmt(h3m, '%')}</strong></div>
      <div><span>USD/HKD</span><strong>{fmt(fx)}</strong></div>
      <div><span>Latest</span><strong>{latest}</strong></div>
    </div>'''
