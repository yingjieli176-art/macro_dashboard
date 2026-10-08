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


CLIENT_RANGE_ORDER = ("5Y", "1Y", "6M", "3M", "1M")


def _native_range_buttons() -> list[dict[str, Any]]:
    """Plotly built-in date-axis range selector buttons."""
    # En-spaces make Plotly's native selector buttons breathe a little without
    # replacing the stable browser-native range-selector interaction.
    pad = "\u2002"
    return [
        dict(count=5, label=f"{pad}5Y{pad}", step="year", stepmode="backward"),
        dict(count=1, label=f"{pad}1Y{pad}", step="year", stepmode="backward"),
        dict(count=6, label=f"{pad}6M{pad}", step="month", stepmode="backward"),
        dict(count=3, label=f"{pad}3M{pad}", step="month", stepmode="backward"),
        dict(count=1, label=f"{pad}1M{pad}", step="month", stepmode="backward"),
    ]


def _remove_year_band_for_client_controls(fig: go.Figure) -> None:
    """Remove the static top year strip when the viewport changes client-side."""
    fig.layout.shapes = tuple(
        shape
        for shape in (list(fig.layout.shapes) if fig.layout.shapes else [])
        if getattr(shape, "name", None)
        not in {YEAR_BAND_SHAPE_NAME, YEAR_DIVIDER_SHAPE_NAME}
    )
    fig.layout.annotations = tuple(
        ann
        for ann in (list(fig.layout.annotations) if fig.layout.annotations else [])
        if not _is_year_band_annotation(ann)
    )


DASHBOARD_CHART_HEIGHT = 420
DASHBOARD_MARGIN_LEFT = 62
DASHBOARD_MARGIN_BOTTOM = 38
DASHBOARD_MARGIN_TOP = 88


def _visible_right_axis_count(fig: go.Figure) -> int:
    """Count visible overlay Y axes placed on the right side."""
    count = 0
    for axis_name in ("yaxis2", "yaxis3", "yaxis4", "yaxis5"):
        axis = getattr(fig.layout, axis_name, None)
        if axis is None:
            continue
        if getattr(axis, "visible", True) is False:
            continue
        if getattr(axis, "overlaying", None) is None:
            continue
        side = getattr(axis, "side", "right")
        if side == "right":
            count += 1
    return count


def _right_margin_for_axes(fig: go.Figure) -> int:
    count = _visible_right_axis_count(fig)
    return {0: 34, 1: 70, 2: 98, 3: 124}.get(count, 136)


def apply_dashboard_chart_standard(fig: go.Figure) -> go.Figure:
    """Final visual standard shared by every Macro Chart.

    Figure builders own only data, traces and axis semantics. This function owns
    the visual system: dimensions, margins, legend, typography, grid and axis
    chrome. Calling it last prevents module-specific layout drift.
    """
    fig.update_layout(
        height=DASHBOARD_CHART_HEIGHT,
        template="plotly_white",
        hovermode="x unified",
        dragmode=False,
        margin=dict(
            l=DASHBOARD_MARGIN_LEFT,
            r=_right_margin_for_axes(fig),
            t=DASHBOARD_MARGIN_TOP,
            b=DASHBOARD_MARGIN_BOTTOM,
            pad=1,
        ),
        font=dict(
            family="Inter, Segoe UI, Microsoft JhengHei, PingFang TC, sans-serif",
            size=11,
            color="#475569",
        ),
        hoverlabel=dict(
            bgcolor="#ffffff",
            bordercolor="#dbe3ec",
            font_size=11,
            font_family="Inter, Segoe UI, Microsoft JhengHei, PingFang TC, sans-serif",
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.012,
            xanchor="left",
            x=0.0,
            font=dict(size=10, color="#334155"),
            bgcolor="rgba(255,255,255,0)",
            borderwidth=0,
            itemwidth=30,
            traceorder="normal",
        ),
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
    )

    fig.update_xaxes(
        showgrid=True,
        gridcolor="#edf1f5",
        griddash="dot",
        showline=True,
        linecolor="#cbd5e1",
        linewidth=1,
        ticks="outside",
        ticklen=3,
        tickcolor="#94a3b8",
        tickfont=dict(size=10, color="#64748b"),
        ticklabelstandoff=5,
        automargin=False,
        zeroline=False,
    )

    primary = fig.layout.yaxis
    primary.update(
        showgrid=True,
        gridcolor="#e7edf3",
        griddash="dot",
        showline=True,
        linecolor="#cbd5e1",
        linewidth=1,
        ticks="outside",
        ticklen=3,
        tickcolor="#94a3b8",
        tickfont=dict(size=10, color="#64748b"),
        automargin=False,
        fixedrange=True,
        zeroline=False,
    )
    if primary.title is not None:
        primary.title.font = dict(size=11, color="#64748b")
        primary.title.standoff = 8

    for axis_name in ("yaxis2", "yaxis3", "yaxis4", "yaxis5"):
        axis = getattr(fig.layout, axis_name, None)
        if axis is None:
            continue
        axis.update(
            showgrid=False,
            showline=False,
            ticks="outside",
            ticklen=3,
            tickcolor="#94a3b8",
            tickfont=dict(size=9, color="#64748b"),
            automargin=False,
            fixedrange=True,
        )
        if axis.title is not None:
            axis.title.font = dict(size=10, color="#64748b")
            axis.title.standoff = 6

    return fig


