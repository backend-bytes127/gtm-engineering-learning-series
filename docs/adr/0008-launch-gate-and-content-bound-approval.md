# ADR-0008: Nothing goes live until a launch gate passes; approval is bound to the exact content

Status: accepted
Date: 2026-11-10

## Context
Project 03 sends messages to real people on someone's real mailbox and LinkedIn profile. The brief says that before a sequence goes live every contact must be checked, every message personalised, and the limits and stop rules set. Mistakes here are not recoverable: a wrong or empty-placeholder message cannot be un-sent, and a restricted LinkedIn account is the sender's actual profile. outbound-os already had the idea of a gate decision before any send; this project makes it explicit.

## Decision
- `launch_checklist` is a pure read of the database with six items: contacts validated, sequence well-formed, every template approved, every (contact, step) draft renders without a missing variable, sender profile set, limits/hours/stop rules set. `launch` raises unless all six pass.
- Approval stores a SHA-256 of `channel + subject + body`. Editing an approved template changes the hash, which silently un-approves it. `tick` re-checks the hash on **every send**, not just at launch, so a template edited after launch is blocked rather than sent.
- A draft that cannot be personalised (a variable with no value and no fallback) blocks the launch by default. `--hold-incomplete` parks just those contacts (`Stopped`, reason `draft_incomplete`) and launches the rest, so one gap in the data does not hold up everyone.
- Unsubscribe is always a stop rule. The other three (reply, bounce, meeting) can be narrowed in the rules, but a legal opt-out cannot be switched off.

## Alternatives considered
- **A flag on the sequence ("approved: true").** Cheap, but it goes stale the moment someone edits a template.
- **Send with empty placeholders or generic fallbacks.** Produces "Hi , I saw that  is growing". Rejected: a skipped contact is better than a bad message.
- **Hard-fail the whole launch on any missing data, no escape hatch.** Safe but impractical on real lists, which always have gaps.

## Consequences
- (+) The failure modes that cannot be undone are blocked in code, and each block names the contact and the missing field.
- (+) The gate is testable without sending anything.
- (-) More ceremony than a typical sequencer: a template must be re-approved after any edit, including typo fixes. That is the intent.
