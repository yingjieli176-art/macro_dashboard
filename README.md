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

## Chart sections

| # | Section |
|---|---|
| 1–4 | Federal Reserve rates, nominal/real Treasury yields, curve, US liquidity |
| 5–8 | Hong Kong monetary pulse, bank liquidity, HIBOR funding, HKD / market overlays |
| 9 | US equity risk (VIX/VIXEQ and term structure) |
| 10 | Precious metals |
| 11 | Digital assets |
| 12 | Copper price/inventory |
| 13 | Asian rates and yield curves |

The 5Y / 1Y / 6M / 3M / 1M selectors must keep **both X and each Y axis
adaptive**. A Plotly compatibility view is not proof that native ECharts
X/Y autoscaling works.

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
