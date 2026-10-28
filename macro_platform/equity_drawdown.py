"""Completed SPX/RSP price drawdowns; peaks never reset with the viewport."""
from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

from macro_platform.market_history import completed_daily_closes
from macro_platform.request_runtime import observed_cache

SNAPSHOT = Path(__file__).resolve().parents[1] / "data_snapshots/us_equity_daily.json"
PRICE_BASIS = "split_adjusted_close_ex_dividends"
SERIES = {
    "SPX": {"symbol": "^GSPC", "instrument": "INDEX", "name": "SPX（标普500市值加权）",
            "source": "https://finance.yahoo.com/quote/%5EGSPC/history/", "color": "#5070dd"},
    "RSP": {"symbol": "RSP", "instrument": "ETF", "name": "RSP（标普500等权ETF）",
            "source": "https://finance.yahoo.com/quote/RSP/history/", "color": "#ea580c"},
}


def completed_us_date(now=None):
    clock = pd.Timestamp.now(tz="America/New_York") if now is None else pd.Timestamp(now)
    clock = clock.tz_localize("UTC") if clock.tzinfo is None else clock
    clock = clock.tz_convert("America/New_York")
    day = clock.normalize().tz_localize(None)
    return day if (clock.hour, clock.minute) >= (16, 15) else day - pd.Timedelta(days=1)


def parse_yahoo_history(payload, key, now=None):
    config = SERIES[key]
    nodes = (payload.get("chart") or {}).get("result") or []
    if len(nodes) != 1:
        raise ValueError(f"{key}: missing price history")
    node = nodes[0]
    meta = node.get("meta") or {}
    if (meta.get("symbol") != config["symbol"] or meta.get("currency") != "USD"
            or meta.get("instrumentType") != config["instrument"]):
        raise ValueError(f"{key}: unexpected security, currency or instrument")
    if meta.get("dataGranularity") != "1d":
        raise ValueError(f"{key}: daily bars required; provider returned another frequency")
    # quote.close is split-adjusted but excludes dividend reinvestment.
    # adjclose includes distributions and must not be mixed with the SPX price index.
    return completed_daily_closes(node, now=now)


def calculate_drawdown(frame):
    """Calculate full-history, close-to-close running drawdowns without look-ahead."""
    result = frame[["observation_date", "close"]].copy()
    result["observation_date"] = pd.to_datetime(result["observation_date"], errors="coerce")
    result["close"] = pd.to_numeric(result["close"], errors="coerce")
    result = (result.dropna(subset=["observation_date"]).sort_values("observation_date")
              .drop_duplicates("observation_date", keep="last").reset_index(drop=True))
    valid = result["close"].map(lambda value: pd.notna(value) and math.isfinite(float(value)) and value > 0)
    result.loc[~valid, "close"] = float("nan")
    peak, peak_day = None, None
    peaks, peak_dates = [], []
    for row in result.itertuples():
        if pd.notna(row.close) and (peak is None or row.close > peak):
            peak, peak_day = float(row.close), row.observation_date
        peaks.append(peak)
        peak_dates.append(peak_day)
    result["peak"] = pd.to_numeric(pd.Series(peaks), errors="coerce")
    result["peak_date"] = pd.to_datetime(peak_dates)
    result["drop_amount"] = result["peak"] - result["close"]
    result["drawdown_pct"] = (result["close"] / result["peak"] - 1.0) * 100.0
    return result


@observed_cache(paths=lambda: (SNAPSHOT,))
def load_equity_history(key):
    empty = pd.DataFrame(columns=["observation_date", "close"])
    config = SERIES[key]
    try:
        payload = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        if payload.get("price_basis") != PRICE_BASIS:
            return empty
        node = payload["series"][key]
        if node.get("symbol") != config["symbol"] or node.get("frequency") != "1d":
            return empty
        frame = pd.DataFrame(node["records"]).rename(columns={"date": "observation_date"})
        frame = calculate_drawdown(frame)[["observation_date", "close"]]
        frame = frame.loc[frame.observation_date.le(completed_us_date())]
        frame.attrs.update({"source": config["source"], "fetched_at": payload.get("fetched_at"),
                            "price_basis": PRICE_BASIS})
        return frame
    except (OSError, KeyError, ValueError, TypeError, AttributeError):
        return empty


