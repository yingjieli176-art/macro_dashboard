"""Audit individual observations offline; a fresh download cannot hide old data."""
from __future__ import annotations

import argparse
import json
import math
import pandas as pd
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from macro_platform.echarts_axes import option_observation_health
from pandas.tseries.holiday import USFederalHolidayCalendar


def federal_publication_health(health, now=None):
    """Use federal business days only for Treasury/NY Fed daily publications.

    This remains an offline cadence warning, never proof of source freshness.
    Equity, Cboe and non-US calendars are deliberately unaffected.
    """
    today = pd.Timestamp.now(tz="America/New_York") if now is None else pd.Timestamp(now)
    if today.tzinfo is not None:
        today = today.tz_convert("America/New_York").tz_localize(None)
    today = today.normalize()
    business_day = pd.offsets.CustomBusinessDay(calendar=USFederalHolidayCalendar())
    for name, observed in health["latest_by_name"].items():
        due = pd.Timestamp(observed) + 2 * business_day
        health["due_by_name"][name] = due.strftime("%Y-%m-%d")
        if today <= due and name in health["stale_names"]:
            health["stale_names"].remove(name)
            health["stale_details"] = [s for s in health["stale_details"] if not s.startswith(name + "（")]
    return health


SPECS = [
    ("move_daily.json", "observation_date", "", ["close"]),
    ("spx_gex_daily.json", "observation_date", "", ["gex_usd"]),
    ("jpy_3m_atm_saxo.json", "observation_date", "", ["value"]),
    ("jpy_1m_25d_rr_saxo.json", "observation_date", "", ["value"]),
    ("jpy_implied_qcam_monthly.json", "observation_date", "", ["value"]),
    ("srf_usage_daily.json", "observation_date", "", ["accepted_usd"]),
    ("cftc_jpy_weekly.json", "observation_date", "", ["noncommercial_long", "noncommercial_short", "net_contracts"]),
    ("japan_gov_yields.json", "observation_date", "", ["japan_2y", "japan_10y", "japan_30y"]),
    ("jpy_market_daily.json", "date", "", ["usd_jpy_close"]),
    ("jpy_neer_daily.json", "date", "", ["value"]),
    ("censtat_hkd_money_supply.json", "end_of_month", "hk_6_range", ["m2_hkd", "m3_hkd"]),
    ("copper_market_daily.json", "date", "", ["comex_stock_t", "lme_stock_t", "comex_price_usd_lb", "lme_3m_usd_t", "wti_usd_bbl", "vvix"]),
    ("copper_tcrc_weekly.json", "observation_date", "", ["tc_usd_dmt", "rc_cents_lb"]),
    ("usdhkd_daily.json", "observation_date", "", ["value"]),
    ("vixeq_daily.json", "observation_date", "", ["close"]),
    ("skew_daily.json", "observation_date", "", ["close"]),
    ("vvix_daily.json", "observation_date", "", ["close"]),
    ("vix9d_daily.json", "observation_date", "", ["close"]),
    ("dspx_daily.json", "observation_date", "", ["close"]),
    ("spx_put_call_daily.json", "observation_date", "", ["ratio"]),
    ("cor1m_daily.json", "observation_date", "", ["close"]),
    ("cor3m_daily.json", "observation_date", "", ["close"]),
    ("hkma_monetary_statistics.json", "end_of_month", "hk_6_range",
     ["m2_hkd", "m3_hkd", "monetary_base_total", "aggr_balance", "outstanding_efbn", "ow_lb_bf_disc_win"]),
    ("hkma_banking_liquidity_daily.json", "end_of_date", "", ["hibor_overnight", "hibor_1m", "hibor_3m", "disc_win_base_rate", "closing_balance"]),
]


