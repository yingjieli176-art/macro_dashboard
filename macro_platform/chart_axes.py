from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go


RANGE_OFFSETS = {
    "5Y": pd.DateOffset(years=5),
    "1Y": pd.DateOffset(years=1),
    "6M": pd.DateOffset(months=6),
    "3M": pd.DateOffset(months=3),
    "1M": pd.DateOffset(months=1),
}


def _tick_profile(date_range: str) -> dict[str, Any]:
    """Return a readable lower-axis cadence for every supported viewport.

    The lower axis carries month/day detail while the upper axis carries years.
    Cadences are intentionally bounded to roughly 6-10 visible labels so wide
    and narrow Streamlit layouts remain legible without losing useful density.
    """
    return {
        "5Y": {"dtick": "M6", "tickformat": "%m月"},
        "1Y": {"dtick": "M2", "tickformat": "%m月"},
        "6M": {"dtick": "M1", "tickformat": "%m月"},
        "3M": {"dtick": 14 * 24 * 60 * 60 * 1000, "tickformat": "%m-%d"},
        "1M": {"dtick": 5 * 24 * 60 * 60 * 1000, "tickformat": "%m-%d"},
    }.get(date_range, {"dtick": "M2", "tickformat": "%m月"})


def _figure_latest(fig: go.Figure) -> pd.Timestamp | None:
    latest: pd.Timestamp | None = None
    for trace in fig.data:
        values = getattr(trace, "x", None)
        if values is None:
            continue
        parsed = pd.to_datetime(list(values), errors="coerce")
        parsed = parsed[~pd.isna(parsed)]
        if not len(parsed):
            continue
        candidate = pd.Timestamp(parsed.max()).tz_localize(None) if getattr(parsed.max(), "tzinfo", None) else pd.Timestamp(parsed.max())
        if latest is None or candidate > latest:
            latest = candidate
    return latest


def _year_ticks(start: pd.Timestamp, end: pd.Timestamp) -> tuple[list[pd.Timestamp], list[str]]:
    """Center one year label inside each visible calendar-year segment."""
    start = pd.Timestamp(start).tz_localize(None) if getattr(start, "tzinfo", None) else pd.Timestamp(start)
    end = pd.Timestamp(end).tz_localize(None) if getattr(end, "tzinfo", None) else pd.Timestamp(end)
    ticks: list[pd.Timestamp] = []
    labels: list[str] = []
    for year in range(start.year, end.year + 1):
        year_start = pd.Timestamp(year=year, month=1, day=1)
        year_end = pd.Timestamp(year=year + 1, month=1, day=1) - pd.Timedelta(milliseconds=1)
        segment_start = max(start, year_start)
        segment_end = min(end, year_end)
        if segment_end < segment_start:
            continue
        midpoint = segment_start + (segment_end - segment_start) / 2
        ticks.append(midpoint)
        labels.append(str(year))
    if not ticks:
        ticks = [start + (end - start) / 2]
        labels = [str(end.year)]
    return ticks, labels


def apply_time_axis(
    fig: go.Figure,
    date_range: str,
    *,
    latest: pd.Timestamp | None = None,
) -> go.Figure:
    """Apply the dashboard-wide two-level time axis.

    Bottom axis: adaptive month/day detail with a fixed readable cadence.
    Top axis: centered calendar-year labels for the visible range.
    """
    latest = pd.Timestamp(latest) if latest is not None else _figure_latest(fig)
    if latest is None or pd.isna(latest):
        return fig
    if getattr(latest, "tzinfo", None):
        latest = latest.tz_localize(None)

    offset = RANGE_OFFSETS.get(date_range, RANGE_OFFSETS["1Y"])
    start = latest - offset
    if start >= latest:
        start = latest - pd.Timedelta(days=1)

    profile = _tick_profile(date_range)
    year_tickvals, year_ticktext = _year_ticks(start, latest)

    fig.update_layout(
        xaxis=dict(
            type="date",
            range=[start, latest],
            showgrid=True,
            gridcolor="#eef2f7",
            griddash="dot",
            showline=True,
            linecolor="#9ca3af",
            linewidth=1,
            ticks="outside",
            ticklen=4,
            tickcolor="#9ca3af",
            tickangle=0,
            tickfont=dict(size=10, color="#4b5563"),
            ticklabelstandoff=6,
            ticklabeloverflow="hide past div",
            automargin=True,
            fixedrange=True,
            dtick=profile["dtick"],
            tickformat=profile["tickformat"],
            title=None,
            zeroline=False,
            minor=dict(showgrid=False, ticks="outside", ticklen=2),
        ),
        xaxis2=dict(
            type="date",
            overlaying="x",
            matches="x",
            anchor="free",
            side="top",
            position=1.0,
            range=[start, latest],
            showgrid=False,
            showline=True,
            linecolor="#d1d5db",
            linewidth=1,
            ticks="",
            tickvals=year_tickvals,
            ticktext=year_ticktext,
            tickfont=dict(size=11, color="#6b7280"),
            ticklabelstandoff=7,
            automargin=True,
            fixedrange=True,
            title=None,
            zeroline=False,
        ),
    )
    return fig
