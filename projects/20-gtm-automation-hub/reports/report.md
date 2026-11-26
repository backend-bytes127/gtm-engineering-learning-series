# Offline simulation report

Every payload here is **synthetic**. This is the Python reference, with an in-memory Slack. It does not call n8n or Slack.
The same webhook steps are run against n8n by `e2e/run_e2e.py`; see `reports/e2e.md`.

**32 of 32 webhook steps gave the expected status and outcome.**

| # | Route | Step | HTTP | Outcome | Posts accepted / tried |
|---|---|---|---|---|---|
| 1 | signal | valid signal | 200 | `delivered` | 1 / 1 |
| 2 | signal | exact replay | 409 | `replay` | 0 / 0 |
| 3 | signal | same event, new signature | 200 | `duplicate` | 0 / 0 |
| 4 | signal | body changed after signing | 401 | `bad_signature` | 0 / 0 |
| 5 | signal | timestamp 10 minutes old | 401 | `stale_timestamp` | 0 / 0 |
| 6 | signal | timestamp 10 minutes ahead | 401 | `stale_timestamp` | 0 / 0 |
| 7 | signal | unsigned | 401 | `missing_headers` | 0 / 0 |
| 8 | signal | signed, not JSON | 422 | `invalid_json` | 0 / 0 |
| 9 | signal | signed, NaN is not JSON | 422 | `invalid_json` | 0 / 0 |
| 10 | signal | signed, wrong fields | 422 | `invalid_schema` | 0 / 0 |
| 11 | signal | body over the size limit | 413 | `too_large` | 0 / 0 |
| 12 | signal | Slack down for all three tries | 502 | `delivery_failed` | 0 / 3 |
| 13 | signal | sender retries after the failure | 200 | `delivered` | 1 / 1 |
| 14 | signal | Slack fails once, retry works | 200 | `delivered` | 1 / 2 |
| 15 | signal | mention injection is escaped | 200 | `delivered` | 1 / 1 |
| 16 | pql | tier A lead is sent for review | 200 | `pending` | 1 / 1 |
| 17 | pql | same lead again | 200 | `duplicate` | 0 / 0 |
| 18 | pql | tier B lead is not sent | 200 | `not_routed` | 0 / 0 |
| 19 | pql | idempotency key does not match | 422 | `invalid_schema` | 0 / 0 |
| 20 | click | click with a forged signature | 401 | `bad_signature` | 0 / 0 |
| 21 | click | click by a user not on the list | 200 | `not_allowed` | 0 / 0 |
| 22 | click | approve | 200 | `approved` | 1 / 1 |
| 23 | click | click replayed | 409 | `replay` | 0 / 0 |
| 24 | click | second click on a decided lead | 200 | `already_decided` | 0 / 0 |
| 25 | pql | second lead | 200 | `pending` | 1 / 1 |
| 26 | click | dismiss | 200 | `dismissed` | 1 / 1 |
| 27 | click | click for a lead never sent | 200 | `unknown_lead` | 0 / 0 |
| 28 | click | not a button click | 200 | `unsupported_interaction` | 0 / 0 |
| 29 | pql | third lead | 200 | `pending` | 1 / 1 |
| 30 | click | reply URL on another host | 200 | `approved` | 0 / 0 |
| 31 | pql | lead while Slack is down | 502 | `delivery_failed` | 0 / 3 |
| 32 | click | no click possible on an unsent lead | 200 | `unknown_lead` | 0 / 0 |

## Churn digest input (invented, file dated 2026-11-23)

8 accounts, £13,832 score-weighted trailing revenue. Digest built for 2026-11-23.

| Primary reason | Accounts | Score-weighted revenue |
|---|---|---|
| OVERDUE | 3 | £5,600 |
| FEWER_ORDERS | 1 | £3,172 |
| RETURNS_UP | 1 | £1,638 |
| SCORE_ONLY | 1 | £589 |
| SPEND_DOWN | 1 | £2,112 |
| THIN_HISTORY | 1 | £720 |
