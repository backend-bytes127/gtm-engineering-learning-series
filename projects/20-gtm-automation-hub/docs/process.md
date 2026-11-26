# Signal-to-action operating process

Owner roles are suggestions. **Built** means code here does it and it ran against a local fake of Slack. **Not built** is a design only.

| # | Step | Owner role | Tool | Input | Output | Decision / fork | Failure handling | Status |
|---|---|---|---|---|---|---|---|---|
| 1 | Agree the payload contracts | GTM engineer with source owners | `hub/contracts.py`, `hub/churn.py` | Signal, PQL task and queue formats | Versioned contracts | Format changes: change both languages and rerun the tour | Unknown or bad fields are refused | Built |
| 2 | Create the Slack app | Slack workspace admin | `slack/manifest.json` | Manifest | App with one scope | More scopes shown than in the manifest? Do not install | Delete the app and start again | Manifest built |
| 3 | Set secrets | GTM engineer | `.env`, edited by hand | Random keys, webhook URL | Configured container | No key: every request gets 503 | Rotate any key that was exposed | Built (fail closed) |
| 4 | Prove the paths before going live | GTM engineer | `e2e/run_e2e.py` | Synthetic payloads | `reports/e2e.md` | Any check fails? Do not connect Slack | Fix and rerun in a new container | Built |
| 5 | Receive a signed event | Source system | Webhook | Signed bytes | Authenticated request | Bad or old signature: 401. Same signature: 409 | Nothing stored for 401 | Built |
| 6 | Validate and dedupe | n8n | Gate node | Authenticated request | Event to send | Invalid: dead letter. Seen: duplicate. Not tier A: not routed | One execution at a time keeps state consistent | Built |
| 7 | Deliver | n8n | HTTP node | Message | Slack post | Accepted? Mark as seen | Three tries, then dead letter and 502 | Built (fake endpoint) |
| 8 | Post the weekly digest | n8n schedule | Workflow A | Newest queue file | One digest | Any bad row? Post nothing. Older than 8 days? Add a warning | Failed run stays in the execution list | Built (run by hand; schedule not observed) |
| 9 | Review a lead | Sales-assist rep | Slack buttons | PQL alert | Approved or dismissed | Not on the allow-list, or already decided: no change | Forged or replayed click is refused | Logic built; real clicks not connected |
| 10 | Act on an approval | Sales-assist rep | CRM (not built) | Approved lead | Logged contact | Consent and identity present? | Record why not contacted | Not built |
| 11 | Check dead letters | GTM engineer | Workflow export | Dead-letter list | Repaired or discarded events | Payload fault: ask the source to fix. Delivery fault: sign again and resend | Only the newest 100 are kept, so check at least daily | Manual; no alert |
| 12 | Check the digest ran | Customer success lead | Slack, n8n executions | Monday | Digest seen | Missing or marked stale? Check the scoring job and n8n | Use the queue file directly | Not built |
| 13 | Review usefulness | GTM lead | Review meeting | Decisions, outcomes, holdout results | Keep, change or stop an alert | Alerts ignored? Reduce volume or stop | Never claim lift without a holdout | Not built |
