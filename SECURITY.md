# Security and data handling

This repository teaches GTM automation, which routinely touches API tokens, OAuth clients and personal data. The rules below keep it safe to publish.

## Never commit

| Item | Why | Where it lives instead |
|---|---|---|
| API tokens (Apify, Google, Slack, ...) | Account takeover, billing abuse | n8n credential store (encrypted with `N8N_ENCRYPTION_KEY`) |
| OAuth client files (`client_secret*.json`) | Contains a client secret | Entered once in the n8n credential UI |
| `.env` files | Holds the n8n encryption key | Local only; `.env.example` documents the keys |
| Raw n8n workflow exports | Carry owner e-mail, internal ids, sheet ids, credential ids | Use `sanitize_n8n_export.py` first |
| Real personal data (scraped profiles, customer lists) | Privacy law and platform terms | Keep outside the repo; use synthetic data |
| Unblurred screenshots of real data | Identifies people | Pixelate before committing |

## Enforced automatically

`scripts/check_no_secrets.py` scans the working tree for token patterns, Google OAuth client ids and secrets, spreadsheet ids, private keys, home-directory paths, e-mail addresses and forbidden file names. It runs:

- locally on every commit, once you enable the hook: `make hooks`
- on demand: `make secrets`
- in CI on every push and pull request

## n8n deployment notes

- The compose file binds n8n to `localhost` and sets `N8N_SECURE_COOKIE=false` because it serves plain HTTP. **Do not expose that port to a network.** Put TLS in front of it before any shared use.
- The encryption key in `.env` protects stored credentials. Back it up with the volume; losing it makes saved credentials unreadable.
- Form triggers are unauthenticated by default. Add form authentication or network controls before pointing a form at real data.

## If a secret is ever committed

1. Revoke or rotate it at the provider immediately. Deleting the commit is not enough; assume it was copied.
2. Remove it from history (`git filter-repo`) only after rotating.
3. Add a pattern to `scripts/check_no_secrets.py` so it cannot recur.

## Reporting

Open a private security advisory on the repository, or contact the maintainer directly. Do not open a public issue containing a secret.
