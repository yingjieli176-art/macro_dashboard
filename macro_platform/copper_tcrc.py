"""Dated spot concentrate charges, separate from positive copper prices/stocks."""
from __future__ import annotations

import json
import math
from pathlib import Path
from urllib.parse import urlsplit

import pandas as pd

SNAPSHOT_PATH = Path(__file__).resolve().parents[1] / "data_snapshots/copper_tcrc_weekly.json"
METHOD_URL = "https://mfs.mysteelcdn.com/group1/M00/18/2B/rBL64GI9YFqAKHS8AAZRnysuAGc193.pdf"
COLUMNS = ["observation_date", "tc_usd_dmt", "rc_cents_lb", "source_url"]


def validate_record(row, today=None):
    """Accept signed/zero charges; reject bad dates, units and mixed providers."""
    day = pd.Timestamp(row["observation_date"])
    today = pd.Timestamp(today) if today is not None else pd.Timestamp.now(tz="Asia/Shanghai").tz_localize(None)
    if pd.isna(day) or day.tzinfo is not None or day.normalize() > today.normalize():
        raise ValueError("Invalid TC observation date")
    tc, rc = float(row["tc_usd_dmt"]), float(row["rc_cents_lb"])
    if not all(math.isfinite(v) for v in (tc, rc)) or not math.isclose(rc, tc / 10, abs_tol=1e-6):
        raise ValueError("Invalid Mysteel TC/RC pair")
    url = str(row["source_url"])
    source = urlsplit(url)
    article = (source.hostname in {"youse.mysteel.com", "youse.m.mysteel.com"}
               and source.path.startswith("/a/"))
    bulletin = (source.hostname in {"list1.mysteel.com", "list1.m.mysteel.com"}
                and source.path.startswith("/zhishi/"))
    if source.scheme != "https" or not (article or bulletin):
        raise ValueError("Unverified TC publisher")
    return dict(observation_date=day.strftime("%Y-%m-%d"), tc_usd_dmt=tc,
                rc_cents_lb=rc, source_url=url)


def load_tcrc_snapshot():
    try:
        payload = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
        rows = []
        for row in payload.get("records", []):
            try:
                rows.append(validate_record(row))
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
        frame = pd.DataFrame(rows, columns=COLUMNS)
        frame["observation_date"] = pd.to_datetime(frame["observation_date"])
        return frame.sort_values("observation_date").drop_duplicates("observation_date", keep="last")
    except (OSError, ValueError, TypeError):
        return pd.DataFrame(columns=COLUMNS)


def latest_tcrc_rows():
    frame = load_tcrc_snapshot()
    if frame.empty:
        return []
    row = frame.iloc[-1]
    return [{"指标": name, "最新值": value, "单位": unit,
             "实际报价日": row.observation_date.strftime("%Y-%m-%d"), "口径": basis}
            for name, value, unit, basis in (
                ("TC 粗炼费", row.tc_usd_dmt, "美元/干吨", "Mysteel 进口干净铜精矿现货周指数"),
                ("RC 精炼费", row.rc_cents_lb, "美分/磅", "按 Mysteel 方法论：TC 数值 ÷ 10"))]


def tcrc_history_rows(months=6, now=None):
    """All verified dates in a rolling calendar window, without filled gaps."""
    end = pd.Timestamp(now) if now is not None else pd.Timestamp.now(tz="Asia/Shanghai")
    if end.tzinfo is not None:
        end = end.tz_convert("Asia/Shanghai").tz_localize(None)
    end = end.normalize()
    start = end - pd.DateOffset(months=months)
    frame = load_tcrc_snapshot()
    frame = frame.loc[frame.observation_date.between(start, end)].sort_values("observation_date", ascending=False)
    return [{"报价日期": row.observation_date.strftime("%Y-%m-%d"),
             "TC 粗炼费（美元/干吨）": row.tc_usd_dmt,
             "RC 精炼费（美分/磅，TC÷10）": row.rc_cents_lb,
             "来源": row.source_url} for row in frame.itertuples(index=False)]
