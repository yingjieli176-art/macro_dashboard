"""Public five-year CDS aggregates and source-identified NVIDIA 1Y quotes."""
from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from macro_platform.chart_axes import RANGE_OFFSETS, apply_time_axis
from macro_platform.nvidia_cds import load_nvidia_cds

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "data_snapshots/ai_cds_daily.json"
SOURCE_URL = "https://irates.today/chart_data.json"
METHOD_URL = "https://irates.today/capex.html#method"
ATTRIBUTION = "Open-Sourced Rates Observatory, irates.today"
NVIDIA_1Y_NAME = "NVIDIA 1Y"
HY_OAS_NAME = "HY OAS (R1)"
HY_OAS_URL = "https://fred.stlouisfed.org/series/BAMLH0A0HYM2"
IG_OAS_NAME = "IG OAS (R2)"
IG_OAS_URL = "https://fred.stlouisfed.org/series/BAMLC0A0CM"
SERIES = {
    "sn_nvidia": ("NVIDIA 5Y", "#16a34a"),
    "sn_amd": ("AMD 5Y", "#785db0"),
    "sn_alphabet": ("Alphabet 5Y（谷歌）", "#0891b2"),
    "sn_microsoft": ("Microsoft 5Y（微软）", "#d97706"),
    "sn_oracle": ("Oracle 5Y", "#5070dd"),
}


def checked_day(value, today=None):
    if not isinstance(value, str):
        raise ValueError("An ISO observation date is required")
    day = date.fromisoformat(value)
    if day.isoformat() != value or day > (today or date.today()):
        raise ValueError("Invalid/future observation date")
    return value


def parse_source(payload, today=None):
    """Whitelist bp CDS series and retain nulls on their original calendar."""
    if not isinstance(payload, dict):
        raise ValueError("Invalid CDS source document")
    built = checked_day(payload.get("built"), today)
    days = [checked_day(day, today) for day in payload.get("dates", [])]
    if not days or days != sorted(set(days)) or days[-1] > built:
        raise ValueError("CDS source calendar is missing, duplicate or unsorted")
    catalogue = {entry["id"]: entry for entry in payload.get("catalogue", [])}
    nodes = {}
    for key, (label, _) in SERIES.items():
        entry = catalogue.get(key, {})
        values = payload.get("series", {}).get(key)
        # IDs alone do not establish the measure or units.
        expected = "5y CDS"
        if entry.get("unit") != "bp" or expected not in entry.get("label", ""):
            raise ValueError("Missing/wrong CDS spread descriptor: " + key)
        if not isinstance(values, list) or len(values) != len(days):
            raise ValueError("Truncated CDS calendar: " + key)
        records = []
        for day, value in zip(days, values):
            if value is not None:
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                    raise ValueError("Invalid CDS bp observation: " + key)
                value = float(value)
            records.append({"observation_date": day, "spread_bps": value})
        if not any(row["spread_bps"] is not None for row in records):
            raise ValueError("No priced observations: " + key)
        nodes[key] = {"label": label, "source_label": entry["label"], "unit": "bp", "tenor": "5Y",
                      "quote_basis": "source_aggregate",
                      "records": records}
    return {"schema_version": 1, "built": built, "source_asof": days[-1],
            "source_calendar_count": len(days),
            "source": ATTRIBUTION, "source_url": SOURCE_URL, "methodology_url": METHOD_URL,
            "methodology": "Daily SEC SBS traded-spread medians; five-year bucket 4.4–5.6 years. "
                           "Five selected corporate reference entities only. No bid/ask or real-time closing quotes.",
            "series": nodes}


def load_cds_snapshot(path=None):
    try:
        payload = json.loads(Path(path or SNAPSHOT).read_text(encoding="utf-8"))
        if payload.get("source_url") != SOURCE_URL or payload.get("source") != ATTRIBUTION:
            raise ValueError("Unknown CDS snapshot source")
        checked_day(payload["built"])
        checked_day(payload["source_asof"])
        nodes = payload["series"]
        if not isinstance(nodes, dict) or not nodes:
            raise ValueError("Missing CDS series")
        for key, node in nodes.items():
            if key not in SERIES:
                continue  # Ignore retired names during migration, then persist only the selected five.
            if node.get("unit") != "bp" or node.get("tenor") != "5Y":
                raise ValueError("Wrong CDS measure")
            days = []
            for row in node["records"]:
                day = checked_day(row["observation_date"])
                if day > payload["source_asof"]:
                    raise ValueError("Observation beyond source calendar")
                days.append(day)
                value = row["spread_bps"]
                if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                          or not math.isfinite(value) or value < 0):
                    raise ValueError("Invalid CDS spread")
            if days != sorted(set(days)):
                raise ValueError("Duplicate/unsorted CDS observations")
        payload["series"] = {key: nodes[key] for key in SERIES if key in nodes}
        return payload
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def load_nvidia_1y():
    quotes = load_nvidia_cds()
    return quotes.loc[quotes.tenor.eq("1Y")]


