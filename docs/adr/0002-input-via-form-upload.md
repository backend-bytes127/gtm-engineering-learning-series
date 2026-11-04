# ADR-0002: Ingest source files through a form upload

Status: accepted
Date: 2026-11-04

## Context
The merge needs six Excel exports. The obvious n8n pattern, a "Read/Write Files from Disk" node, reads from a path inside the container. The container mounts only its own data volume, and n8n restricts file access to a sandbox directory by default.

## Decision
Use a **Form Trigger** with six file fields. n8n stores each upload as binary data under a property named after the field label (non-word characters replaced by `_`), and **Extract From File** nodes read each one. The Project 01 flow already used a Form Trigger for its ICP input, so this is consistent with the existing pattern.

## Alternatives considered
- **Bind-mount the data folder** into the shared n8n container. Requires editing a compose file that serves other workflows, and breaks on a clean checkout.
- **Copy files in with `docker cp`** before each run. Manual and error-prone.
- **Google Drive / S3 as the source.** Adds a credential and a network dependency to what is meant to be a self-contained lesson.
- **Webhook with raw binary.** Works, but a form gives non-technical users a UI at no extra cost.

## Consequences
- (+) Works on any clone with no volume configuration; reusable for any dataset; the same upload path is testable with a plain multipart POST (`scripts/e2e.py`).
- (+) Field labels become binary property names, so renaming a label is a breaking change. This is encoded in `build_workflow.py` (`FILES`).
- (-) A form submission is not a scheduled job. For recurring runs, swap the trigger for a Schedule + storage read; the six Code nodes do not change.
- (-) The result is downloaded from the execution, not returned to the browser. Returning a file through the Form ending node depends on `WEBHOOK_URL` being reachable, which was not the case in the target environment.
