# US source updates

`update-us-sources.yml` owns US snapshot collection at minutes 11 and 41 of every UTC hour, including weekends. GitHub schedules can start late; this is a retry cadence, not a publication SLA. It also runs on relevant source-code pushes. Historical US-specific workflows are retained for manual recovery only. The independent all-source audit may also repair observed pipeline lag.

`refresh_us_sources.py` runs independent bounded collectors, then compares each saved last-observation date with its publisher. Failed, missing and still-lagging families receive a second attempt. The FRED collector finishes before Cboe supplements because both can update VIX/SPX cache files. Late Cboe CSVs cannot prevent the dated official closing endpoints from advancing history. Copper, WTI, LME and CME refresh independently using current observations and retained history.

Successful files are published even when another source fails. `publish_source_refresh.py` fetches the latest main, preserves concurrent updates and unions validated FRED observations by date. Upstream wins revisions to overlapping dates. No force push is used. A second audit checks the actual published files; unresolved failures remain red in Actions and are retained in the `us-source-freshness` artifact. The scheduled next run automatically retries.

The page watches snapshot revisions and five-minute live-cache buckets, including in long-open sessions. NASDAQ-100, gold and silver now also have completed-bar snapshots available during a live API outage. Live data only replaces a snapshot when its last observation date is newer.

“Latest” means the latest real observation available from its publisher. SOFR/EFFR are published for an earlier effective date; H.4.1 is weekly; Treasury fiscal data, CDS and option statistics may publish later. No stale date is relabeled as today, and ratios/means retain their existing same-date/session rules. If the source itself has not published, preserve the last real observation and retry.

## SPX put/call source change

Cboe's report for 2026-11-09 names its aggregate **SPX + SPXW + SPXO**, where the previous reports named **SPX + SPXW**. The parser accepts only these explicit named baskets and reconciles put volume, call volume, total volume and the published ratio. Each newly fetched row records its exact `product`; older rows without that field retain the legacy SPX + SPXW definition. The chart's 63-session mean follows the dated publisher aggregate, so a window spanning the change includes both definitions. The source label on the chart discloses SPXO. TOTAL, broad INDEX and open-interest ratios are never substituted.
