# Macro Dashboard

Market and macroeconomic data dashboard with 13 interactive charts and
watchlists. Production UI: <https://data-macromarket.streamlit.app/>.

**Stable application baseline:** `2026-10-09-tga-close-recovery-r38`. A green
GitHub Actions run confirms code/tests, **not** the deployed browser version.
Compare the build identifier printed above the first chart before filing a
UI regression.

## Run locally

Requires Python 3.12+ and a network connection for sources that have no
bundled observations.

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

If an external feed is unavailable, the dashboard may use a *dated, verified*
last-good snapshot, or display a missing-series warning. Do not read a cached
observation as a live quote.

Source freshness uses **each field's actual observation date**, not a JSON
download timestamp. Daily/weekly feeds receive seven weekdays of grace (this
is not an exchange holiday calendar). HK monthly monetary statistics allow
the following publication cycle plus a one-week buffer. Genuine late series
remain visible with their date, age and frequency; missing dates are not filled.

`Audit actual source freshness` runs daily and after snapshot updates. Its
Actions summary and `actual-source-freshness` artifact show field-level dates;
overdue or absent observations fail the audit even when a collector fetched
other series successfully. Run locally with `python scripts/audit_source_freshness.py`.

CME copper warehouse totals use **Activity Date**, not Report Date, and convert
short tons to metric tonnes. COCHILCO remains the historical backup. HKAB's
dated O/N and 3M HIBOR fixing supplements the lagging HKMA daily bulletin.
Snapshot publishers retry fetch/rebase/push races without force-pushing;
automatic data jobs never run the obsolete HSTECH code-wiring patch.

## Chart sections

| # | Section |
|---|---|
| 1–4 | Federal Reserve rates, nominal/real Treasury yields, curve, US liquidity |
| 5–8 | Hong Kong monetary pulse, bank liquidity, HIBOR funding, HKD / market overlays |
| 9 | US equity risk (VIX/VIXEQ, VIX3M−VIX, VIXEQ−VIX, VIXEQ/VIX, COR1M/COR3M) |
| 10 | Precious metals |
| 11 | Digital assets |
| 12 | Copper price/inventory |
| 13 | Asian rates and yield curves |

The 5Y / 1Y / 6M / 3M / 1M selectors must keep **both X and each Y axis
adaptive**. A Plotly compatibility view is not proof that native ECharts
X/Y autoscaling works.

Chart 9 retains the VIXEQ/VIX ratio and adds the **VIXEQ−VIX difference**
in volatility points on R2. Both use same-date observations with no forward
fill. **COR1M / COR3M** use original Cboe index points on their own R4 axis;
they are correlation indices, not volatility readings. Official Cboe histories
are bundled for cold start and refreshed each weekday by
`update-correlation-snapshot.yml`. Early history includes Cboe back-calculations.

## Validation

```bash
python -m unittest discover -s tests -p "test_maintenance_workflows.py" -v
python -m unittest discover -s tests -p "test_tga_closing_schema_2022.py" -v
python -m unittest discover -s tests -p "test_echarts_axes.py" -v
python -m unittest discover -s tests -p "test_app_runtime_smoke.py" -v
```

The full `Viewport Y-axis regression` GitHub workflow additionally tests
offline app startup, historical observations, data provenance and dynamic axes.
The separate `Maintenance workflow safety` workflow is intentionally fast
and does not contact external data vendors.

## Architecture and safe maintenance

Read [docs/MAINTENANCE.md](docs/MAINTENANCE.md) for the module boundaries,
data source provenance, automatic snapshot jobs vs. **manual-only obsolete
migration jobs**, a cautious performance optimization plan, and the merge
checklist.

Do not commit a plot or a new estimated rate as an original observation.
The Treasury DTS TGA closing account changed field placement in April 2022;
`macro_platform/treasury_cash.py` records the correct account-label-based
interpretation.

## SPX / RSP drawdown chart (11)

SPX uses the S&P 500 float-adjusted market-cap-weighted **price index**;
RSP is the Invesco S&P 500 Equal Weight ETF. RSP is a fund, not an index:
its price reflects fund fees, distributions and tracking differences.
Both histories use completed US daily `quote.close` prices, split-adjusted
but **without dividend reinvestment**. Never mix Yahoo `adjclose` total-return
adjustments with the SPX price index. `range=max` monthly responses are rejected.

For every date, drawdown = `(close / cumulative_max(close) - 1) * 100`.
Peaks are calculated on each security's full available daily history **before**
limiting the rendered chart to five years or changing its viewport. This is
close-to-close drawdown, not intraday-high drawdown. Chart 11 has its own fragment and time controls, without a data table.
Equity and volatility charts are grouped together, followed by Asia rates,
commodities and crypto assets. Captions show latest completed close, prior peak/date,
absolute drop and percentage decline. Missing or stale observations remain labeled.

The data-only `update-us-equity-snapshot.yml` job refreshes both histories and
atomically publishes `data_snapshots/us_equity_daily.json`. Partial, stale,
future, non-daily or truncated responses cannot replace last-good data.


## China equity drawdowns (12)

The CSI 300 (000300), CSI 1000 (000852), and CSI 2000 (932000) share one
percentage drawdown axis. Prices come from the CSI official historical API,
using completed mainland trading-day closes and each index's full available
history since its base date. Published pre-launch backcasts are retained;
carry-in API rows before the base date are excluded. The five-year visible
window never resets earlier highs, including 2007 and 2015 peaks.

The data-only China equity workflow atomically updates all three histories.
Incomplete sessions, missing indices, shortened history and stale responses
cannot replace the last-good snapshot. Actual observation dates remain visible.

Display order: 1–4 US policy/rates/liquidity; 5–8 Hong Kong liquidity;
9 US equity risk; 10 VIX term structure; 11 US equity drawdowns;
12 China equity drawdowns; 13 China rates; 14 Japan rates/equity;
15 precious metals; 16 copper; 17 crypto. Internal builder keys stay stable.