def _visible_y_ranges(fig: go.Figure, start: pd.Timestamp, end: pd.Timestamp) -> dict[str, list[float]]:
    """Scale each Y axis independently using ONLY observations in the X viewport."""
    import math

    grouped: dict[str, list[float]] = {}
    for trace in fig.data:
        if getattr(trace, "visible", True) in (False, "legendonly"):
            continue
        xs, ys = getattr(trace, "x", None), getattr(trace, "y", None)
        if xs is None or ys is None:
            continue
        axis_ref = getattr(trace, "yaxis", None) or "y"
        axis_name = "yaxis" if axis_ref == "y" else "yaxis" + axis_ref[1:]
        for x, y in zip(xs, ys):
            try:
                stamp = pd.Timestamp(x)
                if stamp.tzinfo is not None:
                    stamp = stamp.tz_localize(None)
                value = float(y)
                if start <= stamp <= end and math.isfinite(value):
                    grouped.setdefault(axis_name, []).append(value)
            except (TypeError, ValueError, OverflowError):
                continue

    result = {}
    for name, values in grouped.items():
        low, high = min(values), max(values)
        span = high - low
        # A flat series gets a small symmetric range; never fabricate movement.
        padding = span * 0.09 if span > 0 else max(abs(low) * 0.01, 0.001)
        axis = getattr(fig.layout, name, None)
        if getattr(axis, "type", None) == "log":
            if low <= 0:
                continue
            import math
            result[name] = [math.log10(max(low - padding, low * 0.8)), math.log10(high + padding)]
        else:
            result[name] = [low - padding, high + padding]
    return result


