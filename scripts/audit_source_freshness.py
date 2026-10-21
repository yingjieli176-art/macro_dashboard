"""Audit individual observations offline; a fresh download cannot hide old data."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from macro_platform.echarts_axes import option_observation_health


SPECS = [
    ("jpy_market_daily.json", "date", "", ["usd_jpy_close"]),
    ("jpy_neer_daily.json", "date", "", ["value"]),
    ("copper_market_daily.json", "date", "", ["comex_stock_t", "lme_stock_t", "comex_price_usd_lb", "lme_3m_usd_t"]),
    ("usdhkd_daily.json", "observation_date", "", ["value"]),
    ("vixeq_daily.json", "observation_date", "", ["close"]),
    ("cor1m_daily.json", "observation_date", "", ["close"]),
    ("cor3m_daily.json", "observation_date", "", ["close"]),
    ("hkma_monetary_statistics.json", "end_of_month", "hk_6_range",
     ["m2_hkd", "m3_hkd", "monetary_base_total", "aggr_balance", "outstanding_efbn", "ow_lb_bf_disc_win"]),
    ("hkma_banking_liquidity_daily.json", "end_of_date", "", ["hibor_overnight", "hibor_3m", "closing_balance"]),
]


def audit(root=ROOT, now=None):
    reports = []
    for filename, date_key, cadence, fields in SPECS:
        payload = json.loads((root / "data_snapshots" / filename).read_text(encoding="utf-8"))
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
                           "observation_cadence": "weekly" if filename == "jpy_neer_daily.json" else "daily"})
        health = option_observation_health({"series": series}, chart_key=cadence, now=now)
        missing = [field for field in fields if field not in health["latest_by_name"]]
        reports.append({"file": filename, **health, "missing_names": missing})
    market = json.loads((root / "data_snapshots" / "hk_market_daily.json").read_text())
    series = [{"name": symbol, "data": [[r["observation_date"], r.get("close")]
                                          for r in node.get("records", [])]}
              for symbol, node in market.get("series", {}).items()]
    health = option_observation_health({"series": series}, now=now)
    reports.append({"file": "hk_market_daily.json", **health,
                    "missing_names": [symbol for symbol in ("0700.HK", "0388.HK", "^HSI", "HSTECH")
                                      if symbol not in health["latest_by_name"]]})
    from macro_platform.treasury_cash import read_verified_tga_snapshot
    tga = read_verified_tga_snapshot(root / "data_snapshots" / "treasury_tga_daily.json")
    tga_option = {"series": [{"name": "TGA_DAILY", "data": [[str(row.observation_date), row.TGA_DAILY]
                                                             for row in tga.itertuples()]}]}
    tga_health = option_observation_health(tga_option, now=now)
    reports.append({"file": "treasury_tga_daily.json", **tga_health,
                    "missing_names": [] if "TGA_DAILY" in tga_health["latest_by_name"] else ["TGA_DAILY"]})
    for symbol in ("IORB", "EFFR", "SOFR", "RRPONTSYAWARD", "DGS3MO", "DGS2", "DGS10",
                   "DFII5", "DFII10", "T10YIE", "WALCL", "WRESBAL", "RRPONTSYD", "VIXCLS", "VXVCLS", "SP500"):
        payload = json.loads((root / "data_snapshots" / "fred_cache" / f"{symbol}.json").read_text())
        rows = payload.get("records") or []
        option = {"series": [{"name": symbol, "observation_cadence": "weekly" if symbol in ("WALCL", "WRESBAL") else "daily", "data": [[r.get("date"), r.get("value")] for r in rows]}]}
        health = option_observation_health(option, now=now)
        reports.append({"file": f"fred_cache/{symbol}.json", **health,
                        "missing_names": [] if symbol in health["latest_by_name"] else [symbol]})
    return reports


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="source_health.json")
    parser.add_argument("--only", action="append", help="Audit only these snapshot files (repeatable)")
    args = parser.parse_args()
    reports = audit()
    if args.only:
        reports = [report for report in reports if report["file"] in args.only]
        if not reports:
            raise SystemExit("No matching source snapshots selected")
    Path(args.output).write_text(json.dumps(reports, ensure_ascii=False, indent=2) + "\n")
    summary = ["## Actual source observation dates", "", "| Snapshot | Series | Last observation | Update due by | Status |",
               "|---|---|---|---|---|"]
    failed = False
    for report in reports:
        for name, day in report["latest_by_name"].items():
            bad = name in report["stale_names"] or name in report["future_names"]
            failed |= bad
            status = "OVERDUE / invalid future date" if bad else "within cadence limit (not source-latest verification)"
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
