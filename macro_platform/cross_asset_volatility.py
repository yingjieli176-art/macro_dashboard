"""Cross-asset option-implied volatility, with independently sourced observations.

OVX: Cboe daily closes, with FRED OVXCLS as fallback.
MOVE: existing validated ICE BofA ^MOVE daily-close snapshot.
EUR/USD and USD/JPY: dated one-month implied-volatility references from MINKABU.
"""
import json
import math
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from macro_platform import jpy_implied_vol as saxobank
from macro_platform import move_index
from macro_platform.chart_axes import apply_time_axis
from macro_platform.cboe_history import OVX_HISTORY_URL

FRED_URL = "https://fred.stlouisfed.org/series/OVXCLS"
MOVE_URL = move_index.SOURCE_URL
SNAPSHOT_DIR = Path(__file__).resolve().parents[1] / "data_snapshots"
MINKABU_NEWS_URL = "https://fx.minkabu.jp/news"
USDJPY_REFERENCE_SNAPSHOT = SNAPSHOT_DIR / "usdjpy_1m_minkabu.json"
EURUSD_REFERENCE_SNAPSHOT = SNAPSHOT_DIR / "eurusd_1m_minkabu.json"
USDJPY_REFERENCE_IDENTITY = {
    "symbol": "USDJPY_1M_MINKABU", "source": "MINKABU PRESS", "pair": "USDJPY",
    "tenor": "1M", "quote_type": "implied_volatility_reference", "unit": "percent",
}
EURUSD_REFERENCE_IDENTITY = {**USDJPY_REFERENCE_IDENTITY, "symbol": "EURUSD_1M_MINKABU", "pair": "EURUSD"}
USDJPY_REFERENCE_NAME = "USD/JPY 1M 隐含波动率（MINKABU 参考）"
EURUSD_REFERENCE_NAME = "EUR/USD 1M 隐含波动率（MINKABU 参考）"


def _validate_records(payload, identity):
    if any(payload.get(k) != v for k, v in identity.items()):
        raise ValueError("Unexpected 1M ATM snapshot identity")
    records = [saxobank._validate_record(row) for row in payload.get("records", ())]
    dates = [row["observation_date"] for row in records]
    if dates != sorted(set(dates)):
        raise ValueError("Duplicate or unsorted implied volatility dates")
    return records


def _load_snapshot(path, identity):
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return _validate_records(payload, identity=identity)
    except (OSError, ValueError, KeyError, TypeError, OverflowError):
        return []


def load_usdjpy_reference(path=USDJPY_REFERENCE_SNAPSHOT):
    return _load_snapshot(path, USDJPY_REFERENCE_IDENTITY)


def load_eurusd_reference(path=EURUSD_REFERENCE_SNAPSHOT):
    return _load_snapshot(path, EURUSD_REFERENCE_IDENTITY)


def _valid_series(frame, column, minimum=0, maximum=10000):
    if frame is None or frame.empty or not {"observation_date", column}.issubset(frame.columns):
        return pd.DataFrame(columns=["observation_date", column])
    data = frame[["observation_date", column]].copy()
    data["observation_date"] = pd.to_datetime(data["observation_date"], errors="coerce")
    data[column] = pd.to_numeric(data[column], errors="coerce")
    data = data.dropna(subset=["observation_date", column])
    data = data.loc[data[column].gt(minimum) & data[column].lt(maximum)]
    return data.drop_duplicates("observation_date", keep="last").sort_values("observation_date")


TEN_YEAR_YIELD_URL = "https://fred.stlouisfed.org/series/DGS10"
BRENT_URL = "https://fred.stlouisfed.org/series/DCOILBRENTEU"
WTI_URL = "https://fred.stlouisfed.org/series/DCOILWTICO"
REALIZED_WINDOW = 20
TRADING_DAYS_YEAR = 252
HISTORY_START = pd.Timestamp("2020-01-01")


def twenty_day_realized_volatility(frame, column, *, yield_basis_points=False):
    """Rolling 20 observed daily changes, annualized by sqrt(252).

    US10Y is the DGS10 yield level (not bond price or bond total return).
    DGS10 is quoted in percent: first-difference in percentage points and
    multiply by 100 for bp. Oil uses log price returns, annualized in %.
    Always require 20 valid consecutive returns (21 closes); do not fill gaps
    or mistake 20 calendar days for 20 observed trading sessions.
    """
    empty = pd.DataFrame(columns=["observation_date", "rv20"])
    if frame is None or frame.empty or not {"observation_date", column}.issubset(frame.columns):
        return empty
    series = frame[["observation_date", column]].copy()
    series["observation_date"] = pd.to_datetime(series["observation_date"], errors="coerce")
    series[column] = pd.to_numeric(series[column], errors="coerce")
    series = (series.dropna(subset=["observation_date"])
              .drop_duplicates("observation_date", keep="last")
              .sort_values("observation_date"))
    values = series[column].where(series[column].gt(0) & series[column].lt(float("inf")))
    if yield_basis_points:
        # Yield-change volatility: ΔDGS10 in bp, NOT bond-price returns.
        returns = values.diff() * 100.0
    else:
        # Invalid/zero/negative observations remain gaps and cannot be used
        # as the base of the following day's return.
        import numpy as np
        returns = np.log(values / values.shift(1)) * 100.0
    series["rv20"] = returns.rolling(REALIZED_WINDOW, min_periods=REALIZED_WINDOW).std(ddof=1) * math.sqrt(TRADING_DAYS_YEAR)
    return series[["observation_date", "rv20"]].dropna().reset_index(drop=True)


