"""Plotly time-series adapter for Streamlit 1.64 native Apache ECharts.

ECharts dataZoom(filterMode='filter') removes observations outside the viewport
from axis extent calculations. yAxis.scale=True disables the zero baseline.
Together this gives native, fully client-side X/Y autoscaling even after an
arbitrary zoom-box selection, without a Streamlit rerun.
"""
from __future__ import annotations

import math
from copy import deepcopy
import unicodedata

import pandas as pd

from macro_platform.chart_axes import RANGE_OFFSETS, _visible_y_ranges, _figure_latest



def _axis_unit(axis, traces):
    """Compact display-only unit from Plotly axis titles and hover values."""
    text = str(getattr(getattr(axis, "title", None), "text", None) or "").lower()
    for trace in traces:
        template = str(getattr(trace, "hovertemplate", None) or "")
        start = template.find("%{y")
        if start != -1:
            end = template.find("}", start)
            if end != -1:
                text += " " + template[end + 1:].split("<extra>", 1)[0].strip().lower()
    if "usd/hkd" in text:
        return "USD/HKD"
    if "hk$ bn" in text:
        return "HK$ bn"
    if "usd/oz" in text:
        return "USD/oz"
    if "usd/t" in text or "$/t" in text:
        return "USD/t"
    if "usd t" in text or text.endswith(" t"):
        return "USD tn"
    if "usd b" in text or text.endswith(" b"):
        return "USD bn"
    if " pp" in text or "(pp)" in text:
        return "pp"
    if "%" in text:
        return "%"
    if " pts" in text or "index" in text:
        return "pts"
    if " hkd" in text:
        return "HKD"
    if " usd" in text:
        return "USD"
    if " x" in text:
        return "×"
    return ""


def _axis_readable_title(source_axis, index, traces):
    title = str(getattr(getattr(source_axis, "title", None), "text", None) or "").strip()
    unit = _axis_unit(source_axis, traces)
    if index == 0:
        if title and len(title) <= 25:
            return title
        return "Left · " + (unit or "value")
    return f"R{index} · {unit or 'value'}"


def _responsive_chart_layout(option, fig, axis_map):
    """Keep every independent axis; compact only the narrow-container layout.

    Media options contain presentation only, so rotation cannot reset zoom,
    replace observations, or merge axes. The final default restores desktop
    geometry when a phone rotates or a browser window grows again.
    """
    desktop = {key: deepcopy(option[key]) for key in ("legend", "grid", "yAxis", "xAxis")}
    for axis in desktop["yAxis"]:
        axis["nameRotate"] = 90
        axis.setdefault("nameTextStyle", {}).update({"lineHeight": 12, "align": "center"})
        axis["nameTextStyle"].setdefault("fontSize", 12)
        axis.setdefault("axisLabel", {}).setdefault("fontSize", 12)
        axis["axisLabel"].setdefault("margin", 8)
        axis.setdefault("splitNumber", 5)
    if "toolbox" in option:
        desktop["toolbox"] = deepcopy(option["toolbox"])

    units = []
    for ref, index in sorted(axis_map.items(), key=lambda pair: pair[1]):
        source = getattr(fig.layout, "yaxis" if ref == "y" else "yaxis" + ref[1:], None)
        traces = [trace for trace in fig.data if (getattr(trace, "yaxis", None) or "y") == ref]
        unit = _axis_unit(source, traces)
        if not unit:
            # Keep compact source units the older desktop title helper does
            # not recognize (for example copper inventories in kt).
            title = str(getattr(getattr(source, "title", None), "text", None) or "")
            suffix = title.rsplit(" · ", 1)[-1].strip()
            unit = suffix if suffix and len(suffix) <= 12 else "value"
        units.append(unit)

    media = []
    # Estimate legend rows conservatively at each band's lower width. Explicit
    # row breaks keep the plain legend complete without a pagination control.
    for maximum, usable, spacing, label_size in (
        (700, 456, 48, 10),
        (480, 336, 44, 10),
        (360, 236, 40, 9),
    ):
        names, used, rows = [], 0, 1
        for series in option["series"]:
            name = series["name"]
            if name in names:
                continue
            width = 30 + sum(10 if unicodedata.east_asian_width(char) in "WF" else 6.2 for char in name)
            if used and used + width > usable:
                names.append("\n")
                rows += 1
                used = 0
            names.append(name)
            used += width
        axes = deepcopy(option["yAxis"])
        for index, axis in enumerate(axes):
            axis.update({
                "show": True,
                "name": f"{'L' if index == 0 else 'R' + str(index)}\n{units[index]}",
                "nameLocation": "end", "nameRotate": 0, "nameGap": 10,
                "nameTextStyle": {"fontSize": 9, "lineHeight": 12,
                                  "align": "center", "color": "#475569"},
                "offset": max(0, index - 1) * spacing,
                "splitNumber": 3,
                "axisLabel": {"color": "#475569", "fontSize": label_size,
                              "hideOverlap": True, "margin": 4},
            })
        override = {
            "legend": {"type": "plain", "top": 26, "left": 4, "right": 4,
                       "data": names, "itemWidth": 14, "itemHeight": 8,
                       "itemGap": 8, "textStyle": {"fontSize": 10, "lineHeight": 14}},
            "grid": {"left": 42, "right": 38 + max(0, len(axes) - 2) * spacing,
                     "top": 26 + rows * 22 + 40, "bottom": 58, "containLabel": False},
            "yAxis": axes,
            "xAxis": {"splitNumber": 3, "axisLabel": {"margin": 8, "fontSize": 9}},
        }
        if "toolbox" in option:
            override["toolbox"] = {"right": 4, "top": 0, "itemSize": 13}
        media.append({"query": {"maxWidth": maximum}, "option": override})
    # Reset every property introduced by a media override, including the
    # legend's explicit row breaks and toolbox icon size.
    desktop["legend"].update({"data": [series["name"] for series in option["series"]],
                              "right": "auto", "itemWidth": 25, "itemHeight": 14,
                              "itemGap": 10})
    desktop["legend"].setdefault("textStyle", {})["lineHeight"] = 14
    desktop["legend"]["textStyle"].setdefault("fontSize", 12)
    desktop["xAxis"].setdefault("axisLabel", {}).setdefault("fontSize", 12)
    desktop["xAxis"]["axisLabel"].setdefault("margin", 8)
    desktop["xAxis"].setdefault("splitNumber", 5)
    if "toolbox" in desktop:
        desktop["toolbox"]["itemSize"] = 15
    media.append({"option": desktop})
    option["media"] = media
    return option



