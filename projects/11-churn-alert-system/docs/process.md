# Weekly retention and churn-risk process

Owner roles are suggestions. Steps 1-6 and 8 are automated by `python -m churnalert`; steps 7 and 9-11 are human work that this code
does not perform. The code sends nothing.

| # | Step | Owner role | Tool | Input | Output | Decision / fork | Failure handling |
|---|---|---|---|---|---|---|---|
| 1 | Fetch and verify data | Data / GTM engineer | `fetch_data.py` (in production: billing or order export) | Source file | Verified local file | Hash matches? yes: continue; no: stop | Hash mismatch raises an error; do not analyse an unverified file |
| 2 | Load and bucket rows | GTM engineer | Python, `sql/01_lines.sql` | Line items | Each row in exactly one bucket | Overlap, no id, non-merchandise, zero value, or analysed | Missing column or empty required value stops the load |
| 3 | Reconcile | RevOps | `sql/05_checks.sql` | SQL tables | Pass/fail per check | All balance to the penny? no: stop, publish nothing | `ReconciliationError` names the failed check |
| 4 | Retention reporting | RevOps | SQL views, `report.py` | Movements | GRR, NRR, waterfall, cohorts | Compare same months a year apart; never month-on-month for irregular buyers | If a definition changes, restate history and say so |
| 5 | Backtest and monitor | Data / GTM engineer | `backtest.py` | Past snapshots with closed labels | Precision at capacity, calibration, intervals | Model still ahead of the simple rules? no: fall back to the overdue rule | Unobserved label window raises an error |
| 6 | Score and build queue | GTM engineer | `queue.py` | Accounts as of the run day | Local CSV ranked by churn score, with reasons (value ranking is optional and less precise) | Alerted in last 28 days? yes: skip. No rule fired? mark SCORE_ONLY | Damaged history file stops the run; same-day rerun gives the same queue |
| 7 | Randomise a holdout | RevOps | Spreadsheet or CRM (not built) | Queue | Treat and control flags | Control accounts get business as usual | Record the assignment before any contact; never move an account between arms |
| 8 | Size the test | RevOps | `experiment.py` | Expected churn rate and effect | Accounts needed per arm | Reachable in a reasonable time? no: do not claim an effect | Report "unmeasured" |
| 9 | Triage and act | Customer success manager | CRM (not built), playbook | Treatment accounts | Contact, service fix or no action | RETURNS_UP: resolve service issue before any sales ask | Wrong or stale reason: record it and skip |
| 10 | Log the outcome | Customer success manager | CRM (not built) | Contact result | Reason heard, action, date | Known benign cause (seasonal buyer)? mark it | Missing log counts as not contacted |
| 11 | Review after 90 days | Head of customer success + RevOps | Report | Orders in the window, both arms | Retention by arm with interval | Keep, change or stop the motion | Inconclusive is a valid result; do not stop early on a good week |