def cds_summary(payload=None, *, nvidia_1y=None):
    payload = load_cds_snapshot() if payload is None else payload
    nvidia_1y = load_nvidia_1y() if nvidia_1y is None else nvidia_1y
    rows = []
    for key, (label, _) in SERIES.items():
        node = payload.get("series", {}).get(key, {})
        points = [row for row in node.get("records", []) if row.get("spread_bps") is not None]
        last = points[-1] if points else {}
        first = points[0] if points else {}
        calendar = payload.get("source_calendar_count") or max(
            (len(n.get("records", [])) for n in payload.get("series", {}).values()), default=0)
        lag = ((date.fromisoformat(payload["source_asof"]) - date.fromisoformat(last["observation_date"])).days
               if last and payload.get("source_asof") else None)
        status = ("公开源未提供5Y CDS" if node.get("availability") == "not_published" else
                  "未取得可计价观测" if not points else
                  "最新观测落后源截止日" if lag else "与源截止日一致")
        rows.append({"公司 / 指数": label, "最新CDS（bp）": last.get("spread_bps"),
                     "实际观测日": last.get("observation_date", "缺失"), "观测数": len(points),
                     "首个观测日": first.get("observation_date", "缺失"),
                     "源日历天数": calendar,
                     "源日历覆盖率（%）": round(len(points) / calendar * 100, 1) if calendar else None,
                     "距源截止日（天）": lag, "数据状态": status,
                     "口径": "日度成交汇总" if points else "暂无可计价CDS观测"})
    latest = nvidia_1y.iloc[-1] if not nvidia_1y.empty else None
    rows.append({
        "公司 / 指数": NVIDIA_1Y_NAME,
        "最新CDS（bp）": latest.spread_bps if latest is not None else None,
        "实际观测日": latest.observation_date.date().isoformat() if latest is not None else "缺失",
        "观测数": len(nvidia_1y),
        "首个观测日": nvidia_1y.observation_date.iloc[0].date().isoformat() if latest is not None else "缺失",
        "数据状态": "最新已导入报价" if latest is not None else "暂无 1Y 报价",
        "口径": "美元优先无担保 CDS 平价利差",
    })
    return pd.DataFrame(rows)


def build_cds_figure(date_range="5Y", payload=None, *, hy_oas=None, ig_oas=None, nvidia_1y=None):
    payload = load_cds_snapshot() if payload is None else payload
    nvidia_1y = load_nvidia_1y() if nvidia_1y is None else nvidia_1y
    fig = go.Figure()
    missing = []
    asof = payload.get("source_asof")
    cutoff = pd.Timestamp(asof) - RANGE_OFFSETS.get(date_range, RANGE_OFFSETS["1Y"]) if asof else None
    for key, (label, color) in SERIES.items():
        records = payload.get("series", {}).get(key, {}).get("records", [])
        records = [r for r in records if cutoff is None or pd.Timestamp(r["observation_date"]) >= cutoff]
        if not any(row["spread_bps"] is not None for row in records):
            missing.append(label)
            continue
        fig.add_trace(go.Scatter(x=[r["observation_date"] for r in records],
            y=[r["spread_bps"] if r["spread_bps"] is not None else float("nan") for r in records], mode="lines+markers", name=label,
            line=dict(color=color, width=2.1, dash="solid"),
            marker=dict(size=3.5), connectgaps=False,
            hovertemplate=label + ": %{y:.2f} bp<extra></extra>"))
    if nvidia_1y.empty:
        missing.append(NVIDIA_1Y_NAME)
    else:
        start = nvidia_1y.observation_date.max() - RANGE_OFFSETS.get(date_range, RANGE_OFFSETS["1Y"])
        view = nvidia_1y.loc[nvidia_1y.observation_date.ge(start)]
        fig.add_trace(go.Scatter(
            x=view.observation_date, y=view.spread_bps, mode="lines+markers", name=NVIDIA_1Y_NAME,
            line=dict(color="#0f766e", width=2.2, dash="dash"), marker=dict(size=3.5),
            connectgaps=False, hovertemplate=NVIDIA_1Y_NAME + ": %{y:.2f} bp<extra></extra>",
        ))
    oas_axes = []
    for oas, name, color, label, axis in (
        (hy_oas, HY_OAS_NAME, "#be123c", "HY OAS", 1),
        (ig_oas, IG_OAS_NAME, "#0369a1", "IG OAS", 2),
    ):
        if oas is None:
            continue
        if oas.empty:
            missing.append(name)
        else:
            start = oas.observation_date.max() - RANGE_OFFSETS.get(date_range, RANGE_OFFSETS["1Y"])
            view = oas.loc[oas.observation_date.ge(start)]
            fig.add_trace(go.Scatter(
                x=view.observation_date, y=view.oas_pct, mode="lines", name=name,
                yaxis=f"y{axis+1}", line=dict(color=color, width=2.4, dash="dash"),
                connectgaps=False, hovertemplate=label + ": %{y:.2f}%<extra></extra>",
            ))
            oas_axes.append(f"y{axis+1}")
            fig.update_layout(**{f"yaxis{axis+1}": dict(title=f"R{axis} · %", overlaying="y",
                side="right", anchor="free", position=.88 if axis == 1 else 1, showgrid=False)})
            fig.update_layout(xaxis_domain=[0, .8], margin_r=140)
    fig.update_layout(height=460, yaxis_title="CDS spread · bp", hovermode="x unified",
        paper_bgcolor="white", plot_bgcolor="white", meta={"missing_series": missing,
        "source_asof": asof, "attribution": ATTRIBUTION, "show_observation_markers": True,
        "preserve_axis_titles": oas_axes})
    return apply_time_axis(fig, date_range) if fig.data else fig
