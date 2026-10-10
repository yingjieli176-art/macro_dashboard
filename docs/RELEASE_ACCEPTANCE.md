# r41 release acceptance record

This record separates code/CI evidence from acceptance in Streamlit Cloud.
**Production release is not approved by a green CI result.** No main merge or
Cloud deployment is performed by this change.

## Reproduced issues and changes

1. `get_yahoo_daily_history` referenced `requests.utils.quote` after removing
   the `requests` import. Successful remote histories failed before HTTP. Use
   the standard-library URL encoder and assert actual raw snapshot observations
   survive the complete loader/response-parser path with original dates.
2. The late-result poller discarded completed quote rows before requesting an
   app rerun. Persist the result first, retain a newer manual quote, and respect
   the current watchlist so removed symbols are not restored. Failed futures
   do not repeatedly trigger reruns; original chart controls remain unchanged.

The full-page smoke now asserts native ECharts messages with observed samples,
dataZoom filtering and independent scaled axes, with no Plotly substitution.
This is server renderer evidence; it does not execute JavaScript. The separate
Chromium CI job verifies canvas paint and actual range/mode interactions using
the real application and repository snapshots, with external sources disabled.
The test entry point `tests/browser_offline_app.py` must never be deployed.

## Data admission

Default production gate: all 13 chart positions must have their intended
observed series; missing critical data blocks full-data release. Partial
observations may be reviewed in preproduction with visible missing/stale status.
This is not approval to silently release partial charts.

| Requirement | Current evidence | Gate |
| --- | --- | --- |
| HK market history | Snapshot price basis is `raw_close`; tests compare every date/value and preserve extrema | Verify the same files in the deployment |
| HSTECH live fetch | Preserved last-success metadata; `--raw-only` does not fetch HSTECH | Do not claim a new live HSTECH fetch |
| FRED history | 3 valid stored series: IORB, EFFR, SOFR; 20/23 absent in the r40 collection | Full-data release blocked |
| FRED transport | CSV requests timed out in CI; backup FRED_API_KEY was not configured | Provide the key securely in the platform secret manager or restore verified public reads |
| US yields / curves | DGS3MO/DGS2/DGS10/DFII5/DFII10/T10YIE missing from stored backups | Online recovery must be observed; never fabricate replacements |
| US liquidity | TGA alone is not Net Liquidity; WALCL and ON RRP must satisfy age/unit checks | Derived Net Liquidity must remain absent when a constituent is unavailable |
| Other charts | Genuine stored HKMA, VIXEQ and copper data; live Yahoo/Asia inputs can still fail | Verify each intended series, date, units and missing-state label |

## Deployment and rollback

Candidate code build: `2026-10-10-release-acceptance-r41`. The PR records the
exact candidate SHA and merged main parent. Check the actual Cloud branch,
deployed SHA, build label, dependency versions and logs; an HTTP 200 alone is
insufficient. No preproduction Cloud URL or usable owner dashboard session was
available. On 2026-10-10 the existing production URL became reachable in the
browser. Its visible build is `2026-10-09-tga-close-recovery-r38`, not the r41
candidate. It showed all 13 native chart positions with no exception/renderer
error and visible observation dates, including US yields and liquidity. This
is old-deployment evidence: it neither proves r41 deployed nor establishes the
provenance/completeness of the candidate's missing offline FRED backups. r41
Cloud interaction remains **UNVERIFIED**.

Recorded pre-r41 main candidate for rollback:
`52e0b5d2c36e1be577b43afcf962878292b1c926`. This is a repository restoration
point, **not a Cloud-verified known-good deployment**. Keep the entire Git tree,
including code, requirements and source snapshots. Restore that exact complete
tree, install its dependencies, restart the app/clear process caches, and repeat
the browser/data gates. Restoring `app.py` alone is insufficient. A rollback
exercise in the actual preproduction environment remains outstanding.

The read-only `rollback-restoration` CI job restores that complete recorded Git
tree into a separate checkout, installs its own requirements in a fresh runner,
starts a fresh process and tests real snapshot canvas rendering in Chromium.
It records the restored SHA, code/requirements/snapshot checksums and installed
dependencies. This proves isolated restoration only; a historical unpinned
dependency range cannot reproduce an unknown former Cloud environment exactly.
Missing data in the restored tree still blocks full-data release.

Expanded Chromium candidate checks use real mouse drags for the native slider
and toolbox box selection. A CI-only React hook bridge finds the existing
instance in the pinned Streamlit component; ECharts processed samples and actual
axis extents are then inspected. No chart, bundle or data is replaced by the
probe, and a framework mismatch fails the test. Two isolated browser contexts
exercise independent range/mode settings and both manual quote refresh buttons.
These are CI interaction checks, not a Cloud resource or performance result.
The server sampling job also records Linux RSS where readable; peak RSS alone
cannot establish memory convergence.

The first Linux sampling report increased RSS from roughly 299 MB at warm
sample 20 to 910 MB after 200 reruns, despite settled threads. Investigation
found the harness reused the same exception object for every simulated HTTP
failure: its growing traceback retained prior execution frames and figures.
The harness now raises a fresh exception per call and does not record mock call
history. A local 80-rerun comparison reduced peak RSS to 231,908 KiB. This fixes
measurement contamination; it is not proof of Cloud memory convergence. Earlier
reports from the reused-exception harness must not be used as production leak
or performance evidence. Final CI collects fresh 3/100/100 samples again.

The standalone Chromium server also installs its offline transport once for
the whole process. Per-session context-manager patches could overlap and restore
another session's transport while background work was active. Production
requests are not patched; both helpers are exclusively acceptance entry points.

## Remaining target-environment checks

1. Deploy the same final candidate SHA to preproduction, then verify all 13
   positions, the five ranges, both market modes, slider/box zoom and independent
   left/right axes. Exercise manual market and watchlist refresh.
2. Simulate missing-to-restored sources and completion beyond the initial
   eight-second UI wait. Confirm observations/quotes update without clearing
   caches and that controls survive the two-second metadata poll/app rerun.
3. Use multiple real browser sessions and repeated manual refresh/cache release;
   record threads, pending jobs, HTTP concurrency and RSS after requests finish.
   Python cannot forcibly stop already executing requests. An instantaneous
   thread/RSS sample is not evidence of resource convergence.
4. Predetermine acceptable cold-start, warm-rerun and single-chart interaction
   budgets. Collect 3–5 independent Cloud cold starts and sufficient warm and
   interaction samples (e.g. 100 each); report median, P95, failures and sample
   count. Repeat cold/P95 checks after production publication.

`scripts/benchmark_runtime.py` supplies independent-process cold and repeated
server-script samples, native option byte counts, threads and peak RSS. Its
AppTest range input reruns the script; it is not a browser fragment benchmark.
It cannot satisfy Cloud or browser end-to-end latency gates. Native canvas CI
acceptance likewise cannot establish Cloud transport performance. Those gates
remain **UNVERIFIED**, and no production performance claim is made.
