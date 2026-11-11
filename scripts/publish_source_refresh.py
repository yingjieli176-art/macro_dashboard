"""Publish validated snapshots while preserving concurrent source updates.

Conflicting upstream files win and remain visible as lag in the source audit.
No force push or timestamp-based overwrite is used.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def git(root, *args, check=True):
    return subprocess.run(["git", *args], cwd=root, check=check, capture_output=True)


def reconcile_report(root):
    path = root / "data_snapshots/all_source_freshness.json"
    if not path.exists():
        return
    sys.path.insert(0, str(root))
    from scripts.probe_all_sources import jobs
    stored = {key: date for key, _, _, date, _ in jobs()}
    report = json.loads(path.read_text())
    rows = []
    for row in report.get("sources", []):
        if row["id"] not in stored:
            continue
        date, source = stored[row["id"]], row.get("source_latest")
        row["repository_latest"] = date
        row["status"] = ("unverified" if source is None else "live_only" if date is None else
                         "pipeline_lag" if date < source else "source_behind_repository" if date > source else
                         "snapshot_verified" if row.get("verification_method") == "snapshot" else "at_source_latest")
        rows.append(row)
    report["sources"] = rows
    report["repository_reconciled_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")


def merge_fred_snapshot(name, candidate, upstream):
    """Union dated same-definition observations; upstream wins revised dates.

    This resolves real parallel JSON conflicts without dropping newer local
    dates or rolling back revisions already on main. Reject malformed inputs.
    """
    if not name.startswith("data_snapshots/fred_cache/"):
        return None
    try:
        import pandas as pd
        from macro_platform.fred_observations import validate_observations
        local, remote = json.loads(candidate), json.loads(upstream)
        sid = Path(name).stem
        if local["series_id"] != sid or remote["series_id"] != sid:
            return None
        for node in (local, remote):
            validate_observations(pd.DataFrame(node["records"]), sid,
                                  date_column="date", value_column="value", min_rows=12)
        records = {row["date"]: row for row in local["records"]}
        records.update({row["date"]: row for row in remote["records"]})
        # Metadata describes the source supplying the newest observation.
        result = dict(local if local["coverage_end"] > remote["coverage_end"] else remote)
        result["records"] = [records[d] for d in sorted(records)]
        result["coverage_end"] = result["records"][-1]["date"]
        if result["records"] == remote["records"]:
            return upstream
        result["merge_sources"] = sorted({str(local.get("source_series", "")), str(remote.get("source_series", ""))})
        return (json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
    except (ValueError, KeyError, TypeError):
        return None


def publish(root=ROOT, audit=reconcile_report):
    base = git(root, "rev-parse", "HEAD").stdout.decode().strip()
    names = git(root, "ls-files", "--modified", "--others", "--exclude-standard", "-z", "--", "data_snapshots/").stdout
    paths = {name.decode() for name in names.split(b"\0") if name and name.endswith(b".json")}
    candidates = {name: (root / name).read_bytes() for name in paths if (root / name).is_file()}
    for _ in range(5):
        git(root, "fetch", "origin", "main")
        upstream = git(root, "rev-parse", "origin/main").stdout.decode().strip()
        changed = {name.decode() for name in git(root, "diff", "--name-only", "-z", base, upstream,
                                                "--", "data_snapshots/").stdout.split(b"\0") if name}
        # This is a disposable CI checkout. Keep code and concurrent data at
        # the newest main revision before restoring uncontested observations.
        git(root, "reset", "--hard", upstream)
        for name in changed.intersection(candidates):
            if (root / name).is_file() and (root / name).read_bytes() == candidates[name]:
                continue
            if (root / name).is_file():
                merged = merge_fred_snapshot(name, candidates[name], (root / name).read_bytes())
                if merged is not None:
                    candidates[name] = merged
                    continue
            print("Preserving concurrent upstream snapshot:", name, flush=True)
            if name != "data_snapshots/all_source_freshness.json":
                candidates.pop(name)
        for name, content in candidates.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        audit(root)
        staged = sorted(set(candidates) | ({"data_snapshots/all_source_freshness.json"}
                        if (root / "data_snapshots/all_source_freshness.json").is_file() else set()))
        if staged:
            git(root, "add", "--", *staged)
        if git(root, "diff", "--cached", "--quiet", check=False).returncode == 0:
            print("No observation changes to publish", flush=True)
            return
        git(root, "commit", "-m", "data: refresh published observations and verify source dates")
        if git(root, "push", "origin", "HEAD:main", check=False).returncode == 0:
            print("Published verified source snapshots", flush=True)
            return
        # The next attempt compares new upstream against this attempt's base.
        base = upstream
        candidates = {name:(root/name).read_bytes() for name in candidates if (root/name).is_file()}
    raise RuntimeError("Snapshot publication conflicted repeatedly; upstream was preserved")


if __name__ == "__main__":
    publish()
