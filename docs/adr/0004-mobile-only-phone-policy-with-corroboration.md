# ADR-0004: Mobile-only phones; decide column trust by cross-source evidence

Status: accepted
Date: 2026-11-04

> Figures in this record were measured on the instructor-provided dataset the project was first built on (292 rows). That dataset is **not included** in the repository; a small synthetic sample is (see `projects/02-contact-list-merge/sample-data/README.md`).

## Context
The Rules require "E.164, mobile only: no board lines or direct lines". Sources expose several phone columns with unreliable labels. Taking the Rules literally ("ignore anything labelled direct") and taking the labels on faith both give wrong answers.

## Decision
Treat each phone column as a hypothesis and **measure it**: for every number in a candidate column, check whether the same number appears in any other source for the same data set.

| Column | Corroborated by other sources | Decision |
|---|---|---|
| Apollo "Corporate Phone" | 0 of 28 | Board lines. Excluded |
| ZoomInfo "Direct Phone Number" | 0 of 7 | Direct lines. Excluded |
| Apollo "Mobile Phone" | n/a | Trusted |
| ZoomInfo "Mobile phone" | n/a | Trusted |
| Apollo "Work Direct Phone" | 10 of 11 | Mislabelled mobile column (it never co-occurs with Mobile Phone). Accepted **only when another source agrees** |
| Forms, event contact numbers, phone typed into notes | n/a | Accepted after format validation |

Parsing rejects placeholders (`NA`, `-`), repeated or sequential digits (`1234567890`), Excel scientific-notation damage (`9.18772E+11`, digits already lost), and STD-coded landlines (`080-43057296`). Validation is per country (India, US, UK, UAE, Singapore) after normalizing trunk prefixes and `00` international prefixes.

## Alternatives considered
- **Trust labels.** Would discard 10 real mobiles hiding in "Work Direct".
- **Accept every number that parses.** Would publish 28 board lines and 7 direct lines as mobiles.
- **Accept Work Direct unconditionally.** Right 10 times out of 11, but the 11th (a number with no other source) is exactly the case the Rules warn about.

## Consequences
- (+) The decision is reproducible: the evidence is a script-level count, recorded here.
- (+) One uncorroborated number is left blank and flagged in the audit rather than guessed.
- (-) A person whose only mobile sits in a "Work Direct" column and appears nowhere else gets a blank. That is the intended conservative behavior.
