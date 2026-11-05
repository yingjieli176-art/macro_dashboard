"""Public, attributed five-year CDS aggregates; never equity swap prices/coupons."""
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
SERIES = {
    "sn_oracle": ("Oracle 5Y", "#5070dd"),
    "sn_intel": ("Intel 5Y", "#b45309"),
    "sn_amd": ("AMD 5Y", "#785db0"),
    "sn_nvidia": ("NVIDIA 5Y", "#16a34a"),
    "sn_alphabet": ("Alphabet 5Y（谷歌）", "#0891b2"),
    "sn_nebius": ("Nebius 5Y（NBIS）", "#be185d"),
    "sn_coreweave": ("CoreWeave 5Y*", "#dc2626"),
    "cdx_ig5": ("CDX IG 5Y · 指数", "#64748b"),
}
OPTIONAL_SERIES = {"sn_alphabet", "sn_nebius"}


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
        if key in OPTIONAL_SERIES and not entry and values is None:
            nodes[key] = {"label": label, "unit": "bp", "tenor": "5Y",
                          "quote_basis": "unavailable", "availability": "not_published",
                          "records": []}
            continue
        # IDs alone do not establish the measure or units.
        expected = "CDX IG 5y" if key == "cdx_ig5" else "5y CDS"
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
        if key not in OPTIONAL_SERIES and not any(row["spread_bps"] is not None for row in records):
            raise ValueError("No priced observations: " + key)
        nodes[key] = {"label": label, "source_label": entry["label"], "unit": "bp", "tenor": "5Y",
                      "quote_basis": "upfront_implied" if key == "sn_coreweave" else "source_aggregate",
                      "records": records}
    return {"schema_version": 1, "built": built, "source_asof": days[-1],
            "source_calendar_count": len(days),
            "source": ATTRIBUTION, "source_url": SOURCE_URL, "methodology_url": METHOD_URL,
            "methodology": "Daily SEC SBS traded-spread medians; five-year bucket 4.4–5.6 years. "
                           "CoreWeave*: source upfront-implied running spread, flat hazard, 40% recovery. "
                           "CDX IG: CFTC index tape. No bid/ask or real-time closing quotes.",
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
            if key not in SERIES or node.get("unit") != "bp" or node.get("tenor") != "5Y":
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
        return payload
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def cds_summary(payload=None):
    payload = load_cds_snapshot() if payload is None else payload
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
                     "口径": "预付款推算*" if key == "sn_coreweave" else
                             "信用指数" if key == "cdx_ig5" else
                             "暂无公开CDS，未用股价替代" if not points else "日度成交汇总"})
    return pd.DataFrame(rows)


def build_cds_figure(date_range="5Y", payload=None):
    payload = load_cds_snapshot() if payload is None else payload
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
            line=dict(color=color, width=2.1, dash="dash" if key in {"sn_coreweave", "cdx_ig5"} else "solid"),
            marker=dict(size=3.5), connectgaps=False,
            hovertemplate=label + ": %{y:.2f} bp<extra></extra>"))
    # Preserve the separately verified NVIDIA 1Y path; never infer it from 5Y.
    nvidia = load_nvidia_cds()
    one_year = nvidia.loc[nvidia.tenor.eq("1Y")]
    if not one_year.empty:
        fig.add_trace(go.Scatter(x=one_year.observation_date, y=one_year.spread_bps,
            mode="lines+markers", name="NVIDIA 1Y · 授权报价", line=dict(color="#0284c7", dash="dot"),
            connectgaps=False, hovertemplate="NVIDIA 1Y: %{y:.2f} bp<extra></extra>"))
    else:
        missing.append("NVIDIA 1Y · 待数据源")
    fig.update_layout(height=460, yaxis_title="CDS spread · bp", hovermode="x unified",
        paper_bgcolor="white", plot_bgcolor="white", meta={"missing_series": missing,
        "source_asof": asof, "attribution": ATTRIBUTION, "show_observation_markers": True})
    return apply_time_axis(fig, date_range) if fig.data else fig
