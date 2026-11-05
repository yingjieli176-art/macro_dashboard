"""Completed daily standing repo amounts, including every eligible collateral."""
from __future__ import annotations

from collections import defaultdict
import json
import math
from pathlib import Path

import pandas as pd

SNAPSHOT = Path(__file__).resolve().parents[1] / "data_snapshots/srf_usage_daily.json"
API_URL = "https://markets.newyorkfed.org/api/rp/results/search.json"
SOURCE_URL = "https://www.newyorkfed.org/markets/desk-operations/repo"
START = "2021-07-29"
TWICE_DAILY_START = "2025-06-26"
SECURITIES = {"Treasury": "treasury_usd", "Agency": "agency_usd", "Mortgage-Backed": "mbs_usd"}


def _amount(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("Missing accepted repo amount")
    amount = float(value)
    if not math.isfinite(amount) or amount < 0:
        raise ValueError("Invalid accepted repo amount")
    return amount


def parse_operations(payload, today=None):
    """Count distinct completed regular SRF operations, never RRP/SVE/term repo.

    Regular closing times identify the published standing operations. Unknown
    special schedules remain gaps, rather than being guessed or set to zero.
    A post-June-2025 daily total needs both AM and PM results, even when zero.
    """
    today = pd.Timestamp(today).date() if today is not None else pd.Timestamp.now(tz="America/New_York").date()
    days = defaultdict(dict)
    seen = {}
    for operation in payload.get("repo", {}).get("operations", []):
        if (operation.get("operationType") != "Repo" or operation.get("term") != "Overnight"
                or operation.get("auctionStatus") != "Results"):
            continue
        note = str(operation.get("note", "")).lower()
        if "small value" in note or "sve" in note or "readiness" in note:
            continue
        close = str(operation.get("closeTime", ""))
        if close not in {"08:30", "13:45"}:
            continue
        day = pd.Timestamp(operation["operationDate"])
        if pd.isna(day) or day.tzinfo is not None or day.date() > today or day.strftime("%Y-%m-%d") < START:
            raise ValueError("Invalid SRF operation date")
        day = day.strftime("%Y-%m-%d")
        if close == "08:30" and day < TWICE_DAILY_START:
            continue
        if operation.get("settlementDate") != day or operation.get("settlementType") != "Same Day":
            raise ValueError("Unexpected SRF settlement convention")
        identifier = str(operation.get("operationId") or "")
        if not identifier:
            raise ValueError("Missing SRF operation identity")
        amount = _amount(operation.get("totalAmtAccepted"))
        components = {}
        for detail in operation.get("details") or []:
            key = SECURITIES.get(detail.get("securityType"))
            if key is None or key in components:
                raise ValueError("Unexpected SRF collateral breakdown")
            components[key] = _amount(detail.get("amtAccepted"))
        if set(components) != set(SECURITIES.values()) or not math.isclose(sum(components.values()), amount, abs_tol=.01):
            raise ValueError("SRF total differs from accepted collateral amounts")
        fingerprint = (day, close, amount, tuple(sorted(components.items())))
        if identifier in seen:
            if seen[identifier] != fingerprint:
                raise ValueError("Conflicting duplicate SRF result")
            continue
        seen[identifier] = fingerprint
        if close in days[day]:
            raise ValueError("Ambiguous standing repo operation for one session")
        days[day][close] = dict(operation_id=identifier, accepted_usd=amount, **components)
    records, incomplete = [], []
    for day, sessions in sorted(days.items()):
        expected = {"08:30", "13:45"} if day >= TWICE_DAILY_START else {"13:45"}
        if set(sessions) != expected:
            incomplete.append(day)
            continue
        records.append(dict(observation_date=day,
            accepted_usd=sum(s["accepted_usd"] for s in sessions.values()),
            **{key: sum(s[key] for s in sessions.values()) for key in SECURITIES.values()},
            morning_accepted_usd=sessions.get("08:30", {}).get("accepted_usd"),
            afternoon_accepted_usd=sessions["13:45"]["accepted_usd"],
            operation_ids=[sessions[k]["operation_id"] for k in sorted(sessions)]))
    if not records:
        raise ValueError("No complete daily standing repo results")
    return dict(source="Federal Reserve Bank of New York", source_url=SOURCE_URL, api_url=API_URL,
        unit="USD", observation_cadence="daily", aggregation="Completed AM + PM regular standing repo accepted amounts, all three collateral types; excludes SVE, RRP and term repo",
        incomplete_dates=incomplete, records=records)


def load_srf_usage(path=SNAPSHOT):
    columns = ["observation_date", "SRF_USAGE_BN"]
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        rows = payload.get("records") or []
        if not rows:
            return pd.DataFrame(columns=columns)
        data = pd.DataFrame(rows)
        data["observation_date"] = pd.to_datetime(data["observation_date"], errors="coerce")
        data["SRF_USAGE_BN"] = pd.to_numeric(data["accepted_usd"], errors="coerce") / 1e9
        today = pd.Timestamp.now(tz="America/New_York").tz_localize(None).normalize()
        valid = (data.observation_date.notna() & data.observation_date.le(today)
                 & data.SRF_USAGE_BN.ge(0) & data.SRF_USAGE_BN.lt(float("inf")))
        return data.loc[valid, columns].sort_values("observation_date").drop_duplicates("observation_date", keep="last")
    except (OSError, KeyError, ValueError, TypeError):
        return pd.DataFrame(columns=columns)


def usage_caption():
    frame = load_srf_usage()
    if frame.empty:
        return "SRF用量暂无已核实的完整日数据；缺失不代表零用量。"
    row = frame.iloc[-1]
    return (f"SRF实际用量：{row.SRF_USAGE_BN:.3f} 十亿美元（{row.SRF_USAGE_BN * 1e9:,.0f}美元），"
            f"实际操作日 {row.observation_date:%Y-%m-%d}。日合计须当日各场结果齐全；零值表示已公布的实际零成交。")
