# Morning freshness incident: 2026-11-13

The scheduled jobs were running, but source-date auditing did not reliably repair discovered lag. This was not a requirement for the user to request each refresh.

## Evidence

- [Scheduled full-source run 43353655664](https://github.com/yingjieli176-art/macro_dashboard/actions/runs/43353655664/job/131650417926) at 02:39 UTC identified DX-Y.NYB 11/09→11/11, SPX_GEX 11/11→11/12 and MOVE 11/10→11/12. Both before and after reports retained all three pipeline_lag rows; no collector ran because all three were absent from FAMILIES. DXY also had no persistent writer script.
- [Scheduled FRED run](https://github.com/yingjieli176-art/macro_dashboard/actions/runs/43353625028/job/131650314716) fetched all 30 feeds without transport failures but its final cadence gate failed for EFFR/SOFR. Their 11/10 records equaled their primary source's latest publication; the two-business-day health test incorrectly included Veterans Day.
- [Scheduled TGA run](https://github.com/yingjieli176-art/macro_dashboard/actions/runs/43331875758/job/131578309366) fetched and validated 11/10, found no source update, then failed the same non-federal cadence check.
- [SPX report run](https://github.com/yingjieli176-art/macro_dashboard/actions/runs/43300827847/job/131471244163) completed collection without surfacing all per-date rejections when saved records were unchanged. Cboe now labels reports SPX+SPXW+SPXO; the retained metric is SPX+SPXW. See the preceding audit document for original publisher evidence.
- Earlier holiday/IORB/SPX-diagnostic fixes remained in unmerged PR #109; production did not contain them.

## Changes

1. Complete recovery coverage for every persisted feed in the current audit inventory: MOVE, GEX, DXY, Saxo JPY volatility, CFTC yen, copper TC/RC, WTI and Japan TIC feeds. A regression test fails when a future stored audit feed lacks a writer.
2. Add an identity-checked daily DXY writer. Reuse completed_daily_closes admission; reject wrong products/frequencies, short responses, future dates, nonfinite closes, regression and holes. Preserve older verified history and write atomically.
3. Retry mapped unverified and missing-snapshot feeds as well as known pipeline lag. Record collector outcomes and unmapped lag; collector completion never means fresh data. Perform a second targeted recovery/recheck before the existing strict gate, and still publish good observations when another source remains unresolved.
4. Add bounded live five-year Yahoo history fallback when the short-window transport fails, using independent HTTP reads and the same completed-session parser. Stored snapshots are not promoted to live verification.
5. Integrate PR #109's narrow federal holiday, PRATES effective-date and SPX rejection diagnostics; align FRED's own EFFR/SOFR health deadline with the federal publication calendar. Future-date validation stays strict.
6. Add Beijing 05:43, 06:43 and 07:43 scheduled attempts plus default-branch scheduled/manual VIX, SPX/RSP and FRED workflow-completion followups to the existing recovery workflow. Checkout always uses trusted main, not triggering-run code or artifacts. Self-triggering is excluded. Existing concurrency serializes recovery and good snapshots retain conflict protection.

GitHub cron is best-effort and can be delayed or dropped under load; this reduces dependence on one dispatch but does not promise an exact morning SLA. [Official documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

## Actual recovery and limits

The revised recovery command fetched MOVE and GEX through 2026-11-12 and DXY through 2026-11-11. Independent live rechecks confirmed those observation dates. No source dates or prices were fabricated. Related local checks: 56 tests and 80 subtests passed.

SPX P/C remains unresolved because the available report basket changed. The strict source check remains red for this source rather than substituting another ratio. TGA, EFFR/SOFR and sparse CDS may have old observation dates even when the local copy equals the source; freshness and publication cadence are different facts. Source transport failures remain visible. Licensed live-only OAS histories are not persisted.

All charts, ratios, data-source definitions and existing presentation changes are retained. No live dashboard was opened.
