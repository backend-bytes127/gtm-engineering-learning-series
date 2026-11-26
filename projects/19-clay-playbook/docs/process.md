# Operating process: account enrichment and ICP scoring in Clay

Owner roles are suggested. In the build behind [the README](../README.md) one operator did every step, once. Steps 11 and 12 are recommended practice and were **not** performed.

| # | Step | Owner role | Tool | Input | Output | Decision / fork | Failure handling |
|---|---|---|---|---|---|---|---|
| 1 | Agree the ICP and the spend cap | RevOps with sales lead | Document | Target definition, budget | Filter values, score rules, maximum credits | Is the signal worth its price? If not, stop at free scoring | No agreed cap or owner: do not run paid columns |
| 2 | Record balances | GTM engineer | Clay Settings > Usage | None | Starting data credits and actions | Enough balance for the ceiling (rows x price, per paid step)? | If the balance cannot be read, stop |
| 3 | Search companies | GTM engineer | Clay company search | Industry, HQ country, size band | A match count and a preview | Do the preview rows look like the ICP? | Too broad: tighten filters. Record that the saved rows are not a random sample |
| 4 | Save a small table | GTM engineer | Clay | Search, custom row count (25) | Company table | Save to table, with no enrichment ticked | Wrong destination or ticked enrichment: go back before saving |
| 5 | Make runs manual | GTM engineer | Table Auto-run setting | New table | Manual table, no schedules | Any scheduled column? | A schedule exists: remove it before going on |
| 6 | Clean and score | GTM engineer | Formula columns | Source fields | Domain Clean, Vendor Model, Fit Score, Reason Codes, Tier | A or B goes to step 7; C and DQ stop. The keyword rule behind the tier is unvalidated | Formula preview wrong or blank: fix before saving. Unclear vendor model stays visible, never assumed to be product |
| 7 | Configure paid step 1 | GTM engineer | Clay enrichment | Domain Clean, 90 days, limit 10 | Unrun paid column with run condition | Column Auto-run off, condition and referenced columns visible | Condition missing after reopening: add it again, do not save without it |
| 8 | Test, then run step 1 | GTM engineer | Clay run controls, usage history | One blocked row, one passing row, then the rest | Job counts or no-result cells | Blocked row shows "Run condition not met" and the passing row behaves as expected? | No: stop. Unclear price, or the ceiling would break the cap: stop. Errors: read them before any re-run, since re-run billing is untested |
| 9 | Run step 2 on misses | GTM engineer | Second provider | Rows still empty after step 1 | Second job count or no-result cells | Start only when step 1 is complete; test one miss and one hit | Step 1 incomplete or errored: do not start step 2. This provider billed misses in the build |
| 10 | Merge, flag and reconcile | GTM engineer, then RevOps | Hiring Signal formula, usage history, Settings > Usage | Both outputs, starting balances | One status per row, cost by column, ending balances | Balance change matches table usage? Count implausible for company size? | Mismatch: stop runs and investigate other activity. Implausible count: REVIEW_COUNT, no routing |
| 11 | Review before use (not performed) | Sales development lead | Company websites, careers pages | REVIEW_COUNT rows, a sample of unclear and tier C rows | Confirmed, corrected or excluded accounts | Is the signal about this company and relevant to the offer? | Cannot confirm: treat as no signal |
| 12 | Decide whether to repeat (not performed) | RevOps | Review notes, cost record | Coverage, errors, cost per usable signal | Keep, change or drop the signal; date of next manual run | Does the signal change what a rep does? | No: drop the paid column. Scheduling needs a separate approval and cap |

## Status values

| Value | Meaning | Action |
|---|---|---|
| `HIRING_PROVIDER_1` | Step 1 reported 1 to 100 open jobs | Look at relevance before prioritising |
| `HIRING_PROVIDER_2` | Step 1 count empty or zero, step 2 reported jobs | Same; check step 2's count for plausibility, which the formula does not do |
| `REVIEW_COUNT` | Step 1 reported more than 100 | Check which entity the domain belongs to |
| `NO_JOBS_FOUND` | No count from either column. Confirm both cells actually ran without errors | No timing signal; not proof of no hiring |
| `NOT_CHECKED` | Did not pass the fit gate | Make no statement about hiring |
