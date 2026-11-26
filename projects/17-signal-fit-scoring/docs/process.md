# Operating process

One row per step, so it can be loaded into a process tool. Owner roles are suggestions.

| Step | Owner role | Tool | Input | Output | Decision / fork | Failure handling |
|---|---|---|---|---|---|---|
| 1. Fetch and verify data | GTM engineer | `fetch_data.py` | Public source | Files in `data/raw/` | Hash matches? yes: continue; no: stop | A changed hash means old results are not comparable. Review the source before updating the hash |
| 2. Agree the point in time and field list | RevOps lead with sales and privacy owners | `fitscore/config.py` | Data dictionary | Allowed and excluded fields, each with a reason | Known before the first call and allowed by policy? no: exclude | If the timing of a field cannot be shown, exclude it |
| 3. Write the simple rules first | Sales manager | `config/scoring.json` | Team judgement | Points rules, recorded before later results | None | If nobody can state a rule, use "earlier success first" |
| 4. Choose the model | Analyst | `python -m fitscore` | Months before the test period | Selection table | Boosted beats logistic by 0.01 or more? yes: it is the headline; the best logistic is still shipped for reason codes | Fewer than two outcome classes in the history: stop |
| 5. Backtest month by month | Analyst | `fitscore/backtest.py` | All months | `reports/report.md` | Interval for model minus rule excludes zero at the capacity cut, with months resampled? yes: consider the model; no: keep the rule | A result that looks too good: run the leakage ladder and find the field |
| 6. Decide what to run | Head of sales and RevOps | Report | Short-answer table | Rule or model, and a review date | On this data: keep the rule as the ranking in use; run the model in shadow | No agreement: keep the current rule |
| 7. Score the new batch | GTM engineer | `python -m fitscore score` | CSV with `row_id` and fields | Ranked CSV with tier, reasons, unknowns | Batch rank (default) or fixed thresholds | Invalid numbers or ids stop the run. Blank or unseen values are neutral and listed |
| 8. Work the queue | Sales reps | CRM (not built here) | Ranked CSV | Call attempts | A first, then B; C low-touch | A rep who disagrees with a reason code records why |
| 9. Explore | Sales manager | `explore_sample` column | B and C rows | Randomly chosen rows to work anyway | Row flagged? yes: work it at normal effort | If skipped, record it: later training data will be biased |
| 10. Record outcomes | RevOps | CRM export (not built here) | Attempts and results | One outcome per row, with date | Outcome mature? no: leave it out of training | Missing outcomes are unknown, never "lost" |
| 11. Monitor monthly | Analyst | Report, monthly and tier tables | New month | Drift and lift review | Tier A lift near 1.0, or win rate or tier sizes move sharply? yes: stop using the score and fall back to the rule | Log the month and the cause if known |
| 12. Fairness and privacy review | Privacy owner | Field policy and leakage ladder | Proposed field changes | Approval or refusal | Protected or proxy field? yes: needs a documented decision | Default is to leave it out. This project has **not** tested proxy effects |

Steps 8 to 10 describe what a team would need to do. No CRM connection exists in this repository.
