"""Unattended US collection, isolated retries, and independent source-date checks."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import probe_all_sources as probe
from scripts.sync_fred_verified_cache import SERIES

# Single scheduled owner for these snapshots. Legacy workflows remain manual.
COLLECTORS = {
    "sync_fred_verified_cache.py": set(SERIES),
    "update_equity_risk_snapshot.py": {"VIXEQ", "COR3M", "VIXCLS", "SP500", "VXVCLS", "GVZCLS"},
    "update_tail_risk_snapshot.py": {"SKEW", "VVIX_TERM", "VIX9D"},
    "update_spx_put_call_snapshot.py": {"SPX_PCR"},
    "update_us_equity_snapshot.py": {"SPX", "RSP"},
    "update_us_market_history.py": {"^NDX", "GC=F", "SI=F"},
    "refresh_copper_current.py": {"HG=F", "CL=F", "comex_stock_t", "lme_stock_t", "lme_3m_usd_t"},
    "sync_tga_daily_snapshot.py": {"TGA_DAILY"},
    "update_srf_usage.py": {"SRF_USAGE"},
    "update_ai_cds_snapshot.py": {"NVIDIA_CDS_5Y", "SN_AMD_CDS_5Y", "SN_ALPHABET_CDS_5Y",
                                  "SN_MICROSOFT_CDS_5Y", "SN_ORACLE_CDS_5Y"},
}
US_IDS = set().union(*COLLECTORS.values())
BAD = {"pipeline_lag", "unverified", "live_only", "snapshot_verified"}


def collect(scripts, runner=subprocess.run):
    def run(script):
        try:
            result = runner([sys.executable, str(ROOT / "scripts" / script)], cwd=ROOT,
                            timeout=360, check=False)
            return script, result.returncode
        except subprocess.TimeoutExpired:
            print("Collector timeout; preserving successful files:", script, flush=True)
            return script, 124
    # FRED and the close supplement share files; finish the base collector first.
    scripts = list(scripts)
    with ThreadPoolExecutor(max_workers=3) as pool:
        outcomes = dict(pool.map(run, [s for s in scripts if s != "update_equity_risk_snapshot.py"]))
    if "update_equity_risk_snapshot.py" in scripts:
        key, code = run("update_equity_risk_snapshot.py")
        outcomes[key] = code
    return outcomes


def audit():
    probe.reset_probe_cache()
    with ThreadPoolExecutor(max_workers=5) as pool:
        return list(pool.map(probe.check, [job for job in probe.jobs() if job[0] in US_IDS]))


def retry_collectors(outcomes, rows):
    bad = {r["id"] for r in rows if r["status"] in BAD}
    return [script for script, ids in COLLECTORS.items()
            if outcomes.get(script, 1) or ids.intersection(bad)]


def write_report(rows, outcomes, path=None):
    path = path or ROOT / "data_snapshots/all_source_freshness.json"
    try:
        report = json.loads(path.read_text())
    except (OSError, ValueError):
        report = {}
    previous = {row["id"]: row for row in report.get("sources", [])}
    previous.update({row["id"]: row for row in rows})
    report.update(checked_at=datetime.now(timezone.utc).isoformat(), chart_numbering=probe.CHART_NUMBERING,
                  us_checked_at=datetime.now(timezone.utc).isoformat(),
                  us_collectors=outcomes or report.get("us_collectors", {}), sources=sorted(previous.values(), key=lambda r: r["id"]))
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    summary = __import__("os").environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as stream:
            stream.write("## US source observations\n\n| Series | Stored | Source | Result |\n|---|---|---|---|\n")
            for row in rows:
                stream.write(f"| {row['id']} | {row.get('repository_latest')} | {row.get('source_latest')} | {row['status']} |\n")


def main():
    if "--verify-published" in sys.argv:
        rows = audit()
        write_report(rows, {})
    else:
        outcomes = collect(COLLECTORS)
        rows = audit()
        retry = retry_collectors(outcomes, rows)
        if retry:
            print("Independent retry:", retry, flush=True)
            outcomes.update(collect(retry))
            rows = audit()
        write_report(rows, outcomes)
    bad = [row for row in rows if row["status"] in BAD]
    for row in rows:
        print(row["id"], row.get("repository_latest"), row.get("source_latest"), row["status"], flush=True)
    # Data are published by an always-run workflow step even when checks fail.
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
