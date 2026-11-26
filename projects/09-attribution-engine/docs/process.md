# Operating process

Owner roles are suggestions. "Stop" means nothing is published until the step passes.

| # | Step | Owner role | Tool | Input | Output | Decision / fork | Failure handling |
|---|---|---|---|---|---|---|---|
| 1 | Agree the conversion and lookback | RevOps lead with finance | Written definition | CRM stages, sales cycle | One conversion definition, lookback in days | New definition? Restate history or start a new series | No agreement: do not report credit |
| 2 | Govern campaign naming | Marketing operations | UTM builder, naming sheet | Campaign briefs | Tagged links that say brand or non-brand and retargeting | Link fails the naming rule? Fix before launch | Untagged traffic is tracked as a data-quality metric |
| 3 | Export touches and conversions | Data engineer | Analytics and CRM exports | Landing events, CRM conversions | Events and journeys tables | Both sources complete for the period? | Missing days: stop and backfill |
| 4 | Normalise channels | GTM engineer | `attribution/channels.py` | URL and referrer | One channel per event | `unmapped` or `paid_search_unclassified` above the agreed limit? | Add a rule with a test; never relabel as direct |
| 5 | Build journeys at a point in time | GTM engineer | `attribution/journeys.py` | Events, conversions, lookback | Eligible touches, dropped-row counts, untracked conversions | Drop counts changed sharply? | Investigate clocks, time zones, identity joins |
| 6 | Attribute with every method | GTM engineer | `attribution/methods.py` | Journeys | Channel by method credit | Credit differs from conversions by even one unit? | `CreditError` stops the run |
| 7 | Cross-check in SQL | Analytics engineer | `attribution/sql/` | Same tables | Heuristic credit from SQL | Gap above 0.05 conversions? | Run stops; find which layer applies a different rule |
| 8 | Report the spread | GTM engineer | `python -m attribution` | Credit table | Low and high credit and cost range per channel | Methods agree or disagree? Agreement is still not proof of effect | Publish ranges, never one method alone |
| 9 | Pick what to test | Marketing leader and RevOps | Decision table | Spread, real spend, feasible sample sizes | Ordered test backlog | Enough volume to detect a lift that would change the budget? | If not: record "not measurable", consider a longer or broader test |
| 10 | Pre-register the holdout | Analyst, signed off by the budget owner | `docs/holdout-test-design.md` | Baseline rate, minimum lift | Written plan and decision rule | User-level or region-level? | Region tests need a separate analysis method |
| 11 | Run and monitor | Marketing operations | Ad and e-mail platforms | Assignment list | Delivery logs | Sample-ratio mismatch or holdout contamination? | Stop, fix, restart with a new salt |
| 12 | Analyse and decide | Analyst and budget owner | `attribution/holdout.py` | Outcomes by assigned arm | Incremental effect with interval; keep, cut or retest | Interval too wide for the rule? | Call it inconclusive; do not fall back to attribution as proof |
| 13 | Review quarterly | RevOps | Test log | Past tests, current spread | Updated backlog and caveats | Channel, audience or spend level changed? | Treat the old estimate as expired and retest |
