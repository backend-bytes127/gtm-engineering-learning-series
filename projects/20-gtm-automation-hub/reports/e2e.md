# End-to-end run against n8n 2.32.6

Run on 2026-11-26 (UTC) by `python e2e/run_e2e.py`.
Synthetic payloads; Slack replaced by a local fake.
Nothing here contacted Slack.

**48 of 48 checks passed.** For each webhook step, the HTTP status, outcome and every message sent
to the fake endpoint had to equal what the Python reference produced for the same signed bytes.

| Check | Result |
|---|---|
| signal: valid signal | pass |
| signal: exact replay | pass |
| signal: same event, new signature | pass |
| signal: body changed after signing | pass |
| signal: timestamp 10 minutes old | pass |
| signal: timestamp 10 minutes ahead | pass |
| signal: unsigned | pass |
| signal: signed, not JSON | pass |
| signal: signed, NaN is not JSON | pass |
| signal: signed, wrong fields | pass |
| signal: body over the size limit | pass |
| signal: Slack down for all three tries | pass |
| signal: sender retries after the failure | pass |
| signal: Slack fails once, retry works | pass |
| signal: mention injection is escaped | pass |
| pql: tier A lead is sent for review | pass |
| pql: same lead again | pass |
| pql: tier B lead is not sent | pass |
| pql: idempotency key does not match | pass |
| click: click with a forged signature | pass |
| click: click by a user not on the list | pass |
| click: approve | pass |
| click: click replayed | pass |
| click: second click on a decided lead | pass |
| pql: second lead | pass |
| click: dismiss | pass |
| click: click for a lead never sent | pass |
| click: not a button click | pass |
| pql: third lead | pass |
| click: reply URL on another host | pass |
| pql: lead while Slack is down | pass |
| click: no click possible on an unsent lead | pass |
| dead letters are saved with their reasons | pass |
| a failed delivery keeps the event for repair | pass |
| saved state holds no secret and no delivery URL | pass |
| decisions are saved | pass |
| n8n itself rejects malformed JSON labelled as JSON, before the signature gate | pass |
| dedupe survives an n8n restart | pass |
| churn: manual run succeeds | pass |
| churn: digest equals the Python reference | pass |
| churn: Slack down fails the run after three tries | pass |
| churn: bad amount posts nothing and fails | pass |
| churn: wrong columns posts nothing and fails | pass |
| churn: header only posts nothing and fails | pass |
| churn: empty inbox posts nothing and fails | pass |
| container logs hold neither signing secret | pass |
| container logs hold no delivery URL, even after failed sends | pass |
| a missing secret rejects requests (fails closed) | pass |

## Concurrency and timing measurements (limits, not passes)

One machine, one run. The counts vary between runs.

| n8n concurrency setting | Measurement | Result |
|---|---|---|
| limit 1 (this project's default) | 20 copies of one identical request sent at once: Slack posts (1 is correct) | 1 |
| limit 1 (this project's default) | 20 different events sent at once: delivered | 20 |
| limit 1 (this project's default) | of those, delivered a second time when re-sent later, because their record was overwritten | 0 |
| limit 1 (this project's default) | replays sent immediately after the first answer, out of 10, that were delivered again | 0 |
| no limit (n8n's own default) | 20 copies of one identical request sent at once: Slack posts (1 is correct) | 20 |
| no limit (n8n's own default) | 20 different events sent at once: delivered | 20 |
| no limit (n8n's own default) | of those, delivered a second time when re-sent later, because their record was overwritten | 19 |
| no limit (n8n's own default) | replays sent immediately after the first answer, out of 10, that were delivered again | 0 |
