"""Refresh only lagging source families with their existing validated collectors.

Used in review CI; this does not commit or publish observations. The before /
after reports and resulting last-good snapshots are retained for review.
"""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
FAMILIES = {
    "sync_fred_verified_cache.py": {"IORB", "EFFR", "SOFR", "RRPONTSYAWARD", "DGS3MO", "DGS2", "DGS10",
        "DFII5", "DFII10", "T10YIE", "WALCL", "WRESBAL", "RRPONTSYD", "VIXCLS", "VXVCLS", "SP500", "GVZCLS"},
    "update_usdhkd_snapshot.py": {"HKD=X"},
    "update_yen_market.py": {"JPY=X"},
    "update_japan_gov_yields.py": {"japan_2y", "japan_10y"},
    "update_correlation_snapshot.py": {"COR1M", "COR3M"},
    "update_copper_snapshot.py": {"HG=F", "comex_stock_t", "lme_stock_t", "lme_3m_usd_t"},
    "update_us_equity_snapshot.py": {"SPX", "RSP"},
    "update_china_equity_snapshot.py": {"000300", "000852", "932000"},
    "update_hk_market_daily.py": {"0700.HK", "0388.HK", "^HSI", "HSTECH"},
    "update_hkma_daily_snapshot.py": {"hibor_overnight", "hibor_3m", "disc_win_base_rate", "closing_balance"},
    "update_hkma_snapshot.py": {"m2_hkd", "m3_hkd", "aggr_balance_bf_disc_win", "outstanding_efbn",
        "ow_lb_bf_disc_win", "mb_bf_disc_win_total"},
    "sync_tga_daily_snapshot.py": {"TGA_DAILY"},
    "update_vixeq_snapshot.py": {"VIXEQ"},
}


def main():
    report = json.loads(Path(sys.argv[1]).read_text())
    lagging = {row["id"] for row in report["sources"] if row["status"] == "pipeline_lag"}
    for script, sources in FAMILIES.items():
        if not lagging.intersection(sources):
            continue
        print("Refresh observed lag:", script, sorted(lagging.intersection(sources)), flush=True)
        try:
            subprocess.run([sys.executable, str(ROOT/"scripts"/script)], cwd=ROOT,
                           check=True, timeout=240)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            # The strict after-audit decides whether an unresolved lag remains.
            print("Collector did not complete; retaining its last-good snapshot:", type(error).__name__, flush=True)


if __name__ == "__main__":
    main()