def build_safe_echarts_option(fig, date_range="1Y"):
    """Minimal native ECharts rescue path, independent of the rich adapter.

    All valid observations retain their *actual dates* and numerical values;
    unsupported Plotly decorations are omitted. The browser still filters X
    samples before independently auto-fitting each Y axis. Never fabricate
    or interpolate a missing observation in the process.
    """
    date_range = date_range if date_range in RANGE_OFFSETS else "1Y"
    series, axis_map = [], {}
    latest = None
    for trace in fig.data:
        if getattr(trace, "visible", True) in (False, "legendonly"):
            continue
        xs, ys = getattr(trace, "x", None), getattr(trace, "y", None)
        if xs is None or ys is None:
            continue
        ref = getattr(trace, "yaxis", None) or "y"
        points = []
        for x, y in zip(xs, ys):
            try:
                when = pd.Timestamp(x)
                if pd.isna(when):
                    continue
                if when.tzinfo is not None:
                    when = when.tz_localize(None)
            except (TypeError, ValueError, OverflowError):
                continue
            try:
                value = float(y)
                if not math.isfinite(value):
                    value = None
                else:
                    # Display-only rounding avoids e.g. 3.429999999999998
                    # in native ECharts hover panels. Original market
                    # observations stay unchanged in Plotly/source files.
                    value = round(value, 8)
            except (TypeError, ValueError, OverflowError):
                value = None
            # Keep the original date and a null gap even if this source did
            # not report a value. Skipping points shifts sparse chart series
            # and would silently fabricate a continuous line.
            points.append([when.isoformat(), value])
            if value is not None:
                latest = when if latest is None else max(latest, when)
        if not any(value is not None for _, value in points):
            continue
        if ref not in axis_map:
            axis_map[ref] = len(axis_map)
        series.append({
            "name": str(getattr(trace, "name", None) or "Series"),
            "type": "line",
            "showSymbol": False,
            "connectNulls": False,
            "data": points,
            "yAxisIndex": axis_map[ref],
            "animation": False,
        })
    if latest is None or not series:
        return None
    axes = []
    for ref, index in axis_map.items():
        source = getattr(fig.layout, "yaxis" if ref == "y" else "yaxis" + ref[1:], None)
        prior = getattr(source, "range", None)
        inverse = False
        if prior is not None and len(prior) == 2:
            try:
                inverse = float(prior[0]) > float(prior[1])
            except (ValueError, TypeError):
                pass
        axes.append({
            "type": "value", "scale": True, "inverse": inverse,
            "position": "left" if index == 0 else "right",
            "offset": max(index - 1, 0) * 55,
            "name": _axis_readable_title(source, index, [
                trace for trace in fig.data
                if (getattr(trace, "yaxis", None) or "y") == ref
            ]),
            "nameLocation": "middle", "nameGap": 42,
            "splitLine": {"show": index == 0},
        })
    window_start = (latest - RANGE_OFFSETS[date_range]).isoformat()
    return _responsive_chart_layout({
        "animation": False,
        "legend": {"type": "scroll", "top": 14},
        "grid": {
            "left": 80, "right": 55 + max(0, len(axes)-1)*70,
            "top": 68, "bottom": 72,
        },
        "tooltip": {"trigger": "axis"},
        "xAxis": {
            "type": "time",
            # Plain ECharts string template: no JavaScript functions/objects.
            "axisLabel": {
                "hideOverlap": True,
                "formatter": "{MM}-{dd}" if date_range in ("1M", "3M") else "{yyyy}-{MM}",
            },
        },
        "yAxis": axes,
        "dataZoom": [
            {"type": "inside", "xAxisIndex": 0, "filterMode": "filter",
             "startValue": window_start, "endValue": latest.isoformat()},
            {"type": "slider", "show": True, "height": 22, "bottom": 12,
             "xAxisIndex": 0, "filterMode": "filter",
             "startValue": window_start, "endValue": latest.isoformat()},
        ],
        "series": series,
    }, fig, axis_map)



