"""One inventory for all fifteen plotted charts, including derived series."""
from datetime import datetime, timezone
import json
import math
from pathlib import Path

import pandas as pd

SOURCE_REPORT = Path(__file__).resolve().parents[1] / "data_snapshots/all_source_freshness.json"


def figure_rows(figures, now=None):
    try:
        from macro_platform.echarts_axes import option_observation_health
    except ImportError:
        option_observation_health = None
    rows = []
    for number in range(1, 16):
        figure = figures.get(number)
        if figure is None or not getattr(figure, "data", None):
            rows.append({"图表": number, "指标": "整图", "实际观测日": "缺失", "频率": "—", "状态": "待恢复"})
            continue
        for trace in figure.data:
            if str(trace.name) in {"Strong-side CU 7.75", "Linked Rate Center 7.80", "Weak-side CU 7.85"}:
                # Convertibility guide levels are annotations, not dated
                # source observations. Keep the inventory equal to the chart.
                continue
            dates = []
            xs, ys = getattr(trace, "x", None), getattr(trace, "y", None)
            for day, value in zip(xs if xs is not None else [], ys if ys is not None else []):
                try:
                    when = pd.Timestamp(day)
                    if pd.notna(when) and math.isfinite(float(value)):
                        dates.append(when)
                except (ValueError, TypeError, OverflowError):
                    continue
            if not dates:
                rows.append({"图表": number, "指标": trace.name, "实际观测日": "缺失", "频率": "—", "状态": "待恢复"})
                continue
            last = max(dates)
            monthly = number == 6 or (number == 5 and any(s in trace.name for s in ("M2 ", "Monetary Base")))
            weekly = "Reserve Balances" in trace.name or "Weekly fallback" in trace.name
            cadence = "monthly" if monthly else "weekly" if weekly else "daily"
            item = {"name": trace.name, "data": [[last.isoformat(), 1]], "observation_cadence": cadence}
            health = option_observation_health({"series": [item]}, now=now) if option_observation_health else {}
            status = ("时效适配器暂不可用" if not health else
                      "超出频率窗口" if health["stale_names"] else "在频率窗口内")
            if health.get("future_names"):
                status = "日期异常"
            rows.append({"图表": number, "指标": trace.name, "实际观测日": last.strftime("%Y-%m-%d"),
                         "频率": {"monthly": "月频", "weekly": "周频", "daily": "日频"}[cadence], "状态": status})
    return rows


def _local_time(value):
    try:
        when = pd.Timestamp(value)
        if when.tzinfo is None:
            when = when.tz_localize("UTC")
        return when.tz_convert("Asia/Shanghai").strftime("%Y-%m-%d %H:%M:%S GMT+8")
    except (ValueError, TypeError):
        return str(value or "未取得")


def source_rows(path=SOURCE_REPORT):
    try:
        report = json.loads(path.read_text())
    except (OSError, ValueError, TypeError):
        return None, []
    labels = {"at_source_latest": "与本次源站返回一致", "pipeline_lag": "本地落后源站",
              "source_behind_repository": "源站本次导出较旧，保留较新已验数据",
              "live_only": "页面实时构建，核对图表日期", "unverified": "源站尚未核实"}
    return _local_time(report.get("checked_at")), [{"源指标": row["id"], "图表": ",".join(map(str,row["charts"])),
        "本地数据日期": row.get("repository_latest") or "实时构建",
        "源站数据日期": row.get("source_latest") or "未取得", "核对结果": labels.get(row["status"],row["status"]),
        "本次核对时间": _local_time(row.get("checked_at")), "说明": row.get("error", "")}
        for row in report.get("sources", [])]


def render_freshness_overview(figures, *, quote_rows=None, news=None):
    import streamlit as st
    plotted = figure_rows(figures)
    with st.expander(f"数据最新时间 · 15 张图 / {len(plotted)} 条曲线", expanded=False):
        st.dataframe(pd.DataFrame(plotted)[["图表", "指标", "实际观测日"]],
                     hide_index=True, height=380, width="stretch")
        if quote_rows:
            st.markdown("**市场概览与自选报价**")
            st.dataframe(pd.DataFrame(quote_rows), hide_index=True, height=260, width="stretch")
        items = (news or {}).get("items") or []
        times = [str(item["time"]) for item in items if item.get("time")]
        if times:
            st.caption("最新快讯时间：" + times[0])