def read_payload(path):
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def attach_live_source_evidence(reports, evidence, now=None):
    """Distinguish upstream silence from pipeline lag without hiding old dates.

    Only a recent, successful LIVE comparison of the same saved observation
    qualifies. Snapshot fallbacks and mismatched/stale reports cannot excuse it.
    """
    current = pd.Timestamp.now(tz='UTC') if now is None else pd.Timestamp(now)
    current = current.tz_localize('UTC') if current.tzinfo is None else current.tz_convert('UTC')
    try:
        checked = pd.Timestamp(evidence['checked_at'])
        if checked.tzinfo is None or not pd.Timedelta(0) <= current - checked <= pd.Timedelta(minutes=90):
            return reports
    except (KeyError, ValueError, TypeError):
        return reports
    ids = {row.get('id'): row for row in evidence.get('sources', [])}
    aliases = {
        ('ai_cds_daily.json', 'NVIDIA 5Y'): 'NVIDIA_CDS_5Y',
        ('ai_cds_daily.json', 'AMD 5Y'): 'SN_AMD_CDS_5Y',
        ('ai_cds_daily.json', 'Alphabet 5Y（谷歌）'): 'SN_ALPHABET_CDS_5Y',
        ('ai_cds_daily.json', 'Microsoft 5Y（微软）'): 'SN_MICROSOFT_CDS_5Y',
        ('ai_cds_daily.json', 'Oracle 5Y（甲骨文）'): 'SN_ORACLE_CDS_5Y',
        ('ai_cds_daily.json', 'Broadcom 5Y（博通）'): 'SN_BROADCOM_CDS_5Y',
        ('ai_cds_daily.json', 'CoreWeave 5Y（预付款推算）'): 'SN_COREWEAVE_CDS_5Y',
        ('jpy_1m_25d_rr_saxo.json', 'value'): 'USDJPY_1M_25D_RR_SAXO',
        ('jpy_implied_qcam_monthly.json', 'value'): 'USDJPY_3M_IV_QCAM',
        **{('cftc_jpy_weekly.json', field): 'CFTC_JPY_NONCOMM_NET'
           for field in ('noncommercial_long', 'noncommercial_short', 'net_contracts')},
    }
    for report in reports:
        confirmed = {}
        for name in report['stale_names']:
            row = ids.get(aliases.get((report['file'], name), name), {})
            observed = report['latest_by_name'].get(name)
            try:
                row_checked = pd.Timestamp(row['checked_at'])
                if row_checked.tzinfo is None or not pd.Timedelta(0) <= current - row_checked <= pd.Timedelta(minutes=90):
                    continue
            except (KeyError, ValueError, TypeError):
                continue
            if (row.get('status') == 'at_source_latest' and row.get('verification_method') == 'live'
                    and row.get('repository_latest') == observed == row.get('source_latest')):
                confirmed[name] = {'observation_date': observed, 'verified_at': row_checked.isoformat(),
                                   'source_url': row.get('source_url')}
        report['upstream_delayed'] = confirmed
    return reports


def raw_record_issues(payload, now=None):
    """Catch malformed/interior rows that a max-date-only check would omit."""
    today = pd.Timestamp.now(tz="Asia/Hong_Kong") if now is None else pd.Timestamp(now)
    today = today.tz_localize(None).normalize() if today.tzinfo else today.normalize()
    issues = {"invalid_date_rows": 0, "future_date_rows": 0,
              "duplicate_date_rows": 0, "invalid_value_cells": 0}
    nodes = list((payload.get("series") or {}).values()) if payload.get("series") else [payload]
    numeric = {"value", "close", "spread_bps", "japan_2y", "japan_10y", "close_today_bal", "open_today_bal"}
    numeric.update(field for _, _, _, fields in SPECS for field in fields)
    for node in nodes:
        seen = set()
        for row in node.get("records") or []:
            key = next((key for key in ("observation_date", "date", "end_of_date", "end_of_month", "record_date") if key in row), None)
            try:
                date = pd.Timestamp(row.get(key))
                if pd.isna(date):
                    raise ValueError("missing date")
                if key == "end_of_month":
                    date += pd.offsets.MonthEnd(0)
                if date.tzinfo:
                    date = date.tz_localize(None)
                issues["future_date_rows"] += int(date.normalize() > today)
                # DTS publishes multiple account rows per date. Only repeated
                # dates for the same account are duplicate source records.
                identity = (date, str(row['account_type'])) if key == 'record_date' and 'account_type' in row else date
                issues["duplicate_date_rows"] += int(identity in seen)
                seen.add(identity)
            except (ValueError, TypeError, OverflowError):
                issues["invalid_date_rows"] += 1
            for key in numeric.intersection(row):
                value = row[key]
                if value in (None, "", ".", "null"):
                    continue
                try:
                    if not math.isfinite(float(value)):
                        raise ValueError("nonfinite")
                except (ValueError, TypeError, OverflowError):
                    issues["invalid_value_cells"] += 1
    return issues


