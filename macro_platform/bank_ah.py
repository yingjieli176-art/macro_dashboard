"""Currency-adjusted bank A/H premiums, using same-date raw daily closes."""
import json
from pathlib import Path
import pandas as pd
import plotly.graph_objects as go

SNAPSHOT = Path(__file__).resolve().parents[1] / "data_snapshots/bank_ah_daily.json"
BANKS = {"ABC": ("农业银行", "601288.SS", "1288.HK", "#08916c"),
         "ICBC": ("工商银行", "601398.SS", "1398.HK", "#1677cc"),
         "CCB": ("建设银行", "601939.SS", "0939.HK", "#bd226b")}


def calculate_premium(a, h, fx):
    # No forward fills: both exchanges and the FX observation must share a date.
    frame = a.rename(columns={"close": "a_cny"}).merge(
        h.rename(columns={"close": "h_hkd"}), on="observation_date", how="inner").merge(
        fx.rename(columns={"close": "cny_per_hkd"}), on="observation_date", how="inner")
    frame = frame.dropna().sort_values("observation_date").drop_duplicates("observation_date")
    frame = frame.loc[(frame[["a_cny", "h_hkd", "cny_per_hkd"]] > 0).all(axis=1)].copy()
    frame["premium_pct"] = (frame.a_cny / (frame.h_hkd * frame.cny_per_hkd) - 1) * 100
    return frame


def add_bank_premiums(fig, date_range="5Y"):
    from macro_platform.chart_axes import RANGE_OFFSETS
    try:
        payload = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fig
    for key, (name, _, _, color) in BANKS.items():
        frame = pd.DataFrame(payload.get("series", {}).get(key, {}).get("records", []))
        if frame.empty:
            continue
        frame["observation_date"] = pd.to_datetime(frame.observation_date, errors="coerce")
        frame = frame.dropna(subset=["observation_date", "premium_pct"])
        today = pd.Timestamp.now(tz="Asia/Hong_Kong").tz_localize(None).normalize()
        frame = frame.loc[frame.observation_date.le(today)]
        if date_range in RANGE_OFFSETS and not frame.empty:
            frame = frame.loc[frame.observation_date >= frame.observation_date.max() - RANGE_OFFSETS[date_range]]
        fig.add_trace(go.Scatter(x=frame.observation_date, y=frame.premium_pct,
            name=f"{name} AH溢价率（R2）", yaxis="y3", mode="lines",
            line=dict(color=color, width=2), connectgaps=False,
            hovertemplate="%{x|%Y-%m-%d}<br>AH溢价率：%{y:.2f}%<extra></extra>"))
    fig.update_layout(yaxis3=dict(title="R2 · AH溢价率 (%)", overlaying="y", side="right",
        anchor="free", position=1, autoshift=True, showgrid=False, zeroline=True),
        margin=dict(r=125))
    return fig
