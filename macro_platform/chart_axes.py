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

YEAR_BAND_SHAPE_NAME = "__dashboard_year_band__"


def _tick_profile(date_range: str) -> dict[str, Any]:
    """Readable lower-axis cadence for every supported viewport."""
    return {
        "5Y": {"dtick": "M6", "tickformat": "%m月"},
        "1Y": {"dtick": "M2", "tickformat": "%m月"},
        "6M": {"dtick": "M1", "tickformat": "%m月"},
        "3M": {"dtick": 14 * 24 * 60 * 60 * 1000, "tickformat": "%m-%d"},
        "1M": {"dtick": 5 * 24 * 60 * 60 * 1000, "tickformat": "%m-%d"},
    }.get(date_range, {"dtick": "M2", "tickformat": "%m月"})


def _tick0(start: pd.Timestamp, date_range: str) -> pd.Timestamp:
    if date_range in {"5Y", "1Y", "6M"}:
        return pd.Timestamp(year=start.year, month=1, day=1)
    return start.normalize()


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
        candidate = pd.Timestamp(parsed.max())
        if getattr(candidate, "tzinfo", None):
            candidate = candidate.tz_localize(None)
        if latest is None or candidate > latest:
            latest = candidate
    return latest


def _year_segments(start: pd.Timestamp, end: pd.Timestamp) -> list[tuple[int, pd.Timestamp, pd.Timestamp, pd.Timestamp]]:
    """Return visible calendar-year segments and centered label positions."""
    start = pd.Timestamp(start)
    end = pd.Timestamp(end)
    if getattr(start, "tzinfo", None):
        start = start.tz_localize(None)
    if getattr(end, "tzinfo", None):
        end = end.tz_localize(None)

    segments: list[tuple[int, pd.Timestamp, pd.Timestamp, pd.Timestamp]] = []
    for year in range(start.year, end.year + 1):
        year_start = pd.Timestamp(year=year, month=1, day=1)
        year_end = pd.Timestamp(year=year + 1, month=1, day=1)
        segment_start = max(start, year_start)
        segment_end = min(end, year_end)
        if segment_end <= segment_start:
            continue
        midpoint = segment_start + (segment_end - segment_start) / 2
        segments.append((year, segment_start, segment_end, midpoint))

    if not segments:
        midpoint = start + (end - start) / 2
        segments.append((end.year, start, end, midpoint))
    return segments


def _is_year_band_annotation(annotation: Any) -> bool:
    try:
        text = str(annotation.text or "")
        yref = str(annotation.yref or "")
        y = float(annotation.y)
    except Exception:
        return False
    return yref == "paper" and 1.0 <= y <= 1.12 and text.startswith("<b>") and text.endswith("</b>")


def _apply_year_band(fig: go.Figure, start: pd.Timestamp, end: pd.Timestamp) -> None:
    """Draw a persistent shaded year band above the plot area.

    A paper-coordinate band is more reliable in Streamlit/Plotly than an
    unused overlay x-axis. Each visible calendar year gets its own shaded cell
    and centered label, including a single-year 1M viewport.
    """
    existing_shapes = [
        shape
        for shape in (list(fig.layout.shapes) if fig.layout.shapes else [])
        if getattr(shape, "name", None) != YEAR_BAND_SHAPE_NAME
    ]
    existing_annotations = [
        ann
        for ann in (list(fig.layout.annotations) if fig.layout.annotations else [])
        if not _is_year_band_annotation(ann)
    ]

    year_shapes: list[dict[str, Any]] = []
    year_annotations: list[dict[str, Any]] = []
    for idx, (year, segment_start, segment_end, midpoint) in enumerate(_year_segments(start, end)):
        fill = "rgba(243,244,246,0.96)" if idx % 2 == 0 else "rgba(249,250,251,0.96)"
        year_shapes.append(
            dict(
                type="rect",
                xref="x",
                yref="paper",
                x0=segment_start,
                x1=segment_end,
                y0=1.015,
                y1=1.075,
                line=dict(color="#d1d5db", width=0.8),
                fillcolor=fill,
                layer="above",
                name=YEAR_BAND_SHAPE_NAME,
            )
        )
        year_annotations.append(
            dict(
                x=midpoint,
                y=1.045,
                xref="x",
                yref="paper",
                text=f"<b>{year}</b>",
                showarrow=False,
                xanchor="center",
                yanchor="middle",
                font=dict(size=11, color="#4b5563"),
                align="center",
            )
        )

    # Direct tuple assignment is intentional. Plotly's update_layout can merge
    # shape arrays by index, which leaves stale 5Y cells behind when switching
    # to 1M. Assignment replaces the old year-band cells completely while
    # preserving non-year shapes such as the 7.75–7.85 LERS hrect.
    fig.layout.shapes = tuple(existing_shapes + year_shapes)
    fig.layout.annotations = tuple(existing_annotations + year_annotations)


def apply_time_axis(
    fig: go.Figure,
    date_range: str,
    *,
    latest: pd.Timestamp | None = None,
) -> go.Figure:
    """Apply the dashboard-wide time axis.

    Bottom axis: adaptive month/day detail with bounded label density.
    Top: a shaded calendar-year band, centered within each visible year.
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
            tick0=_tick0(start, date_range),
            tickformat=profile["tickformat"],
            title=None,
            zeroline=False,
            minor=dict(showgrid=False, ticks="outside", ticklen=2),
        ),
        xaxis2=dict(
            visible=False,
            showgrid=False,
            showline=False,
            showticklabels=False,
            matches=None,
            overlaying=None,
            title=None,
        ),
    )
    _apply_year_band(fig, start, latest)
    return fig