def build_drawdown_figure(histories, years=5, series=None):
    import plotly.graph_objects as go

    fig = go.Figure()
    summaries, missing = [], []
    for key, config in (SERIES if series is None else series).items():
        frame = calculate_drawdown(histories.get(key, pd.DataFrame(columns=["observation_date", "close"])))
        actual = frame.dropna(subset=["close", "drawdown_pct"])
        if actual.empty:
            missing.append(config["name"])
            continue
        latest = actual.iloc[-1]
        summaries.append({
            "symbol": key, "name": config["name"],
            "date": latest.observation_date.strftime("%Y-%m-%d"),
            "history_start": actual.observation_date.min().strftime("%Y-%m-%d"),
            "close": float(latest.close), "peak": float(latest.peak),
            "peak_date": latest.peak_date.strftime("%Y-%m-%d"),
            "drop_amount": float(latest.drop_amount),
            "decline_pct": max(0.0, -float(latest.drawdown_pct)),
        })
        # Compute all peaks above before limiting the rendered data volume.
        visible = frame.loc[frame.observation_date.ge(latest.observation_date - pd.DateOffset(years=years))]
        fig.add_trace(go.Scatter(
            x=visible.observation_date.tolist(), y=visible.drawdown_pct.tolist(),
            name=config["name"], mode="lines", connectgaps=False,
            line={"color": config["color"], "width": 2.5},
            hovertemplate=config["name"] + ": %{y:.2f}%<extra></extra>",
        ))
    fig.update_layout(
        yaxis={"title": "距此前收盘高点的回撤 (%)", "ticksuffix": "%", "zeroline": True},
        meta={"drawdown_summary": summaries, "missing_series": missing,
              "price_basis": PRICE_BASIS},
    )
    return fig


def build_price_figure(histories, years=5, series=None, split_axes=False):
    """Original prices; high guides follow the viewport, latest guides stay current."""
    import plotly.graph_objects as go

    fig = go.Figure()
    summaries, missing, references = [], [], []
    for key, config in (SERIES if series is None else series).items():
        frame = calculate_drawdown(histories.get(key, pd.DataFrame(columns=["observation_date", "close"])))
        actual = frame.dropna(subset=["close"])
        if actual.empty:
            missing.append(config["name"])
            continue
        latest = actual.iloc[-1]
        visible = frame.loc[frame.observation_date.ge(latest.observation_date - pd.DateOffset(years=years))]
        visible_actual = visible.dropna(subset=["close"])
        high = visible_actual.loc[visible_actual.close.idxmax()]
        axis_index = len(summaries) if split_axes else 0
        axis_ref = "y" if axis_index == 0 else f"y{axis_index + 1}"
        row = {"symbol": key, "name": config["name"], "date": latest.observation_date.strftime("%Y-%m-%d"),
               "history_start": actual.observation_date.min().strftime("%Y-%m-%d"),
               "close": float(latest.close), "peak": float(high.close),
               "peak_date": high.observation_date.strftime("%Y-%m-%d")}
        summaries.append(row)
        fig.add_trace(go.Scatter(
            x=visible.observation_date.tolist(), y=visible.close.tolist(), name=config["name"],
            yaxis=axis_ref, mode="lines", connectgaps=False,
            line={"color": config["color"], "width": 2.5},
            hovertemplate=config["name"] + ": %{y:,.2f}<extra></extra>"))
        # Shapes support the Plotly recovery path. The native adapter uses
        # equivalent markLine annotations, never artificial price observations.
        short = key if key in ("SPX", "RSP") else config["name"]
        side = "end" if split_axes and axis_index else "start"
        for kind, value, date, dash in (("最高收盘", row["peak"], row["peak_date"], "dot"),
                                         ("最新收盘", row["close"], row["date"], "dash")):
            label = f'{short} {"高" if kind == "最高收盘" else "现"} {value:,.2f}'
            if kind == "最高收盘":
                label += "\n" + date
            references.append({"series": config["name"], "axis": axis_ref, "kind": kind,
                               "value": value, "date": date, "label": label, "short": short,
                               "side": side if split_axes else ("start" if kind == "最高收盘" else "end"),
                               "color": config["color"]})
            fig.add_shape(type="line", xref="paper", x0=0, x1=1, yref=axis_ref, y0=value, y1=value,
                          line={"color": config["color"], "width": 1.2, "dash": dash})
            fig.add_annotation(xref="paper", x=0 if references[-1]["side"] == "start" else 1,
                               yref=axis_ref, y=value, text=label, showarrow=False,
                               xanchor="left" if references[-1]["side"] == "start" else "right",
                               yanchor="bottom" if kind == "最高收盘" else "top",
                               font={"color": config["color"], "size": 10})
        title = "SPX · pts" if split_axes and key == "SPX" else "RSP · USD" if split_axes and key == "RSP" else "指数点位 · pts"
        fig.update_layout(**{("yaxis" if axis_ref == "y" else "yaxis" + axis_ref[1:]): {
            "title": title, "side": "left" if axis_index == 0 else "right",
            **({"overlaying": "y"} if axis_index else {})}})
    fig.update_layout(meta={"price_summary": summaries, "price_reference_lines": references,
                            "price_reference_scope": "visible_window",
                            "missing_series": missing, "price_basis": PRICE_BASIS})
    return fig
