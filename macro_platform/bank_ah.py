"""H shares' discount versus corresponding A shares, in the same currency."""
import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

SNAPSHOT = Path(__file__).resolve().parents[1] / "data_snapshots/bank_ah_daily.json"
BANKS = {"ABC": ("农业银行", "601288.SS", "1288.HK", "#08916c"),
         "ICBC": ("工商银行", "601398.SS", "1398.HK", "#1677cc"),
         "CCB": ("建设银行", "601939.SS", "0939.HK", "#bd226b")}


def calculate_premium(a, h, fx):
    """Retain the public API, but use H discount to A as the primary measure."""
    frame = a.rename(columns={"close": "a_cny"}).merge(
        h.rename(columns={"close": "h_hkd"}), on="observation_date", how="inner").merge(
        fx.rename(columns={"close": "cny_per_hkd"}), on="observation_date", how="inner")
    frame = frame.dropna().sort_values("observation_date").drop_duplicates("observation_date")
    frame = frame.loc[(frame[["a_cny", "h_hkd", "cny_per_hkd"]] > 0).all(axis=1)].copy()
    frame["h_discount_pct"] = (
        1 - frame.h_hkd * frame.cny_per_hkd / frame.a_cny) * 100
    return frame


def _discount_rows(rows):
    """Recalculate all dates from prices, including older premium-only snapshots.

    Never use a premium number as though it already were the H discount.
    The original daily A/H prices and FX remain the authority.
    """
    frame = pd.DataFrame(rows)
    required = {"observation_date", "a_cny", "h_hkd", "cny_per_hkd"}
    if not required.issubset(frame.columns):
        return pd.DataFrame()
    for col in ("a_cny", "h_hkd", "cny_per_hkd"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame["observation_date"] = pd.to_datetime(frame["observation_date"], errors="coerce")
    frame = frame.dropna(subset=list(required))
    frame = frame.loc[(frame[["a_cny", "h_hkd", "cny_per_hkd"]] > 0).all(axis=1)].copy()
    frame = frame.drop_duplicates("observation_date", keep="last").sort_values("observation_date")
    frame["h_discount_pct"] = (
        1 - frame["h_hkd"] * frame["cny_per_hkd"] / frame["a_cny"]) * 100
    return frame


def add_bank_premiums(fig, date_range="5Y"):
    from macro_platform.chart_axes import RANGE_OFFSETS
    try:
        payload = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fig
    for key, (name, _, _, color) in BANKS.items():
        frame = _discount_rows(payload.get("series", {}).get(key, {}).get("records", []))
        if frame.empty:
            continue
        today = pd.Timestamp.now(tz="Asia/Hong_Kong").tz_localize(None).normalize()
        frame = frame.loc[frame.observation_date.le(today)]
        if date_range in RANGE_OFFSETS and not frame.empty:
            frame = frame.loc[frame.observation_date >= frame.observation_date.max() - RANGE_OFFSETS[date_range]]
        if frame.empty:
            continue
        customdata = frame[["a_cny", "h_hkd", "cny_per_hkd"]].to_numpy()
        fig.add_trace(go.Scatter(
            x=frame.observation_date, y=frame.h_discount_pct,
            name=f"{name} H股相对A股折价率（R2）", yaxis="y3", mode="lines",
            line=dict(color=color, width=2), connectgaps=False,
            customdata=customdata,
            hovertemplate=(
                "%{x|%Y-%m-%d}<br>H股相对A股折价：%{y:.2f}%"
                "<br>A收盘：%{customdata[0]:.3f} CNY"
                "<br>H收盘：%{customdata[1]:.3f} HKD"
                "<br>1 HKD = %{customdata[2]:.5f} CNY"
                "<extra></extra>")))
    fig.update_layout(
        yaxis3=dict(title="R2 · H股相对A股折价率（以A股为分母，%）",
                    overlaying="y", side="right", anchor="free",
                    position=1, autoshift=True, showgrid=False, zeroline=True),
        margin=dict(r=125))
    return fig
