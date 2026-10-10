# r44 latest-observation retention

Build: `2026-10-10-latest-observation-r44`. When an upstream response is
missing, invalid or older than a verified stored observation, keep the stored
latest value and its original date. Compare coverage before disk or memory
replacement and prefer the latest observation across both copies. Responses
with the same latest date may still apply official revisions. Offline sync
reports the observations actually retained on disk. No forward-filled dates
or estimated observations are introduced.

Local validation: all 159 regressions pass; `git diff --check` passes.

Two added regressions use actual stored IORB observations to verify older
successful responses cannot overwrite disk or memory, the API can recover
after an older CSV response, and same-date revisions remain admissible.
Current-candidate CI and Cloud acceptance must be evaluated separately from
the historical evidence below. No main merge or Cloud deployment is performed.

On the preceding r43 SHA, the Actions FRED secret was configured and verified:
raw-history job `114158542271` fetched 22/23 series, updated FYGFDPUN, retained
21 unchanged series, and rejected future-dated IORB while preserving its backup.
Health classified 19 series available and four debt series stale. This verifies
Actions retrieval only; the Cloud secret configuration remains unverified.

# Historical r43 release acceptance record

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
3. A fresh second browser session lost five available chart positions after a
   shared cache hit. Plotly 6 pickles NumPy numeric arrays as dtype/bdata maps;
   ECharts expects readable date/value sequences. The first session's last-good
   native options hid the failure on subsequent reruns. Normalize x/y vectors
   to ordinary sequences before caching all macro and HK mode bundles. Clear
   the property before resetting it because Plotly skips equal-value assignments.
   Preserve exact dates, null gaps, observations and layout; invalidate old
   bundle entries through the r42 build revision. Regressions compare actual
   SOFR/HK snapshot samples across cache reads and execute a fresh AppTest
   session against warmed caches. The two-context Chromium assertion remains
   unchanged and must pass before claiming browser session isolation.
4. Live FRED refreshes admitted tomorrow/future observations, nonfinite values
   and implausible policy rates that the offline collector rejected. A reproduced
   live refresh stored a future IORB date and `Infinity` as last-good data. Share
   observation admission between the collector, live refresh, disk writer and
   disk reader; reject dates after the current UTC date, nonfinite values and
   the existing policy-rate bounds. A graph CSV must contain the requested
   series column; a different series cannot be relabeled as the requested one.
   Failed admission continues to the API fallback and preserves existing data
   when all sources fail. Missing points are never filled.
5. Disk writes stamped a slightly later fetch time than the live memory copy,
   so the getter selected the persisted fallback and marked a successful live
   recovery stale. Persist the same fetch timestamp and prefer the live copy on
   an exact tie. A newer independently updated snapshot still wins by timestamp.

The r43 local suite passes all 157 regressions. New tests use actual stored IORB
observations to verify invalid-success rejection, byte-for-byte backup retention,
CSV series identity, API recovery, and source recovery through a warmed getter
without clearing caches. The current build is `2026-10-10-fred-admission-r43`.
The r42 CI/browser/performance results below apply to `037283a`, not this new
candidate; r43 needs its own CI and all remaining Cloud checks. No new upstream
availability or Cloud deployment is claimed by these admission fixes.

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
| FRED history | 23/23 valid stored series after the continuation below; 19 current and 4 stale under the existing age rules | Stored-series coverage alone is not full-chart or Cloud acceptance |
| FRED transport | Official public CSV downloads recovered in the continuation; the earlier CI route timed out and its API fallback was unconfigured | Verify the same candidate and its source updater in CI/Cloud |
| US yields / curves | DGS3MO/DGS2/DGS10/DFII5/DFII10/T10YIE now have verified official backups | Verify deployed files, observation dates and source labels |
| US liquidity | TGA alone is not Net Liquidity; WALCL and ON RRP must satisfy age/unit checks | Derived Net Liquidity must remain absent when a constituent is unavailable |
| Other charts | Genuine stored HKMA, VIXEQ and copper data; live Yahoo/Asia inputs can still fail | Verify each intended series, date, units and missing-state label |

