# ADR-0003: Identity resolution with union-find and a LinkedIn-identity guard

Status: accepted
Date: 2026-11-04

> Figures in this record were measured on the instructor-provided dataset the project was first built on (292 rows). That dataset is **not included** in the repository; a small synthetic sample is (see `projects/02-contact-list-merge/sample-data/README.md`).

## Context
283 valid records describe 90 people. The Rules say two records are the same person when e-mail or LinkedIn slug matches, and that name plus company alone "needs a second check, because different people can share a name". The data deliberately includes:

- two different people with the same name at the **same company** (different titles, different LinkedIn slugs);
- two people with the same name at **different** companies;
- one person with a personal and a work e-mail, linked only by a phone number;
- people who changed employer between sources (same slug, different company);
- nicknames and spelling variants ("Vicky"/"Vikram", "Mohd"/"Mohammed").

## Decision
Use **union-find** over record indices with three tiers, applied in order:

1. **Strong keys** (exact): normalized e-mail, E.164 mobile, public LinkedIn slug, Sales Navigator `ACwAA` id.
2. **Name + company + compatible title** (pairwise): same alias-normalized first name and surname, same canonical company, and titles equal or one side empty. This is the "second check".
3. **Job-change link** (pairwise, flagged): same name, *different* company, same canonical city. Logged as `job-change (verify)`.

Every union passes a **guard**: refuse to merge two groups whose non-empty LinkedIn slug sets (or `ACwAA` id sets) are disjoint. A refusal is logged as `REFUSED merge`.

## Alternatives considered
- **Connected components on a graph of shared keys only.** Equivalent to tier 1; cannot link a record that has no key in common (e.g. an event row with a company but no e-mail match).
- **Probabilistic matching (Fellegi-Sunter, or a trained matcher).** More robust at scale, but needs labelled pairs, and the rules here are explicit and auditable. Revisit for lists in the tens of thousands.
- **Merge on name + company without the title check.** Would merge the two same-name colleagues. The title check is what keeps them apart.

## Consequences
- (+) Deterministic and explainable: every merge is a logged link with a reason; the guard makes the dangerous case (two real people) structurally impossible whenever LinkedIn identities are known.
- (+) Linear in keys; the pairwise tiers are O(n²) over 283 records (about 40,000 comparisons), well under a second.
- (-) The guard only protects when slugs are present. Two slug-less same-name colleagues with compatible titles would merge. Mitigation: documented; titles usually differ.
- (-) Tier 3 is a heuristic (one assumed job change in the data is flagged for human review). It is the one place a false merge is plausible.
- Scale note: beyond a few thousand records, replace the pairwise loops with **blocking** (bucket by surname key + company) and compare only within buckets.
