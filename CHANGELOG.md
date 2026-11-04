# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/). Versions are per repository.

## [1.0.0] - 2026-11-04

### Added
- Display-time masking of names, e-mails, phones and slugs in the notebook, sample README and diagram, with a test that fails if any sample identity becomes visible.
- Project 02 walkthrough notebook: every stage on the synthetic sample with charts (phone-column evidence, record-linking graphs, a job-change timeline), executed and committed with outputs, run as a test in CI (`make notebook`, `make notebook-test`).
- Project 01: LinkedIn ICP Scraper. ICP design and keyword matrix as data files, sanitized n8n workflow (form + manual trigger, Apify actor call, flatten, Google Sheets append).
- Project 02: Contact List Merge. Six-step n8n flow generated from source modules; Python reference implementation; golden-file output; JS/Python parity check; end-to-end test; algorithm, data-quality and rules-traceability documentation; visual build guide.
- Synthetic sample data generator and a README describing how the source exports look in Excel (the instructor dataset is not redistributed).
- Platform: pinned Docker Compose for n8n, Makefile, GitHub Actions CI, secret scanner with pre-commit hook, architecture and operations docs, seven ADRs.
