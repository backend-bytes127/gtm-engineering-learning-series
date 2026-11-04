# Architecture decision records

Short records of decisions that were non-obvious or costly to reverse. Format: context, decision, alternatives, consequences. Status is `accepted` unless stated.

| ADR | Decision |
|---|---|
| [0001](0001-python-reference-then-javascript-port.md) | Build a Python reference first, port to n8n JavaScript, prove equivalence with a parity check |
| [0002](0002-input-via-form-upload.md) | Ingest files through a form upload, not from disk |
| [0003](0003-guarded-union-find-for-identity-resolution.md) | Identity resolution with union-find plus a LinkedIn-identity guard |
| [0004](0004-mobile-only-phone-policy-with-corroboration.md) | Mobile-only phones; decide column trust by cross-source evidence |
| [0005](0005-generated-workflow-json-and-sanitized-exports.md) | Workflow JSON is generated; exports are sanitized before commit |
| [0006](0006-scraper-actor-selection.md) | Scraper actor selection under a free-tier constraint |
| [0007](0007-blank-over-guess-and-review-flags.md) | Leave unknown values blank; surface judgment calls as review flags |

## Template

```markdown
# ADR-NNNN: Title

Status: accepted | superseded by ADR-XXXX
Date: YYYY-MM-DD

## Context
## Decision
## Alternatives considered
## Consequences
```
