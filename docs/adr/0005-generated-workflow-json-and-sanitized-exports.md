# ADR-0005: Workflow JSON is generated; exports are sanitized before commit

Status: accepted
Date: 2026-11-04

## Context
An n8n workflow is a JSON file that embeds each Code node's source as a string. Hand-editing it is error-prone, diffs are unreadable, and a raw `export:workflow` file carries instance metadata: owner project name and e-mail, internal ids, version counters, the Google spreadsheet id and credential ids.

## Decision
1. **Source of truth is `n8n/src/*.js`.** `build_workflow.py` generates the workflow JSON. Node ids are a stable hash of the node name, so rebuilds are byte-identical. CI rebuilds and fails on any diff.
2. **Never commit a raw export.** `sanitize_n8n_export.py` keeps only `id`, `name`, `nodes`, `connections`, `settings`, replaces credential ids with a placeholder (names kept so the right credential is obvious), and replaces any 40+ character id-like string (spreadsheet ids) with `YOUR_GOOGLE_SHEET_ID`.
3. The secret scanner independently fails the build on spreadsheet-id-shaped strings and OAuth client material.

## Alternatives considered
- **Commit raw exports.** Leaks identifiers and creates noisy diffs.
- **Keep Code node source in separate files and let n8n load them.** n8n has no such mechanism for Code nodes without custom nodes or a community package.
- **n8n source control (Git integration).** Requires an enterprise license, and it commits to a repo from the instance rather than letting us gate what is published.

## Consequences
- (+) Reviewable diffs on readable source; reproducible artifact; nothing instance-specific escapes.
- (-) A build step between editing and importing. `make build-workflows` takes under a second.
- (-) After import, credentials must be selected once in the UI. This is by design: credentials are not portable.
