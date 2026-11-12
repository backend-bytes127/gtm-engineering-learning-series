# Deploying to Railway, and sending for real

## What runs where

One Railway service built from the `Dockerfile`: the web app, a background loop that sends due messages once a minute, and a SQLite file on a volume mounted at `/data`. Nothing else.

## Variables (set in the Railway dashboard; never commit them)

| Variable | Required | Purpose |
|---|---|---|
| `APP_PASSWORD` | yes | The single login password (12+ characters). The server refuses to start on a public address without it |
| `SESSION_SECRET` | yes | Signs the login cookie (32+ characters). Changing it signs everyone out |
| `HOST`, `DATA_DIR` | set | `0.0.0.0` and `/data` |
| `UNIPILE_API_KEY` | for live sending | Unipile API v2 key |
| `UNIPILE_ACCOUNT_ID` | for live sending | The id of your connected LinkedIn account in Unipile |
| `UNIPILE_WEBHOOK_SECRET` | for replies | Signing secret of the Unipile webhook endpoint |
| `LIVE_MAX_INVITES_PER_DAY` | optional | Live cap, default 3 (never above 25) |
| `LIVE_MAX_MESSAGES_PER_DAY` | optional | Live cap, default 5 (never above 100) |

## Connecting LinkedIn (you do this in your browser)

1. In the Unipile dashboard, connect your LinkedIn account through their hosted login. Unipile, not this app, holds the LinkedIn session. Copy the **account id**.
2. Create an **API key** and add `UNIPILE_API_KEY` and `UNIPILE_ACCOUNT_ID` to the service. It redeploys.
3. Replies: in Unipile, add a webhook endpoint for `message.new` pointing to `https://<your-domain>/api/webhooks/unipile`, copy its signing secret into `UNIPILE_WEBHOOK_SECRET`. The webhook is public but every request is checked with an HMAC signature over the raw body and a 5-minute window; anything else gets a 401.

## AI drafting and autonomous replies (optional)

Set `ANTHROPIC_API_KEY` (and optionally `ANTHROPIC_MODEL`, default `claude-opus-5-5`, and `AI_DAILY_CALL_CAP`, default 100) to turn on the AI assistant. Then use the **Inbox** page: **Off**, **Review** (Claude drafts, you approve) or **Autonomous** (Claude writes and sends within your limits). Start in Review. Details and the safety rules: [ADR-0010](../../../docs/adr/0010-autonomous-ai-messaging-with-code-level-guardrails.md). The key is read only from the environment and never stored in the database or sent to the browser.

## Safety rails in live mode

- Real sending is a separate, explicit step ("Send for real") after the launch checklist passes. It is refused if a simulation was already run on the project.
- You pick the people. At most 10 at a time; nobody else is ever contacted.
- A **preflight** looks each person up on LinkedIn first and tells you whether an invite or a direct message will go out. It sends nothing.
- Daily caps come from the environment, are further limited by the sending rules, and cannot be raised from the browser.
- **Stop sending** is a kill switch that takes effect on the next tick.
- Rate limits, checkpoints and "invite already pending" are handled without marking the contact as failed. A person who is already a connection skips the invite and gets the message.

## What is verified and what is not

Verified by tests (no network): request shapes, error handling, caps, allow-list, signature checking, reply matching, stop rules. The request shapes are the ones outbound-os verified live against Unipile v2.

Not verified until you run it with a real account: that Unipile's `message.new` payload carries the sender's id in the field we read (`sender_id`, falling back to `sender.id`), and that your plan allows the calls. The first live test with one person is exactly that check; if replies don't register, look at the app logs.

## Operating notes

- The login is one shared password. It is built for one person, not a team.
- Data lives on the volume; redeploying keeps it. "Start over" in the app deletes it.
- Automated LinkedIn activity can breach LinkedIn's terms and get an account restricted. Keep the numbers small and the people consenting.