def build_adaptive_echarts_option(fig, date_range="1Y"):
    """Convert a Plotly chart to a native ECharts time-series option object."""
    date_range = date_range if date_range in RANGE_OFFSETS else "1Y"
    series = []
    y_axis_map = {}
    original_axis_refs = {}
    latest = None
    # The HKD convertibility guide lines are chart annotations, not
    # observations. Keeping them as data would pin the Y axis near 7.75-7.85.
    reference_names = {
        "Strong-side CU 7.75",
        "Linked Rate Center 7.80",
        "Weak-side CU 7.85",
    }
    reference_lines = []

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
                    number = round(number, 8)
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
        trace_name = str(getattr(trace, "name", None) or "Series")
        finite_values = [value for _, value in points if value is not None]
        if (
            axis_ref == "y" and trace_name in reference_names
            and finite_values
            and all(abs(value - finite_values[0]) < 1e-10 for value in finite_values)
        ):
            reference_lines.append({
                "name": trace_name,
                "yAxis": finite_values[0],
                "lineStyle": line_style,
                "label": {"show": False},
            })
            continue
        series.append({
            "name": trace_name,
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

    primary_series = next((item for item in series if item["yAxisIndex"] == y_axis_map.get("y")), None)
    if primary_series is not None and reference_lines:
        primary_series["markLine"] = {
            "silent": True,
            "symbol": ["none", "none"],
            "data": reference_lines,
        }

    # Preserve HKD linked-exchange-rate bands as annotations, rather than
    # inserting synthetic points that would prevent viewport Y autoscaling.
    mark_areas = []
    for shape in fig.layout.shapes or []:
        if getattr(shape, "type", None) != "rect" or str(getattr(shape, "yref", "")) not in ("y", "y1"):
            continue
        xref = str(getattr(shape, "xref", "") or "")
        if xref not in ("paper", "x domain", "x"):
            continue
        try:
            lower = float(shape.y0)
            upper = float(shape.y1)
            if not (math.isfinite(lower) and math.isfinite(upper)):
                continue
            # Only translate horizontal bands covering the full X domain.
            if float(shape.x0) != 0.0 or float(shape.x1) != 1.0:
                continue
        except (TypeError, ValueError, OverflowError):
            continue
        mark_areas.append([
            {"yAxis": min(lower, upper),
             "itemStyle": {"color": str(shape.fillcolor or "rgba(148,163,184,0.08)")}},
            {"yAxis": max(lower, upper)},
        ])
    if primary_series is not None and mark_areas:
        primary_series["markArea"] = {
            "silent": True,
            "label": {"show": False},
            "data": mark_areas,
        }
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
        traces_on_axis = [
            trace for trace in fig.data
            if (getattr(trace, "yaxis", None) or "y") == axis_ref
            and getattr(trace, "visible", True) not in (False, "legendonly")
        ]
        axes.append({
            "type": "value",
            "name": _axis_readable_title(source_axis, index, traces_on_axis),
            "nameLocation": "middle",
            "nameGap": 52 if index == 0 else 45,
            "nameTextStyle": {"fontSize": 10, "color": "#475569"},
            "scale": True,
            "splitNumber": 5,
            "boundaryGap": ["7%", "7%"],
            "inverse": reversed_range,
            "position": "left" if index == 0 else "right",
            "offset": max(0, index - 1) * 58,
            "splitLine": {"show": index == 0, "lineStyle": {"color": "#edf1f5", "type": "dashed"}},
            "axisLine": {"show": True, "lineStyle": {"color": "#cbd5e1"}},
            "axisLabel": {
                "color": "#475569", "fontSize": 10,
                "hideOverlap": True, "margin": 8,
            },
        })
    return _responsive_chart_layout({
        "animation": False,
        "legend": {
            "type": "scroll",
            "top": 31, "left": 12,
            "textStyle": {"color": "#475569", "fontSize": 11},
        },
        "grid": {
            "top": 96,
            "bottom": 75,
            "left": 81,
            "right": 50 + max(0, len(axes) - 1) * 70,
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
            "axisLabel": {
                "color": "#475569", "fontSize": 10,
                "hideOverlap": True, "margin": 10,
                # ECharts defaults to '2026' at January and 'Sep' elsewhere;
                # use explicit calendar labels so year/month never disappear.
                # Compact day ticks remain distinguishable in 1M/3M views.
                # All templates are JSON-compatible (no JavaScript callbacks).
                "formatter": {
                    "year": "{yyyy}-01",
                    "month": "{yyyy}-{MM}",
                    "day": "{MM}-{dd}",
                    "hour": "{MM}-{dd} {HH}:{mm}",
                    "minute": "{HH}:{mm}",
                    "second": "{HH}:{mm}:{ss}",
                },
            },
            "splitNumber": 6,
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
    }, fig, y_axis_map)



def option_observation_health(option, *, chart_key="", now=None):
    """Expose the *plotted* last observation, not the snapshot download date.

    This inspects already-serialized ECharts series. A monthly observation is
    allowed a longer lag than a daily market close; no data is extrapolated.
    """
    now = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize() if now is None else pd.Timestamp(now)
    if now.tzinfo is not None:
        now = now.tz_localize(None)
    now = now.normalize()
    latest_by_name = {}
    stale_names = []
    future_names = []
    stale_details = []
    monthly_names = []
    monthly_chart = chart_key in ("hk_5_range", "hk_6_range")
    for series in option.get("series", []):
        name = str(series.get("name", "Series"))
        observations = series.get("data", [])
        # Each point is [ISO date, numeric value]; keep the actual last
        # finite observation date even when the selected viewport is shorter.
        valid_dates = []
        for point in observations:
            if not isinstance(point, (list, tuple)) or len(point) != 2:
                continue
            try:
                when = pd.Timestamp(point[0])
                if pd.notna(when) and math.isfinite(float(point[1])):
                    valid_dates.append(when.tz_localize(None) if when.tzinfo else when)
            except (ValueError, TypeError, OverflowError):
                continue
        if not valid_dates:
            continue
        latest = max(valid_dates)
        latest_by_name[name] = latest.strftime("%Y-%m-%d")
        age = (now - latest.normalize()).days
        monthly = monthly_chart and (
            chart_key == "hk_6_range" or any(
                key in name for key in ("M2 ", "M3 ", "Monetary Base", "Money Growth")
            )
        )
        # Monthly monetary data is normally published at the end of the
        # following month. Wait until the next publication cycle plus one
        # week before declaring the previous observation overdue.
        # Daily feeds get seven weekdays of grace (not an exchange calendar).
        due = (latest.normalize() + pd.offsets.MonthEnd(2) + pd.Timedelta(days=7)
               if monthly else latest.normalize() + pd.offsets.BDay(7))
        if monthly:
            monthly_names.append(name)
        if now > due:
            stale_names.append(name)
            stale_details.append(f"{name}（截至 {latest:%Y-%m-%d}，距今 {age} 天，{'月频' if monthly else '日/周频'}）")
        if age < -1:
            future_names.append(name)
    return {
        "latest_by_name": latest_by_name,
        "stale_names": stale_names,
        "future_names": future_names,
        "stale_details": stale_details,
        "monthly_names": monthly_names,
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


def expected_viewport_y_bounds(fig, date_range="1Y") -> dict[str, list[float]]:
    """Audit the initial viewport independently of client chart rendering.

    This does not force ECharts Y limits; keeping ECharts limits automatic is
    required for them to change after drag/slider zoom interactions.
    """
    latest = _figure_latest(fig)
    if latest is None or pd.isna(latest):
        return {}
    window = date_range if date_range in RANGE_OFFSETS else "1Y"
    start = latest - RANGE_OFFSETS[window]
    return _visible_y_ranges(fig, start, latest)
