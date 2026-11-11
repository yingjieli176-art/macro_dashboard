# Japan overnight-rate corridor

Display identity `japan_corridor` is inserted as chart 9, after the US/Japan relative-strength chart. Former charts 9–20 become 10–21. Stable chart identities and control keys are retained, and old source-audit numbering is migrated.

The figure uses four percent-per-annum series on one axis: BOJ Complementary Deposit Facility rate (reference floor), BOJ basic loan rate under the Complementary Lending Facility (reference ceiling), BOJ TONA volume-weighted average, and JSDA Tokyo Repo Rate overnight T+0 (trimmed reference-institution quotes). The two administered settings are steps; market rates are never forward-filled. The uniform deposit reference begins 2024-03-21; the older three-tier negative-rate regime is deliberately not assigned a single floor.

BOJ API identities are FM01/STRDCLUCON and IR01/MADR1Z@D. The independent daily TONA Excel releases supplement the slower historical API; final figures supersede provisional figures for the same date. The BOJ homepage confirms both current administered rates and their effective dates. Announced setting history carries its original BOJ decision URLs. JSDA's original workbook is explicitly checked for the overnight T+0 column, without substituting T+1 or longer terms.

`update-japan-corridor.yml` runs twice hourly around the Tokyo morning final release and afternoon/month-end provisional releases. Independent publisher failures preserve saved histories, successful observations are still published, and failed collection is retried. The full-source audit covers all four families and can invoke the collector to repair lag. The page reads snapshots without network calls and watches their revisions.

CLF quantity is not plotted: the daily liquidity-factor table's Loans item identifies CLF but does not by itself establish a complete same-definition gross-new-loan history. A net change must not be labeled as actual daily borrowing or replaced by zero. The chart notes disclose this limitation.
