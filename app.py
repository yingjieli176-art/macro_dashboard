# =========================
# 数据来源
# =========================

st.markdown("### Data Sources")

st.markdown(
    """
**Funding / Liquidity**

- **SOFR** — [FRED: Secured Overnight Financing Rate](https://fred.stlouisfed.org/series/SOFR)

- **IORB** — [FRED: Interest Rate on Reserve Balances](https://fred.stlouisfed.org/series/IORB)

- **EFFR** — [FRED: Effective Federal Funds Rate](https://fred.stlouisfed.org/series/EFFR)

- **ON RRP** — [FRED: Overnight Reverse Repurchase Agreements](https://fred.stlouisfed.org/series/RRPONTSYAWARD)


**Yield**

- **10Y Treasury (DGS10)** — [FRED: 10-Year Treasury Constant Maturity Rate](https://fred.stlouisfed.org/series/DGS10)

- **10Y TIPS Real Yield (DFII10)** — [FRED: 10-Year Treasury Inflation-Indexed Security](https://fred.stlouisfed.org/series/DFII10)

- **10Y Treasury − 10Y TIPS** — Calculated directly from the two FRED series above.
"""
)
