"""Plotly time-series adapter for Streamlit 1.64 native Apache ECharts.

ECharts dataZoom(filterMode='filter') removes observations outside the viewport
from axis extent calculations. yAxis.scale=True disables the zero baseline.
Together this gives native, fully client-side X/Y autoscaling even after an
arbitrary zoom-box selection, without a Streamlit rerun.
"""
from __future__ import annotations

import math

import pandas as pd

from macro_platform.chart_axes import RANGE_OFFSETS


def build_adaptive_echarts_option(fig, date_range="1Y"):
    """Convert a Plotly chart to a native ECharts time-series option object."""
    date_range = date_range if date_range in RANGE_OFFSETS else "1Y"
    series = []
    y_axis_map = {}
    original_axis_refs = {}
    latest = None

    for trace in fig.data:
        if getattr(trace, "visible", True) in (False, "legendonly"):
            continue
        xs, ys = getattr(trace, "x", None), getattr(trace, "y", None)
        if xs is None or ys is None:
            continue
        axis_ref = getattr(trace, "yaxis", None) or "y"
        if axis_ref not in y_axis_map:
            y_axis_map[axis_ref] = len(y_axis_map)
            original_axis_refs[axis_ref] = (
                "yaxis" if axis_ref == "y" else "yaxis" + axis_ref[1:]
            )
        points = []
        for x, y in zip(xs, ys):
            try:
                timestamp = pd.Timestamp(x)
                if pd.isna(timestamp):
                    continue
                if timestamp.tzinfo is not None:
                    timestamp = timestamp.tz_localize(None)
                timestamp_text = timestamp.isoformat()
                number = float(y)
                if not math.isfinite(number):
                    number = None
                else:
                    latest = timestamp if latest is None else max(latest, timestamp)
                points.append([timestamp_text, number])
            except (ValueError, TypeError, OverflowError):
                continue
        if not points:
            continue
        line = getattr(trace, "line", None)
        line_style = {"width": float(getattr(line, "width", None) or 2.3)}
        color = getattr(line, "color", None)
        if isinstance(color, str) and color:
            line_style["color"] = color
        dash = str(getattr(line, "dash", None) or "").lower()
        if dash in ("dash", "longdash", "dashdot", "longdashdot"):
            line_style["type"] = "dashed"
        elif dash == "dot":
            line_style["type"] = "dotted"
        series.append({
            "name": str(getattr(trace, "name", None) or "Series"),
            "type": "bar" if getattr(trace, "type", "") == "bar" else "line",
            "showSymbol": False,
            "connectNulls": False,
            "lineStyle": line_style,
            "yAxisIndex": y_axis_map[axis_ref],
            "data": points,
            "emphasis": {"focus": "series"},
            "animation": False,
        })

    if latest is None or not series:
        return None
    start = latest - RANGE_OFFSETS[date_range]
    axes = []
    for axis_ref, index in sorted(y_axis_map.items(), key=lambda pair: pair[1]):
        source_axis = getattr(fig.layout, original_axis_refs[axis_ref], None)
        old_range = getattr(source_axis, "range", None)
        reversed_range = (
            old_range is not None and len(old_range) == 2
            and old_range[0] is not None and old_range[1] is not None
            and float(old_range[0]) > float(old_range[1])
        )
        axes.append({
            "type": "value",
            "name": str(getattr(getattr(source_axis, "title", None), "text", None) or ""),
            "nameLocation": "middle",
            "nameGap": 42,
            "scale": True,
            "inverse": reversed_range,
            "position": "left" if index == 0 else "right",
            "offset": max(0, index - 1) * 58,
            "splitLine": {"show": index == 0, "lineStyle": {"color": "#edf1f5", "type": "dashed"}},
            "axisLine": {"show": True, "lineStyle": {"color": "#cbd5e1"}},
            "axisLabel": {"color": "#64748b"},
        })
    return {
        "animation": False,
        "legend": {
            "type": "scroll",
            "top": 31, "left": 12,
            "textStyle": {"color": "#475569", "fontSize": 11},
        },
        "grid": {
            "top": 96,
            "bottom": 75,
            "left": 73,
            "right": 43 + max(0, len(axes) - 1) * 66,
            "containLabel": False,
        },
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "cross"}},
        "toolbox": {
            "show": True, "right": 10, "top": 0,
            "feature": {
                "dataZoom": {"yAxisIndex": "none", "title": {"zoom": "框选缩放", "back": "返回上一步"}},
                "restore": {"title": "重置缩放"},
            },
        },
        "xAxis": {
            "type": "time",
            "scale": True,
            "axisLabel": {"color": "#64748b"},
            "splitLine": {"show": True, "lineStyle": {"color": "#f1f5f9", "type": "dashed"}},
        },
        "yAxis": axes,
        "dataZoom": [
            {
                "type": "inside",
                "xAxisIndex": [0],
                "filterMode": "filter",
                "startValue": start.isoformat(),
                "endValue": latest.isoformat(),
            },
            {
                "type": "slider",
                "show": True,
                "height": 22,
                "bottom": 16,
                "xAxisIndex": [0],
                "filterMode": "filter",
                "startValue": start.isoformat(),
                "endValue": latest.isoformat(),
            },
        ],
        "series": series,
    }


def summarize_series_dates(fig, *, now: pd.Timestamp | None = None,
                           maximum_age_days: int = 10) -> dict:
    """Report actual observation dates, not chart rendering/update timestamps.

    Never imply a last-good cached reading is fresh because it was loaded today.
    """
    now = pd.Timestamp.now(tz="UTC").tz_localize(None) if now is None else pd.Timestamp(now)
    if now.tzinfo is not None:
        now = now.tz_localize(None)
    now = now.normalize()
    latest_by_name = {}
    stale_names = []
    future_names = []
    for trace in fig.data:
        xs, ys = getattr(trace, "x", None), getattr(trace, "y", None)
        if xs is None or ys is None:
            continue
        latest = None
        for x, y in zip(xs, ys):
            try:
                value = float(y)
                if not math.isfinite(value):
                    continue
                timestamp = pd.Timestamp(x)
                if pd.isna(timestamp):
                    continue
                if timestamp.tzinfo is not None:
                    timestamp = timestamp.tz_localize(None)
                latest = timestamp if latest is None else max(latest, timestamp)
            except (ValueError, TypeError, OverflowError):
                continue
        if latest is None:
            continue
        name = str(getattr(trace, "name", None) or "Series")
        latest_by_name[name] = latest.strftime("%Y-%m-%d")
        age = (now - latest.normalize()).days
        if age > maximum_age_days:
            stale_names.append(name)
        if age < -1:
            future_names.append(name)
    return {
        "latest_by_name": latest_by_name,
        "stale_names": stale_names,
        "future_names": future_names,
    }