def audit(root=ROOT, now=None):
    reports = []
    for filename, date_key, cadence, fields in SPECS:
        payload = read_payload(root / "data_snapshots" / filename)
        rows = payload.get("records") or []
        series = []
        for field in fields:
            points = []
            for row in rows:
                date = str(row.get(date_key) or "")
                if len(date) == 7:
                    import pandas as pd
                    date = (pd.Timestamp(date + "-01") + pd.offsets.MonthEnd(0)).strftime("%Y-%m-%d")
                points.append([date, row.get(field)])
            series.append({"name": field, "data": points,
                           "observation_cadence": "monthly" if filename == 'jpy_implied_qcam_monthly.json' else
                           "weekly" if filename in {"jpy_neer_daily.json", "cftc_jpy_weekly.json", "copper_tcrc_weekly.json"} else "daily"})
        if filename == 'jpy_implied_qcam_monthly.json' and rows:
            series[0].update(publication_schedule='qcam_monthly', publication_month=rows[-1].get('issue_month', ''))
        health = option_observation_health({"series": series}, chart_key=cadence, now=now)
        missing = [field for field in fields if field not in health["latest_by_name"]]
        reports.append({"file": filename, **health, "missing_names": missing})
    from macro_platform.ai_credit import SERIES as CDS_SERIES, nvidia_issuer_reference
    cds = read_payload(root / "data_snapshots" / "ai_cds_daily.json")
    cds_series = [{"name": label, "data": [[row.get("observation_date"), row.get("spread_bps")]
        for row in cds.get("series", {}).get(key, {}).get("records", [])]}
        for key, (label, _) in CDS_SERIES.items()]
    if reference := nvidia_issuer_reference(cds):
        nvidia = next(item for item in cds_series if item["name"] == CDS_SERIES["sn_nvidia"][0])
        nvidia["data"].append([reference["observation_date"], reference["spread_bps"]])
    cds_health = option_observation_health({"series": cds_series}, now=now)
    reports.append({"file": "ai_cds_daily.json", **cds_health,
        "missing_names": [label for label, _ in CDS_SERIES.values() if label not in cds_health["latest_by_name"]]})
    market = read_payload(root / "data_snapshots" / "hk_market_daily.json")
    banks = read_payload(root / "data_snapshots" / "bank_ah_daily.json")
    bank_series = [{"name": key, "data": [[r["observation_date"], r.get("premium_pct")]
        for r in banks.get("series", {}).get(key, {}).get("records", [])]}
        for key in ("ABC", "ICBC", "CCB")]
    bank_health = option_observation_health({"series": bank_series}, now=now)
    reports.append({"file": "bank_ah_daily.json", **bank_health,
        "missing_names": [key for key in ("ABC", "ICBC", "CCB") if key not in bank_health["latest_by_name"]]})
    series = [{"name": symbol, "data": [[r["observation_date"], r.get("close")]
                                          for r in node.get("records", [])]}
              for symbol, node in market.get("series", {}).items()]
    health = option_observation_health({"series": series}, now=now)
    reports.append({"file": "hk_market_daily.json", **health,
                    "missing_names": [symbol for symbol in ("0700.HK", "0388.HK", "^HSI", "HSTECH")
                                      if symbol not in health["latest_by_name"]]})
    equity_path = root / "data_snapshots" / "us_equity_daily.json"
    try:
        equity = json.loads(equity_path.read_text())
    except (OSError, ValueError):
        equity = {}
    equity_series = [{"name": symbol, "data": [
        [row.get("date"), row.get("close")] for row in
        ((equity.get("series") or {}).get(symbol) or {}).get("records", [])]}
        for symbol in ("SPX", "RSP")]
    equity_health = option_observation_health({"series": equity_series}, now=now)
    reports.append({"file": "us_equity_daily.json", **equity_health,
                    "missing_names": [symbol for symbol in ("SPX", "RSP")
                                      if symbol not in equity_health["latest_by_name"]]})
    china_path = root / "data_snapshots" / "china_equity_daily.json"
    try:
        china = json.loads(china_path.read_text())
    except (OSError, ValueError):
        china = {}
    china_series = [{"name": code, "data": [[row.get("date"), row.get("close")]
        for row in ((china.get("series") or {}).get(code) or {}).get("records", [])]}
        for code in ("000300", "000852", "932000")]
    china_health = option_observation_health({"series": china_series}, now=now)
    reports.append({"file": "china_equity_daily.json", **china_health,
                    "missing_names": [code for code in ("000300", "000852", "932000")
                                      if code not in china_health["latest_by_name"]]})
    from macro_platform.treasury_cash import read_verified_tga_snapshot
    tga = read_verified_tga_snapshot(root / "data_snapshots" / "treasury_tga_daily.json")
    tga_option = {"series": [{"name": "TGA_DAILY", "data": [[str(row.observation_date), row.TGA_DAILY]
                                                             for row in tga.itertuples()]}]}
    tga_health = federal_publication_health(option_observation_health(tga_option, now=now), now)
    reports.append({"file": "treasury_tga_daily.json", **tga_health,
                    "missing_names": [] if "TGA_DAILY" in tga_health["latest_by_name"] else ["TGA_DAILY"]})
    for symbol in ("IORB", "EFFR", "SOFR", "RRPONTSYAWARD", "SRFTSYD", "DGS3MO", "DGS2", "DGS10", "DGS30",
                   "DFII5", "DFII10", "T10YIE", "WALCL", "WRESBAL", "RRPONTSYD", "VIXCLS", "VXVCLS", "SP500", "GVZCLS"):
        payload = read_payload(root / "data_snapshots" / "fred_cache" / f"{symbol}.json")
        rows = payload.get("records") or []
        option = {"series": [{"name": symbol, "observation_cadence": "weekly" if symbol in ("WALCL", "WRESBAL") else "daily", "data": [[r.get("date"), r.get("value")] for r in rows]}]}
        health = option_observation_health(option, now=now)
        if symbol in ("EFFR", "SOFR"):
            health = federal_publication_health(health, now)
        reports.append({"file": f"fred_cache/{symbol}.json", **health,
                        "missing_names": [] if symbol in health["latest_by_name"] else [symbol]})
    for report in reports:
        payload = read_payload(root / "data_snapshots" / report["file"])
        report["invalid_snapshot"] = not bool(payload)
        report["record_issues"] = raw_record_issues(payload, now=now)
    return reports


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="source_health.json")
    parser.add_argument("--only", action="append", help="Audit only these snapshot files (repeatable)")
    parser.add_argument("--source-report", type=Path, help="Recent live source comparison; raw dates are still validated")
    args = parser.parse_args()
    reports = audit()
    evidence_path = args.source_report or ROOT / 'data_snapshots/all_source_freshness.json'
    attach_live_source_evidence(reports, read_payload(evidence_path))
    if args.only:
        reports = [report for report in reports if report["file"] in args.only]
        if not reports:
            raise SystemExit("No matching source snapshots selected")
    Path(args.output).write_text(json.dumps(reports, ensure_ascii=False, indent=2) + "\n")
    summary = ["## Actual source observation dates", "", "| Snapshot | Series | Last observation | Update due by | Status |",
               "|---|---|---|---|---|"]
    failed = False
    for report in reports:
        issues = {key: count for key, count in report["record_issues"].items() if count}
        if report["invalid_snapshot"] or issues:
            failed = True
            summary.append(f"| {report['file']} | raw records | — | — | INVALID: {issues or 'missing/corrupt snapshot'} |")
        for name, day in report["latest_by_name"].items():
            upstream = report.get('upstream_delayed', {}).get(name)
            bad = name in report["future_names"] or (name in report["stale_names"] and not upstream)
            failed |= bad
            status = ("UPSTREAM DELAY: same latest published observation; verified " + upstream['verified_at']
                      if upstream and name not in report['future_names'] else
                      "OVERDUE / invalid future date" if bad else "within cadence limit (not source-latest verification)")
            summary.append(f"| {report['file']} | {name} | {day} | {report['due_by_name'][name]} | {status} |")
        failed |= bool(report["missing_names"])
        for name in report["missing_names"]:
            summary.append(f"| {report['file']} | {name} | missing | — | UNAVAILABLE |")
    text = "\n".join(summary) + "\n"
    print(text)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as handle:
            handle.write(text)
    if failed:
        raise SystemExit("One or more individual source series are overdue or missing; see source_health.json")


if __name__ == "__main__":
    main()

