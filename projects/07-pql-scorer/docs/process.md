# PQL operating process

How a team would run this. **Built** means this repository has code for it. **Not built** is a design only: nothing here connects to a CRM, a messaging tool or an experiment platform.

| # | Step | Owner role | Tool | Input | Output | Decision / fork | Failure handling | Status |
|---|---|---|---|---|---|---|---|---|
| 1 | Agree the event contract | Product analyst with GTM engineer | `tracking_plan.json`, code review | Product events and their meaning | Versioned tracking plan | New or changed event: update the plan before the product ships it | Change without a plan update fails validation | Built (file) |
| 2 | Validate the feed | GTM engineer | `pql.tracking_plan` | Raw events | Clean events and violation counts | Over 1% of rows broken? Stop | Quarantine and count bad rows; stop the run; fix at source | Built |
| 3 | Monitor event volume | Product analyst | Dashboard or alert | Daily counts per event | Alert | A key event drops sharply? Pause routing | Fall back to no action until explained | Not built |
| 4 | Pick who to score and when | GTM engineer with sales lead | `pql.cohort` | Clean events | Eligible visitors at first event + 30 min | Already bought or automation-like? Exclude | Count every exclusion | Built (batch) |
| 5 | Build features | GTM engineer | `pql.features` | Events up to the cut-off | One feature row per visitor | Any later event present? Refuse | Raise an error; do not score | Built (batch) |
| 6 | Retrain and compare | Data analyst | `python -m pql` | Labelled history with embargo | Model, rules comparison, report | Does boosting beat logistic by the stated bar? Does the model beat the points rule enough to be worth running? | If not, ship the simpler option | Built |
| 7 | Check calibration and drift | Data analyst | Report sections 10 and 12 | Recent labelled period | Bin table, weekly table | Predicted and observed far apart? Recalibrate on a fresh period | Keep the previous version | Report built; schedule not built |
| 8 | Set thresholds from capacity | Sales-assist and lifecycle leads | `pql.routing.fit_thresholds` | Validation scores, daily capacities | Score thresholds and version | Capacity changed? Refit on a past period only | Reject empty input | Built |
| 9 | Route in time order | RevOps | `pql.routing.route` | Scores and decision times | Tier A, B or none | Tier full today? Next tier down | Missing score: error, never silent routing; count overflow | Built (replay) |
| 10 | Assign experiment arm | GTM engineer | Stable hash of visitor id and experiment name | Routed visitors | Action or holdout | Holdout: no action | Log assignment before acting; check sample ratio | Not built (check function built) |
| 11 | Create the task or audience | RevOps | CRM or messaging API | Action-arm visitors with consent | Task or audience entry | No identity or no consent? No contact | Idempotency key as a database unique key; retry safely | Dry run built, in memory only |
| 12 | Act | Sales assist or lifecycle | Chat, e-mail or ads tool | Task | Logged touch | Visitor already bought? Cancel | Record non-delivery; keep in intention-to-treat | Not built |
| 13 | Read the experiment | Product analyst | `pql.experiment`, analysis notebook | Assignments and 7-day outcomes | Lift with interval, guardrails | Sample reached plus 7 days? Sample ratio sound? | Broken ratio: discard and fix assignment | Design built; no data |
| 14 | Decide | GTM lead | Review meeting | Lift, cost, margin, guardrails | Keep, change or stop the action | Lift below break-even? Stop | Keep a small permanent holdout | Not built |
