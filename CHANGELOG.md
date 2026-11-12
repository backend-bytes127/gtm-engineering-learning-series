# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/). Versions are per repository.

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
