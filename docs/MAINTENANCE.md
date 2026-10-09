# Macro Dashboard: maintenance and safe optimization plan

> Current build: `2026-10-09-data-integrity-progressive-r39`. This document is
> for maintainers. Do **not** treat a green CI build as proof that Streamlit
> Cloud has deployed it; check the chart build label and Cloud logs separately.

## Runtime boundaries

| Source | Responsibility | Reliability rule |
| --- | --- | --- |
| `app.py` | 13-chart layout, Streamlit widgets/fragments, rendering recovery, market overview | Only the main Streamlit script creates widgets; keep chart controls fragment-local |
| `data.py` | FRED, NY Fed, Treasury, market/news clients | Cache **observed** values; label missing and stale data, never fake market observations |
| `macro_platform/chart_axes.py` | Plotly date ranges, multi-axis fallback | A zoom must refit visible samples, never silently revert to full-range Y |
| `macro_platform/echarts_axes.py` | Native ECharts time slider and independently rescaled axes | Preserve real observation timestamps and null gaps; keep `filterMode: filter` |
| `macro_platform/hk_liquidity.py` | HKMA/HKAB funding, monetary and Hong Kong overlays | Build charts 6/7 independently if other overlays fail |
| `macro_platform/treasury_cash.py` | DTS TGA closing-balance row parsing | 2022+ **TGA Closing Balance** is the named closing amount in `open_today_bal`; arbitrary opening-balance rows are **not** substitutes |
| `data_snapshots/` | Verified last-good observations for cold start | Retain provenance/coverage end; no fabricated or forward-dated records |

## Production source update jobs (KEEP automatic)

The current data-only jobs intentionally run on a schedule and should not be
disabled as part of legacy migration cleanup:

- `update-hkma-daily-snapshot.yml`: Hong Kong daily banking liquidity / HIBOR snapshot
- `update-hkma-snapshot.yml`: HKMA monthly monetary snapshot
- `update-hkma-base-rate-history.yml`: official Hong Kong base rate history
- `update-hk-market-daily.yml`: market daily price history
- `update-copper-snapshot.yml`: verified copper sources
- `sync-fred-verified-cache.yml`: official US rates backup
- `sync-tga-official-snapshot.yml`: official US Treasury daily cash closing balance
- `update-vixeq-snapshot.yml`: Cboe VIXEQ official history

Data-only jobs may commit **snapshot JSON only**. Review any workflow that
edits `app.py`, `data.py`, or `macro_platform/` as a code migration requiring a
PR and regression tests. Historical one-shot workflow patchers are manual
recovery only; they must never run by schedule or automatically on source
updates. Avoid dispatching them against today's stable app unless their patch
has been updated and reviewed.

## Checks before merging a feature or cleanup

1. Run `Viewport Y-axis regression` including Streamlit startup, the real
   Treasury snapshot cold-start test, 5Y/1Y/6M/3M/1M selection and three-axis
   ECharts fallback cases.
2. Confirm Chart 4's Net Liquidity **cannot** calculate today's value from a
   stale TGA or stale ON RRP. Existing component age limits are important.
3. Confirm charts 6 and 7 remain visible from verified HKMA/HKAB data if an
   unrelated overlay provider fails.
4. Confirm the deployed build fingerprint and observe at least one slider
   change for both a US and Hong Kong chart. A successful GitHub job is **not**
   equivalent to a successful interactive browser render.
5. Keep provider outage notes visible rather than substituting invented
   values or artificially updating source timestamps.

## Performance work: recommended order (not yet benchmarked)

The r39 audit fixes keep widget keys, modes, defaults, chart order and date
selectors unchanged. Completed charts now fill their reserved containers on
the main thread as workers finish. HKMA banking/funding reuse their prebuilt
figures. Peer Asian quote providers run concurrently, retaining deterministic
precedence for equal timestamps. Full five-year HK daily observations are
retained; no price extrema are discarded to speed up rendering.

FRED snapshots return immediately and queue a single-flight refresh once their
fetch age exceeds one hour, rather than suppressing refreshes for 84 hours.
The source cache still has its existing hourly TTL; a completed background
refresh becomes visible on the next source-cache refresh. Observation dates
remain original and dated cached observations are never represented as live.

Daily market bars are accepted only after completion in their source market
timezone. HK Raw history is migrated from Yahoo quote.close, with explicit
price_basis=raw_close; legacy adjusted history must not be mixed with new raw
closes. The PR's raw-history CI job supplies a verified snapshot artifact for
review. Scheduled source jobs remain automatic. FRED jobs additionally publish
per-series status/coverage in their Actions summary and a JSON artifact; green
CI can still accompany explicitly reported partial coverage.

The largest avoidable costs should be measured, not guessed. Use separate
timings for (a) cold Streamlit Cloud wake-up, (b) warm page rerun, (c) single
chart window/mode change and (d) slow/failing external data providers.
Measure across several runs, with all 13 figures present, and compare medians
and high-percentile wall times before accepting an optimization.

1. **First priority — measure chart construction and figure serialization.**
   `_build_macro_figures_parallel()` prepares all 13 figures, publishes ready
   sections immediately, and serializes
   several full five-year traces. Profile the worker completion times,
   Streamlit payload size and browser-side ECharts initialization. Only then
   consider further serialization optimizations. This requires browser
   regression tests because dynamic X/Y behavior is fragile.
2. **Second — contain provider latency.** Compare cold/last-good snapshot
   reads to remote requests; preserve the existing 3–5 minute figure cache
   and hourly source cache semantics. Do not add a blocking live request to
   each radio/slider interaction.
3. **Third — reduce duplicate client conversion.** Unify common Plotly /
   native option conversion behind tested pure functions **without changing**
   null handling, the right-axis scale or multi-series units. A fallback to
   Plotly is a degraded mode, not confirmation that dynamic Y works.
4. **Fourth — split oversized source modules incrementally.** `app.py` is
   large and combines quote clients, CSS, view composition and chart builders.
   Extract one well-tested, UI-free module per PR (prefer pure computations
   first); leave widget keys, Streamlit fragments and URL/session state stable.
5. **Fifth — review background tasks.** The Eastmoney news background updater
   starts a daemon thread. Review its lifecycle and cloud resource usage
   only with instrumentation, since replacing it can change freshness.

Any measured optimization must be compared on the same source snapshots and
the same 5Y/1Y/6M/3M/1M viewports. **Never reduce the number of actual market
observations solely to make an axis faster.**

