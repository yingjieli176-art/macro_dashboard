# Source update timing

Daily market/interest-rate data is overdue after two weekdays, rather than seven.
Weekly WALCL/reserve-balance sources retain a ten-calendar-day deadline.
Monthly HK monetary statistics use the end of the following publication cycle plus one day.
These rules detect delay; they do not claim a successful HTTP response contains the newest published value.
Charts always show actual observation dates and never synthesize a more recent date.

HKD M2/M3 are also checked against the original HKMA monetary-statistics release
annex. The summary and dedicated APIs can still return null/older observations
after the new month has been published. The collector discovers the latest
release, validates Table 1A's reference month, HK$ million unit and FX-swap-adjusted
definition, then fills only missing amounts. It records the original PDF URL,
SHA-256 and published rounding precision; it never derives stocks from rounded
percentage changes or replaces more precise API values with rounded amounts.

Review CI records its initial freshness failures before attempting repair.
The final raw-record audit and source comparison remain strict, so a failed
collector or unresolved stale observation still fails the job.

GitHub scheduled runs were observed starting over four hours after their configured time on 2026-10-20.
Source jobs now have several non-round-minute catch-up opportunities after publication, including next-morning US retries.
GitHub schedules remain best-effort, not a guaranteed service-level deadline.
Repeated jobs start from current main, preserve concurrent updates, and never cancel a publisher already running.

The daily HKMA updater retains history, refreshes a 30-day overlap in parallel, and requests the original endpoint before the relay.
Failure of an individual history endpoint does not prevent a current HKAB fixing from being saved.
Failures remain visible as Actions warnings and source_errors; good historical observations are preserved.
The monthly monetary backup preserves verified main-snapshot updates even if its independent live request times out.
TGA runtime snapshots are rechecked after six hours instead of waiting 72 hours.

Post-publish checks validate the relevant per-field observation dates, after saving any good updates.
The independent source audit runs every three hours and requires all four Hong Kong market series.
An old daily value cannot be made current by a new download timestamp or null observation.

Validation: full production regression suite and browser checks run on the pull request.

Daily Treasury nominal/real constant-maturity yields and Cboe VIX/VIX3M/GVZ closes now try the original publisher before FRED's mirror, preserving the same series definition and source date. FRED remains a fallback.
