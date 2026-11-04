# ADR-0001: Python reference first, JavaScript port second, parity check between them

Status: accepted
Date: 2026-11-04

> Figures in this record were measured on the instructor-provided dataset the project was first built on (292 rows). That dataset is **not included** in the repository; a small synthetic sample is (see `projects/02-contact-list-merge/sample-data/README.md`).

## Context
The production logic must run inside n8n Code nodes (JavaScript, no local imports, no filesystem). Debugging data-cleaning rules inside the n8n editor is slow: each iteration is a click-through of upload, run and inspect, and there is no test runner.

## Decision
1. Implement the full pipeline first as a Python package (`pipeline/`) with unit tests, an output-format test suite and a golden-file test.
2. Port the same rules to JavaScript modules (`n8n/src/`), structured as one file per workflow step plus shared helpers.
3. Add a **parity check** that runs the *generated* Code-node source in plain Node against the real data and diffs the result with the Python golden output.
4. Add an **end-to-end test** in a clean n8n container to cover what the harness cannot (n8n's own nodes).

## Alternatives considered
- **Write JavaScript only and test through n8n.** Fewer lines, but every rule change costs a manual round trip, and there is no regression safety net.
- **Run Python from n8n** (Execute Command / Python Code node). Avoids the port, but the Python Code node and the shell are not available in every n8n deployment, and it couples the workflow to a runtime that the container may lack.
- **Unit-test the JavaScript directly with a JS test framework.** Viable and cheaper to maintain, but loses the independent second implementation, which is what catches porting mistakes.

## Consequences
- (+) Fast red/green loop for rule changes; coverage measured (98% of the reference).
- (+) Two implementations written independently agree on 90 of 90 rows, which is strong evidence both are right. The port surfaced no logic differences, only environment ones.
- (+) The harness found nothing the e2e test missed and the e2e test found two things the harness could not (n8n range semantics, emoji decoding), so both layers earn their place.
- (-) Every rule lives in two languages. Mitigation: the contributing guide requires changing both and CI runs parity.
- (-) Some code is ported literally, including a port of Python's `difflib.SequenceMatcher` ratio, to keep fuzzy company matching decisions identical.
