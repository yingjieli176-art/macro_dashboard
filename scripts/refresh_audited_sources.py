"""Refresh only lagging source families with their existing validated collectors.

The workflow publishes validated observations and the before/after audit.
"""
import json
from pathlib import Path
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parents[1]
FAMILIES = {
    "update_japan_corridor.py": {"JP_CORRIDOR_DEPOSIT", "JP_CORRIDOR_LOAN", "JP_CORRIDOR_TONA", "JP_CORRIDOR_REPO"},
    "sync_fred_verified_cache.py": {"VXNCLS", "IORB", "EFFR", "SOFR", "RRPONTSYAWARD", "DGS3MO", "DGS2", "DGS10", "DGS30",
        "DFII5", "DFII10", "T10YIE", "WALCL", "WRESBAL", "RRPONTSYD", "SRFTSYD", "VIXCLS", "VXVCLS", "SP500", "GVZCLS"},
    "update_usdhkd_snapshot.py": {"HKD=X"},
    "update_yen_market.py": {"JPY=X"},
    "update_japan_gov_yields.py": {"japan_2y", "japan_10y", "japan_30y"},
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
    "update_tail_risk_snapshot.py": {"SKEW", "VVIX", "VVIX_TERM", "VIX9D"},
    "update_spx_put_call_snapshot.py": {"SPX_PCR"},
    "update_nikkei225_snapshot.py": {"^N225"},
    "update_srf_usage.py": {"SRF_USAGE"},
    "update_ai_cds_snapshot.py": {"NVIDIA_CDS_5Y", "SN_AMD_CDS_5Y", "SN_ALPHABET_CDS_5Y",
                                  "SN_MICROSOFT_CDS_5Y", "SN_ORACLE_CDS_5Y"},
}


def main():
    report = json.loads(Path(sys.argv[1]).read_text())
    lagging = {row["id"] for row in report["sources"] if row["status"] == "pipeline_lag"}
    def refresh(item):
        script, sources = item
        print("Refresh observed lag:", script, sorted(lagging.intersection(sources)), flush=True)
        try:
            subprocess.run([sys.executable, str(ROOT/"scripts"/script)], cwd=ROOT,
                           check=True, timeout=240)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            # The strict after-audit decides whether an unresolved lag remains.
            print("Collector did not complete; retaining its last-good snapshot:", type(error).__name__, flush=True)
    jobs = [(script, sources) for script, sources in FAMILIES.items() if lagging.intersection(sources)]
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(refresh, jobs))


if __name__ == "__main__":
    main()