def apply_client_time_controls(
    fig: go.Figure,
    *,
    default_range: str = "1Y",
    latest: pd.Timestamp | None = None,
) -> go.Figure:
    """Client-side time buttons update X and every visible Y axis together.

    Native Plotly rangeselector adjusts only X; its automatic Y range is
    calculated against the full trace, not the selected viewport. Relayout
    buttons explicitly update both dimensions without a Streamlit rerun.
    Users can also pan/zoom Y independently (fixedrange=False).
    """
    latest = pd.Timestamp(latest) if latest is not None else _figure_latest(fig)
    if latest is None or pd.isna(latest):
        return fig
    if latest.tzinfo is not None:
        latest = latest.tz_localize(None)

    fig = apply_time_axis(fig, "5Y", latest=latest)
    _remove_year_band_for_client_controls(fig)
    fig = apply_dashboard_chart_standard(fig)
    default_range = default_range if default_range in RANGE_OFFSETS else "1Y"

    buttons = []
    for label in CLIENT_RANGE_ORDER:
        start = latest - RANGE_OFFSETS[label]
        updates: dict[str, Any] = {
            "xaxis.range": [start.isoformat(), _axis_end_with_padding(start, latest).isoformat()],
            "xaxis.autorange": False,
        }
        for axis_name, bounds in _visible_y_ranges(fig, start, latest).items():
            updates[f"{axis_name}.range"] = bounds
            updates[f"{axis_name}.autorange"] = False
        buttons.append(dict(label=label, method="relayout", args=[updates]))

    selected_start = latest - RANGE_OFFSETS[default_range]
    selected_ranges = _visible_y_ranges(fig, selected_start, latest)
    for axis_name, bounds in selected_ranges.items():
        axis = getattr(fig.layout, axis_name, None)
        if axis is not None:
            axis.update(range=bounds, autorange=False, rangemode="normal")
    for axis_name in ("yaxis", "yaxis2", "yaxis3", "yaxis4", "yaxis5"):
        axis = getattr(fig.layout, axis_name, None)
        if axis is not None:
            axis.fixedrange = False

    fig.update_layout(
        updatemenus=[dict(
            type="buttons", direction="right", showactive=True,
            active=CLIENT_RANGE_ORDER.index(default_range),
            buttons=buttons, x=0, xanchor="left", y=1.22, yanchor="top",
            bgcolor="rgba(248,250,252,0.96)",
            bordercolor="#cbd5e1",
            font=dict(size=11, color="#475569"),
        )],
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="left", x=0, font=dict(size=10, color="#334155")),
    )
    fig.update_xaxes(
        type="date",
        range=[selected_start, _axis_end_with_padding(selected_start, latest)],
        autorange=False, fixedrange=False, tickmode="auto",
        tickvals=None, ticktext=None, dtick=None, tickformat=None,
        nticks=8, hoverformat="%Y-%m-%d", rangeslider_visible=False,
        rangeselector=dict(visible=False),
    )
    return fig


def apply_selected_x_viewport(fig: go.Figure, box: dict[str, Any]) -> go.Figure:
    """Zoom into a Streamlit Plotly box selection, recalculating visible Y ranges."""
    try:
        coords = box.get("x", [])
        if len(coords) != 2:
            return fig
        start, end = sorted(pd.Timestamp(v) for v in coords)
        if start.tzinfo is not None:
            start = start.tz_localize(None)
        if end.tzinfo is not None:
            end = end.tz_localize(None)
        if pd.isna(start) or pd.isna(end) or start == end:
            return fig
    except (TypeError, ValueError, OverflowError):
        return fig
    fig.update_xaxes(range=[start, end], autorange=False)
    # For axes with no observations in the selection, leave their previous
    # ranges intact rather than showing a misleading synthetic scale.
    for axis_name, bounds in _visible_y_ranges(fig, start, end).items():
        axis = getattr(fig.layout, axis_name, None)
        if axis is not None:
            axis.update(range=bounds, autorange=False, fixedrange=False, rangemode="normal")
    return fig


def apply_server_time_window(
    fig: go.Figure, date_range: str, *, latest: pd.Timestamp | None = None
) -> go.Figure:
    """Reliable server-rendered X/Y bounds, independent of Plotly button state."""
    latest = pd.Timestamp(latest) if latest is not None else _figure_latest(fig)
    if latest is None or pd.isna(latest):
        return fig
    if latest.tzinfo is not None:
        latest = latest.tz_localize(None)
    date_range = date_range if date_range in RANGE_OFFSETS else "1Y"
    start = latest - RANGE_OFFSETS[date_range]
    fig = apply_time_axis(fig, date_range, latest=latest)
    _remove_year_band_for_client_controls(fig)
    fig = apply_dashboard_chart_standard(fig)
    fig.update_layout(updatemenus=[], dragmode="select", selectdirection="h",
                      uirevision=None)
    fig.update_xaxes(range=[start, _axis_end_with_padding(start, latest)],
                     autorange=False, fixedrange=False, tickmode="auto",
                     tickvals=None, ticktext=None, dtick=None, tickformat=None,
                     rangeslider_visible=False)
    for name, bounds in _visible_y_ranges(fig, start, latest).items():
        axis = getattr(fig.layout, name, None)
        if axis is not None:
            axis.update(range=bounds, autorange=False, fixedrange=False,
                        rangemode="normal")
    return fig
