# Changelog

## Projects 07, 09, 11, 17, 19, 20 and industry guides

- Added product-qualified lead scoring, attribution, revenue retention and churn, account scoring with a backtest, a Clay playbook, a Slack and n8n automation hub, and four industry GTM guides.
- 07, 09, 11, 17 and the guides went through an independent review and its fixes before publication. 19 and 20 were checked by the integrator only.

## Corrections after an independent review

- 03: the stop-request check missed common wording ("please stop", curly apostrophes) and most non-English requests. Added Dutch, German, French and Spanish basics, and routed data-erasure requests to suppression plus a person.
- 04: companies are no longer upserted on `domain` (not a unique HubSpot property); they are searched, then updated or created. Partial failures (HTTP 207) are no longer reported as success. `Retry-After` is honoured and creates are not repeated after a 5xx.
- 02: non-Latin surnames were stripped to nothing and could merge different people; accents are now folded and other scripts kept. A missing surname never matches.
- Coverage figures now exclude test files. The project 15 draft was removed (wrong and unsourced claims).

Format: [Keep a Changelog](https://keepachangelog.com/). Versions are per repository.

## [Unreleased]

### Added
- Project 04: Contact Cleaning App. A web app over Project 02's pipeline: upload the six exports, clean, standardize and consolidate, download the workbooks, and get a HubSpot update plan (match on e-mail and domain, blanks never sent, rows without e-mail skipped). A real push is off by default and needs a startup flag, a typed confirmation and a matching portal id. Deployable as a public no-login demo: isolated in-memory sessions per visitor with expiry and a run cap, no disk writes, and the server refuses to run publicly with a HubSpot token. 56 tests, 96% coverage.

### Changed
- Project 02 `pipeline/run.py` is split into `consolidate`, `write_final` and `write_audit` so other code can reuse it; output is unchanged.

## [1.1.0] - 2026-11-10

### Fixed
- Launch with `--hold-incomplete` no longer parks contacts when the launch is then refused for another reason.

### Added
- Project 03 AI messaging: Claude drafts step messages and replies in Off, Review or Autonomous mode, with code-level guardrails (opt-out detection, needs-human keywords, output checks, disclosure, reply caps), an inbox screen, and ADR-0010.
- Excalidraw diagrams and synthetic UI screenshots for project 03.
- Project 03 hosting and live sending: password login (fails closed), Dockerfile and Railway config, a Unipile LinkedIn provider (offline-tested), guarded live mode with preflight, allow-list, caps and a kill switch, a signed reply webhook, and a background scheduler. Skip and retry-later verdicts in the engine.
- Project 03 web app (`python3 -m sequencer serve`, `make sequencer-app`): a screen per step of the brief, built with the standard library and plain JavaScript modules, with API and front-end guard tests.
- Project 03: Outreach Sequencer. Import and column mapping, contact validation (e-mail, LinkedIn URL, duplicates, opt-outs, suppression list), sequence and template definitions with a linter and per-contact draft checks, a launch gate with approval bound to a content hash, sending rules (daily limits, hours, stop rules), a status and touch tracker in SQLite, a deterministic simulated provider, and a report by step and channel with a "what worked" summary. 262 tests, 98% coverage, golden-file check, independent SQL recount of the report.
- ADR-0008 (launch gate and content-bound approval) and ADR-0009 (provider interface and simulated sending).
- `make sequencer-demo`; project 03 in `make test`, `make lint` and CI.

## [1.0.0] - 2026-11-04

### Added
- Display-time masking of names, e-mails, phones and slugs in the notebook, sample README and diagram, with a test that fails if any sample identity becomes visible.
- Project 02 walkthrough notebook: every stage on the synthetic sample with charts (phone-column evidence, record-linking graphs, a job-change timeline), executed and committed with outputs, run as a test in CI (`make notebook`, `make notebook-test`).
- Project 01: LinkedIn ICP Scraper. ICP design and keyword matrix as data files, sanitized n8n workflow (form + manual trigger, Apify actor call, flatten, Google Sheets append).
- Project 02: Contact List Merge. Six-step n8n flow generated from source modules; Python reference implementation; golden-file output; JS/Python parity check; end-to-end test; algorithm, data-quality and rules-traceability documentation; visual build guide.
- Synthetic sample data generator and a README describing how the source exports look in Excel (the instructor dataset is not redistributed).
- Platform: pinned Docker Compose for n8n, Makefile, GitHub Actions CI, secret scanner with pre-commit hook, architecture and operations docs, seven ADRs.
