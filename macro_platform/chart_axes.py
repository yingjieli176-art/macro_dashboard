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
YEAR_DIVIDER_SHAPE_NAME = "__dashboard_year_divider__"


def _tick_profile(date_range: str) -> dict[str, Any]:
    """Readable lower-axis cadence for every supported viewport."""
    return {
        "5Y": {"dtick": "M12", "tickformat": "%Y"},
        "1Y": {"dtick": "M2", "tickformat": "%m月"},
        "6M": {"dtick": "M1", "tickformat": "%m月"},
        "3M": {"dtick": 14 * 24 * 60 * 60 * 1000, "tickformat": "%m-%d"},
        "1M": {"dtick": 5 * 24 * 60 * 60 * 1000, "tickformat": "%m-%d"},
    }.get(date_range, {"dtick": "M2", "tickformat": "%m月"})


def _axis_ticks(
    start: pd.Timestamp,
    end: pd.Timestamp,
    date_range: str,
) -> list[pd.Timestamp]:
    """Build deterministic labels so Plotly never appends a crowded range-end tick."""
    start = pd.Timestamp(start)
    end = pd.Timestamp(end)

    if date_range == "5Y":
        ticks = pd.date_range(start=start, end=end, freq="YS")
    elif date_range == "1Y":
        ticks = pd.date_range(start=start, end=end, freq="2MS")
    elif date_range == "6M":
        ticks = pd.date_range(start=start, end=end, freq="MS")
    elif date_range == "3M":
        ticks = pd.date_range(start=start.normalize(), end=end, freq="14D")
    elif date_range == "1M":
        ticks = pd.date_range(start=start.normalize(), end=end, freq="5D")
    else:
        ticks = pd.date_range(start=start, end=end, freq="2MS")

    return [pd.Timestamp(value) for value in ticks if start <= value <= end]


def _axis_end_with_padding(start: pd.Timestamp, latest: pd.Timestamp) -> pd.Timestamp:
    """Leave a small right gutter so the final regular tick is not pinned to the frame."""
    span = latest - start
    if span <= pd.Timedelta(0):
        return latest
    padding = max(pd.Timedelta(days=1), span * 0.015)
    padding = min(padding, pd.Timedelta(days=7))
    return latest + padding


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
    """Draw a soft year band plus vertical cross-year separators.

    The shaded band is deliberately subtle so it reads as a temporal guide,
    not another data layer. Every Jan-01 boundary inside the visible window
    gets a light dotted vertical divider through the plot area.
    """
    existing_shapes = [
        shape
        for shape in (list(fig.layout.shapes) if fig.layout.shapes else [])
        if getattr(shape, "name", None)
        not in {YEAR_BAND_SHAPE_NAME, YEAR_DIVIDER_SHAPE_NAME}
    ]
    existing_annotations = [
        ann
        for ann in (list(fig.layout.annotations) if fig.layout.annotations else [])
        if not _is_year_band_annotation(ann)
    ]

    year_shapes: list[dict[str, Any]] = []
    year_dividers: list[dict[str, Any]] = []
    year_annotations: list[dict[str, Any]] = []
    segments = _year_segments(start, end)

    for idx, (year, segment_start, segment_end, midpoint) in enumerate(segments):
        fill = (
            "rgba(243,244,246,0.34)"
            if idx % 2 == 0
            else "rgba(248,250,252,0.24)"
        )
        year_shapes.append(
            dict(
                type="rect",
                xref="x",
                yref="paper",
                x0=segment_start,
                x1=segment_end,
                y0=1.018,
                y1=1.066,
                line=dict(color="rgba(0,0,0,0)", width=0),
                fillcolor=fill,
                layer="above",
                name=YEAR_BAND_SHAPE_NAME,
            )
        )
        year_annotations.append(
            dict(
                x=midpoint,
                y=1.042,
                xref="x",
                yref="paper",
                text=f"<b>{year}</b>",
                showarrow=False,
                xanchor="center",
                yanchor="middle",
                font=dict(size=11, color="#6b7280"),
                align="center",
            )
        )

        # A segment after the first starts exactly at a cross-year boundary.
        # Draw the separator only through the data area so it stays visually
        # subordinate to the year label strip above the plot.
        if idx > 0:
            year_dividers.append(
                dict(
                    type="line",
                    xref="x",
                    yref="paper",
                    x0=segment_start,
                    x1=segment_start,
                    y0=0.0,
                    y1=1.0,
                    line=dict(
                        color="rgba(107,114,128,0.38)",
                        width=1,
                        dash="dot",
                    ),
                    layer="below",
                    name=YEAR_DIVIDER_SHAPE_NAME,
                )
            )

    # Direct tuple assignment is intentional. Plotly's update_layout can merge
    # shape arrays by index, which leaves stale cells/dividers behind after a
    # range change. Assignment fully replaces the temporal guides while
    # preserving unrelated shapes such as the 7.75–7.85 LERS hrect.
    fig.layout.shapes = tuple(existing_shapes + year_shapes + year_dividers)
    fig.layout.annotations = tuple(existing_annotations + year_annotations)


def apply_time_axis(
    fig: go.Figure,
    date_range: str,
    *,
    latest: pd.Timestamp | None = None,
) -> go.Figure:
    """Apply the dashboard-wide time axis.

    Bottom axis: deterministic adaptive labels with bounded density and no
    synthetic latest-date label. Top: a subtle shaded calendar-year band
    centered within each visible year, with dotted cross-year separators.
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
    tickvals = _axis_ticks(start, latest, date_range)
    ticktext = [tick.strftime(profile["tickformat"]) for tick in tickvals]
    axis_end = _axis_end_with_padding(start, latest)

    fig.update_layout(
        xaxis=dict(
            type="date",
            range=[start, axis_end],
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
            tickmode="array",
            tickvals=tickvals,
            ticktext=ticktext,
            dtick=profile["dtick"],
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
