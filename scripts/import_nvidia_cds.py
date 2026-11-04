"""Import an authorized CSV export; no model-derived replacements for missing tenors."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from macro_platform.nvidia_cds import validate_quote


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True)
    args = parser.parse_args()
    rows = [validate_quote(r) for r in pd.read_csv(args.csv).to_dict("records")]
    if not rows:
        raise ValueError("No actual CDS observations supplied")
    path = ROOT / "data_snapshots/nvidia_cds_daily.json"
    old = json.loads(path.read_text()) if path.exists() else {}
    saved = {(r["observation_date"], r["tenor"]): r for r in old.get("records", [])}
    for row in rows:
        saved[(row["observation_date"], row["tenor"])] = row
    payload = dict(issuer="NVIDIA Corporation", currency="USD", seniority="SENIOR_UNSECURED", unit="bp",
                   quote_type="par_spread", status="observations_available", updated_at=datetime.now(timezone.utc).isoformat(),
                   records=[saved[k] for k in sorted(saved)])
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    tmp.replace(path)


if __name__ == "__main__":
    main()