def _historical_iv_trace(name, rows, axis, color):
    reference = _valid_series(pd.DataFrame(rows), "value", maximum=100)
    reference = reference.loc[reference.observation_date.ge(HISTORY_START)]
    if reference.empty:
        return None
    dates, values = [], []
    for row in reference.itertuples(index=False):
        if dates and row.observation_date - dates[-1] > pd.Timedelta(days=45):
            dates.append(dates[-1] + pd.Timedelta(days=1))
            values.append(math.nan)
        dates.append(row.observation_date)
        values.append(row.value)
    return go.Scatter(
        x=dates, y=values, name=name, yaxis=axis, mode="lines+markers",
        connectgaps=False, line={"color": color, "dash": "dash", "width": 2.1},
        marker={"size": 4},
        hovertemplate="%{x|%Y-%m-%d}<br>" + name + ": %{y:.2f}%<extra></extra>",
    )


def build_usdjpy_1m_figure(reference_records=None, *, axis="y"):
    """Share the same dated MINKABU history across dashboard charts."""
    rows = load_usdjpy_reference() if reference_records is None else reference_records
    reference = _historical_iv_trace(USDJPY_REFERENCE_NAME, rows, axis, "#047857")
    fig = go.Figure()
    if reference is not None:
        fig.add_trace(reference)
    fig.update_layout(meta={"missing_series": [] if reference is not None else [USDJPY_REFERENCE_NAME]})
    return fig


def build_figure(date_range="5Y", *, ovx=None, move=None, usdjpy_reference=None,
                 eurusd_reference=None, treasury10y=None, brent=None, wti=None):
    fig = go.Figure()
    sources = (
        ("OVXCLS", ovx, "OVX · 原油30天隐含波动率", "#ea580c", "y", "%"),
        ("MOVE", move, "MOVE · 美债期权波动率", "#0e7490", "y2", "指数点"),
    )
    missing = []
    for column, frame, label, color, axis, unit in sources:
        valid = _valid_series(frame, column)
        valid = valid.loc[valid.observation_date.ge(HISTORY_START)]
        if valid.empty:
            missing.append(label)
            continue
        fig.add_trace(go.Scatter(x=valid.observation_date, y=valid[column],
            name=label, yaxis=axis, mode="lines", connectgaps=False,
            line={"color":color,"width":2.8},
            meta={"observation_cadence":"daily"},
            hovertemplate="%{x|%Y-%m-%d}<br>"+label+": %{y:.2f} "+unit+"<extra></extra>"))
    rows = load_eurusd_reference() if eurusd_reference is None else eurusd_reference
    euro_history = _historical_iv_trace(EURUSD_REFERENCE_NAME, rows, "y3", "#6d28d9")
    if euro_history is None:
        missing.append(EURUSD_REFERENCE_NAME)
    else:
        fig.add_trace(euro_history)
    yen = build_usdjpy_1m_figure(usdjpy_reference, axis="y4")
    fig.add_traces(yen.data)
    missing.extend(yen.layout.meta["missing_series"])
    realized_inputs = (
        (treasury10y, "DGS10", "美国10Y国债收益率 · 20D实现波动率（DGS10变动）",
         "#be123c", "y5", "年化bp", True),
        (brent, "DCOILBRENTEU", "Brent 20D 历史波动率",
         "#c2410c", "y6", "年化%", False),
        (wti, "DCOILWTICO", "WTI 20D 历史波动率",
         "#2563eb", "y6", "年化%", False),
    )
    for frame, column, label, color, axis, unit, yield_bp in realized_inputs:
        realized = twenty_day_realized_volatility(
            frame, column, yield_basis_points=yield_bp)
        realized = realized.loc[realized.observation_date.ge(HISTORY_START)]
        if realized.empty:
            missing.append(label)
            continue
        fig.add_trace(go.Scatter(
            x=realized["observation_date"], y=realized["rv20"],
            name=label, yaxis=axis, mode="lines", connectgaps=False,
            line={"color":color, "width":2.5},
            meta={"observation_cadence":"daily"},
            hovertemplate="%{x|%Y-%m-%d}<br>"+label+": %{y:.2f} "+unit+
                          "<extra></extra>"))
    fig.update_layout(
        yaxis={"title":"L · OVX · 年化%", "showgrid":True},
        yaxis2={"title":"R1 · MOVE · 指数点", "overlaying":"y","side":"right",
                "anchor":"free","position":0.84,"showgrid":False},
        yaxis3={"title":"R2 · EUR/USD 1M · 年化%", "overlaying":"y",
                "side":"right","anchor":"free","position":0.88,"showgrid":False},
        yaxis4={"title":"R3 · USD/JPY 1M · 年化%", "overlaying":"y",
                "side":"right","anchor":"free","position":0.80,"showgrid":False},
        yaxis5={"title":"R4 · 美国10Y国债收益率20D实现波动率 · 年化bp",
                "overlaying":"y","side":"right","anchor":"free",
                "position":0.88,"showgrid":False},
        yaxis6={"title":"R5 · Brent / WTI 20D历史波动率 · 年化%",
                "overlaying":"y","side":"right","anchor":"free",
                "position":0.98,"showgrid":False},
        xaxis={"domain":[0.0,0.68]},
        margin={"l":66,"r":290,"t":105,"b":45},
        legend={"orientation":"h","x":0,"y":1.13},
        meta={"missing_series":missing,
              "axis_order":["y","y2","y3","y4","y5","y6"],
              "preserve_axis_titles":["y","y2","y3","y4","y5","y6"],
              "realized_volatility_method":
              "20 consecutive observed daily changes; sample std × sqrt(252); "
              "US10Y daily yield changes × 100 (bp); oil daily log returns × 100 (%)"},
    )
    return apply_time_axis(fig, date_range) if fig.data else fig