### FRED source recovery continuation (2026-10-10)

The interrupted optimization was resumed from PR head
`a7de1646fea6dc6e5b8bf48196e8907c4b584e2a`. Its 20 missing series are now
stored from real official FRED downloads. The first local run reproduced
four-second connection timeouts (14 fetches failed). A separate DGS10 request
completed in 6.72 seconds and returned 1,694 genuine observations through
2026-10-08. The offline collector now allows a bounded 12-second connection
and 30-second read timeout. The interactive application request budgets,
worker concurrency and chart controls are unchanged.

The second collector run successfully fetched 22 series. IORB's response
contained future-dated values and was rejected by the existing validator;
its original verified snapshot remains byte-for-byte unchanged. The existing
SOFR/EFFR snapshots also remain unchanged because observations did not change.
No future values, interpolation or estimates were added. All 23 stored
series validate, with exact observed dates and values preserved by the runtime
reader. A regression now checks that parity against every repository backup.

The existing age rules classify 19 series as available and four low-frequency
debt series as stale: GFDEBTN, FDHBFRBN and FDHBPIN end 2026-04-01; FDHBFIN ends
2026-01-01. Those are the returned observation dates, not a claim that newer
official releases exist. The age rules and missing/stale disclosure remain
unchanged. Per-series rows, provenance and SHA-256 hashes are recorded in
[`evidence/fred-source-recovery.json`](evidence/fred-source-recovery.json).
This resolves the absent FRED backup blocker; all intended chart constituents
and the target-environment gates below still require acceptance.

Validation of the recovered tree: all 153 regression tests pass. The actual
offline AppTest page emits 11 native chart messages across 13 positions, no
Plotly substitutions and no startup exceptions. Digital assets and Asian
rates remain absent offline; the precious-metals chart has only its GVZ
volatility overlay. Eleven rendered charts therefore do **not** establish
complete intended-series coverage. Exact emitted trace names are recorded in
[`evidence/recovered-offline-chart-smoke.json`](evidence/recovered-offline-chart-smoke.json).

Independent-process and repeated server-script samples using the recovered
snapshots and immediately failing external requests:

| Sample | N | Median seconds | P95 seconds | Runtime/control failures |
| --- | ---: | ---: | ---: | ---: |
| Cold server-script startup | 3 | 2.763 | 2.800 | 0 |
| Warm full-script rerun | 100 | 1.223 | 1.402 | 0 |
| Range-input full-script rerun | 100 | 1.293 | 1.414 | 0 |

Native option JSON totals 1,552,288 bytes. Threads fall from 27 to 2 after
resource-cache release. Peak RSS is 295,628 KiB; this environment cannot read
settled RSS, so no convergence conclusion is drawn. Full samples and source
fingerprints are in
[`evidence/recovered-server-runtime.json`](evidence/recovered-server-runtime.json).
These are local server measurements, not Cloud or browser timings, and the
earlier CI measurements used different source coverage. The local Chromium
download was truncated; browser validation must run in CI for the new SHA.
All Cloud deployment/rollback gates remain outstanding.

## Deployment and rollback

Candidate code build: `2026-10-10-fred-admission-r43`. The PR records the
exact candidate SHA and merged main parent. Check the actual Cloud branch,
deployed SHA, build label, dependency versions and logs; an HTTP 200 alone is
insufficient. No preproduction Cloud URL or usable owner dashboard session was
available. On 2026-10-10 the existing production URL became reachable in the
browser. Its visible build is `2026-10-09-tga-close-recovery-r38`, not the r42
candidate. It showed all 13 native chart positions with no exception/renderer
error and visible observation dates, including US yields and liquidity. This
is old-deployment evidence: it neither proves r42 deployed nor establishes the
provenance/completeness of the candidate's missing offline FRED backups. r42
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
