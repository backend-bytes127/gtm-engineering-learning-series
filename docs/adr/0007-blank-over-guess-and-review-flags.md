# ADR-0007: Leave unknown values blank; surface judgment calls as review flags

Status: accepted
Date: 2026-11-04

> Figures in this record were measured on the instructor-provided dataset the project was first built on (292 rows). That dataset is **not included** in the repository; a small synthetic sample is (see `projects/02-contact-list-merge/sample-data/README.md`).

## Context
Rule 5: "Enrich by filling a gap in one source from another. Leave a cell blank when no source has the value. Never guess." But some outputs are neither plainly known nor plainly unknown: an e-mail with a typo in the domain, a single-source direct-dial number, a possible job change with no hard link.

## Decision
- A cell is filled only from a value present in some source, after deterministic cleaning.
- A repair is allowed only when it is **confirmed by independent evidence** (an e-mail's `.con` becomes `.com` only if the corrected domain is a known company domain from ZoomInfo/Apollo).
- Anything that required judgment is emitted as a **review flag** with the person, the company and a reason, on the Audit node (n8n) and the `Review Flags` sheet (Python reference): repaired e-mails, personal-only e-mails, excluded uncorroborated phones, employer changes, missing LinkedIn slugs.
- Synonym mappings that change meaning slightly (Purchase Manager to Procurement Manager; "Co-Founder & CTO" to Chief Technology Officer) are listed in the project README under "worth a human look".

## Consequences
- (+) The output never contains a value that is not traceable to a source; reviewers get a short list instead of 90 rows to re-check.
- (-) More blanks than an aggressive approach: 30 of 90 mobiles, 8 of 90 LinkedIn URLs, 3 of 90 e-mails. That is the point; completeness can be bought with enrichment, correctness cannot be retrofitted.
