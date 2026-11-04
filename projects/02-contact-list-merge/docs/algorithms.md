# Algorithms and implementation notes

How each stage of the Contact List Merge works, why it works that way, and where it would break. Code references are to the Python reference (`pipeline/`) and the n8n JavaScript (`n8n/src/`); the two implement identical behavior and are checked against each other (`make parity`).

> Figures in this record were measured on the instructor-provided dataset the project was first built on (292 rows). That dataset is **not included** in the repository; a small synthetic sample is (see `projects/02-contact-list-merge/sample-data/README.md`).

Contents: [1 Record model](#1-common-record-model) · [2 Cleaning](#2-cleaning) · [3 Standardization](#3-standardization) · [4 Identity resolution](#4-identity-resolution) · [5 Enrichment and merge](#5-enrichment-and-merge) · [6 Complexity and scaling](#6-complexity-and-scaling) · [7 Failure modes](#7-failure-modes)

## 1. Common record model

Seven sheets, six different schemas. Step 1 maps each row into one shape (`Rec` in Python, a plain object in JS):

| Field | Meaning |
|---|---|
| `source`, `ref` | Provenance: which file and row the record came from |
| `date` | When the *source* observed this information (UTC epoch ms). Used for recency |
| `first`, `last`, `full` | Names. `first/last` only where the source has structured names |
| `emails[]` | Raw strings (may contain several addresses) |
| `phones[]` | Pairs `(raw, kind)`; `kind` is `mobile` (a column whose contents are trusted mobiles), `self` (typed by the person or event staff), or `apollo_direct` (see [ADR-0004](../../../docs/adr/0004-mobile-only-phone-policy-with-corroboration.md)) |
| `company`, `title` | Raw strings |
| `slug`, `acwaa` | Public LinkedIn slug; Sales Navigator internal id |
| `person_loc`, `country` | The person's location (not the company's) |
| `co_*` | Company facts the source asserts: size, website, HQ city/country |

**Dates.** The sources disagree on format and timezone, which matters because Rule 3 ("most recent dated source wins") compares them:

| Source | Raw | Interpretation |
|---|---|---|
| Google Ads | `2026-10-12 13:09:15 IST` | local time, converted to UTC (-5:30) |
| Event scans | `18/09/2026 13:25` | day-first, IST |
| Event delegate list | none per row | the summit's last day (2026-09-19) |
| LinkedIn form | `10/04/2026, 01:48 AM` | month-first, 12-hour |
| Scraped LinkedIn | ISO `...Z` | UTC |
| Apollo | `Primary Email Last Verified At` | the only date available; may be empty |
| ZoomInfo | none populated | treated as the **oldest** possible, so any dated source outranks it for employer/title |

Using the correct day/month order matters: `10/04/2026` is 4 October in the LinkedIn form but `10/04` in a scan would be 10 April. Each loader owns its own format.

## 2. Cleaning

### Names (`clean_name`)
1. Strip emoji (and, in JS, the private-use range `U+E000-U+F8FF` that n8n's xlsx reader substitutes for 4-byte emoji).
2. Remove parenthetical text: pronouns `(He/Him)` and badges `(Open to Connect)`.
3. Split on commas; drop credential parts (`MBA`, `PMP`, `CSPO`, ...). If exactly two parts remain, treat as `Last, First` and swap.
4. Drop leading salutation tokens (`Mr`, `Ms`, `Dr`, `CA`) as long as at least one token remains.
5. Proper-case every token, handling apostrophes (`d'souza` becomes `D'Souza`).

### E-mail (`split_emails`, `classify_email`)
- Lowercase, strip `mailto:`. Split a multi-address cell on `;`/`,`/whitespace **only where an address follows** (lookahead `(?=\S+@)`), so `name @domain.com` (a stray space) is not split.
- Remove inner whitespace; collapse `@@`.
- Classify: `invalid` (placeholder `email_not_unlocked@domain.com`, test domains, `.invalid`), `generic` (`info@`, `sales@`, ... role mailboxes are not people), `ok`, or `repaired`.
- **Repair** (`.con` to `.com`, or a missing TLD) is allowed only if the corrected domain is a **known company domain** taken from the ZoomInfo/Apollo `Website` column. Otherwise the address is dropped. This makes repair evidence-based rather than a guess ([ADR-0007](../../../docs/adr/0007-blank-over-guess-and-review-flags.md)).

### LinkedIn (`linkedin_slug`, `linkedin_acwaa`)
Extract `linkedin.com/in/<slug>` regardless of scheme, country subdomain (`uk.`, `in.`), `/en` suffix, trailing slash or tracking parameters, then lowercase. A slug beginning `acwa` is a Sales Navigator internal id, not a public identity: it is kept as a separate **`acwaa` key** (useful for linking scraper snapshots of the same person) and never published.

### Invalid records (`invalid_reason`)
Test flags and test strings (`\b(test|asdf|qa)\b`, `.invalid`), job seekers/freelancers, hidden `LinkedIn Member` profiles, and placeholder companies (`Self`). **A blank company is not rejected here**: the person may be identified and given a company by another source. Clusters that still have no company after merging are dropped in step 5.

## 3. Standardization

### Company names (`match_company`)
Goal: map `Oakmere Sofwtare`, `Veltrix Mobility PVT LTD`, `Zentrova`, `Kiranat Education` onto the canonical ZoomInfo/Apollo name.

1. Normalize: lowercase, strip emoji, strip legal suffixes (`pvt ltd`, `private limited`, `inc.`, `pte. ltd.`, `llc`, ...), twice, longest suffix first.
2. Exact match on the normalized canonical name.
3. **Unique word-prefix match**: `zentrova` is a prefix of exactly one canonical name (`zentrova logistics`).
4. Otherwise the best **Ratcliff-Obershelp similarity** (`difflib.SequenceMatcher.ratio()`) on space-squashed strings; accept at **>= 0.86**.

The JavaScript contains a faithful port of the matcher (longest-matching-block recursion, with the same tie-breaking) so that borderline decisions are identical in both implementations. **Measured margin on the sample data:** eight strings reach the fuzzy step; every one scores 0.917 to 0.952 against its correct company, and the best *wrong* candidate for any of them scores at most 0.619. The two most similar distinct companies in the universe (`Dunecrest Technologies` / `Quillbyte Technologies`) score 0.667. The threshold of 0.86 therefore has a wide safety margin here; it is a tunable constant and should be re-measured on a larger company universe.

### Job titles (`canonical_title`)
Goal: `Dir. of Mktg`, `Marketing Director`, `Director - Marketing`, `Mgr - Procurement | Helping B2B teams scale revenue` all map to one spelled-out form.

1. Drop headline text after `|`, remove dots, tokenize letters.
2. Drop filler (`of`, `and`, `team`, `co`, `founder`, ...) and **expand abbreviations** (`mgr`, `dir`, `sr`, `vp`, `mktg`, `biz`, `dev`, `rev`, `revops`, `sdr`, `cro`/`cto`/`ceo`/..., `purchase`).
3. Apply structural templates:
   - contains `chief` → `Chief <Function> Officer`
   - `vice president` → `Vice President of <Function>`; `director` → `Director of <Function>`; `head` → `Head of <Function>`
   - `manager` → `[Senior ]<Function> Manager`; `lead` → `<Function> Lead`
   - otherwise title-case the tokens
   where `<Function>` is the remaining tokens in order (`Demand Generation`, `Revenue Operations`).

Because the output is a canonical string, titles from different sources are directly comparable. That is what makes the "compatible title" check in step 4 a string equality.

Judgment calls encoded here (each documented as a review item): `purchase` is read as `procurement`; founder prefixes are dropped (`Co-Founder & CTO` becomes `Chief Technology Officer`).

### Mobile numbers (`parse_mobile`)
A small, explicit decision procedure that returns `(E.164 or None, reason)`:

```
placeholder (NA, -, "Not shared")           -> reject
scientific notation (9.18772E+11)           -> reject   (Excel already destroyed the digits)
"x.0" float artifact                        -> strip ".0"
landline pattern ^0\d{2,4}-\d{6,8}$         -> reject   (STD code, e.g. 080-43057296)
remove "(WhatsApp)" but keep "(415)"         (only parentheses containing letters are removed)
digits = non-digits removed
all-same or sequential digits (last 10)      -> reject   (0000000000, 1234567890)
starts with "+"      -> "+" + digits
starts with "00"     -> "+" + digits[2:]            (international prefix)
else                 -> national number using the person's country
                        India: strip one trunk "0", need 10 digits;  +91
                        US: 10 digits;  +1            Singapore: 8 digits;  +65
                        UAE: strip trunk "0", 9 digits;  +971
validate against per-country mobile pattern
  IN +91[6-9]\d{9}   US +1\d{10}   GB +447\d{9}   AE +9715\d{8}   SG +65[89]\d{7}
```

The country comes from the best available evidence: the record's own country, then its city, then the **company's HQ country**. Landline detection relies on the hyphenated STD format in the raw cell; once hyphens are gone, `080-43057296` is indistinguishable from the mobile `8043057296`, which is why detection happens before digit extraction.

### Company size, website, location
- **Size**: numbers and ranges map to the Rules buckets (`1-10 ... 10,001+`); a range uses its midpoint. Marketing labels (`SMB`, `Enterprise`, `Mid-Market`) have no numeric content and yield nothing.
- **Website**: strip scheme, `www.`, path, query; lowercase. LinkedIn company URLs are never used as a website.
- **City/country**: alias table (`Bangalore`/`BLR` to `Bengaluru`, `Madras` to `Chennai`, `Calcutta` to `Kolkata`, `Gurgaon` to `Gurugram`, `Amdavad` to `Ahmedabad`, `DXB` to `Dubai`, ...) plus keyword detection inside LinkedIn region strings (`Greater Chennai Area`, `Pune/Pimpri-Chinchwad Area`). HQ is the **company's** city, never the contact's.

## 4. Identity resolution

Design rationale in [ADR-0003](../../../docs/adr/0003-guarded-union-find-for-identity-resolution.md). Mechanics:

```
groups = union-find over record indices; each root tracks the set of slugs and acwaa ids in its group

union(i, j):                                            # returns False (and logs REFUSED) if unsafe
    if both groups have slugs and the slug sets are disjoint:    refuse
    if both groups have acwaa ids and the id sets are disjoint:  refuse
    attach root j under root i, union the slug/acwaa sets

pass 1  strong keys:   for each record, for each of e-mail / E.164 mobile / slug / acwaa:
                           key seen before -> union(first record with that key, this record)
pass 2  name + company + title (i < j):
                           same alias-normalized first name + surname,
                           same canonical company,
                           titles equal OR one empty   -> union, log "name+company+title"
pass 3  job change (i < j):
                           same name, DIFFERENT company, same canonical city -> union, log "job-change (verify)"
```

Why the pieces exist:

- **Phone as a key** links a person's personal-e-mail record to their work-e-mail record when nothing else connects them.
- **`acwaa`** links successive scraper snapshots of the same person, which carry the same Sales Navigator id even when the public slug is hidden.
- **Name alias map** (`vicky`→`vikram`, `kate`→`katherine`, `mohd`→`mohammed`, `srinivas`→`shrinivas`, `laxmi`→`lakshmi`) lets a nickname join the formal record, but only inside pass 2 where company and title provide the second check.
- **The guard** is what keeps two real people who share a name, company and even a mailbox from collapsing into one. It is exercised by `test_merge_refused_when_linkedin_slugs_differ_even_if_email_shared`.

Output of the step: 90 person groups and 24 link decisions (23 `name+company+title`, 1 `job-change`), each with the two source rows and a note, so every non-trivial merge can be audited.

## 5. Enrichment and merge

For each group:

### Employer and title (Rule 3)
```
records with a company, sorted by date descending (undated = oldest; ties keep input order)
employer = company of the first record
title    = title of the first record AT THAT EMPLOYER that has a title
```
Taking the title from the same employer prevents an old employer's title from attaching to the new employer.

### Company facts (Rule 4)
```
Website  : ZoomInfo rows for the company -> Apollo rows -> (nothing else asserts a website)
HQ       : ZoomInfo company city/country -> Apollo -> scraped companyLocation
Size     : ZoomInfo employees -> Apollo -> forms/event ranges, in that order; bucket the number
```
Each pick is the **most common** value among that source's rows (ties: first seen), so one stray row cannot override the source's consensus.

### Name
Candidates are the cleaned full names from all records. If a LinkedIn slug exists, candidates are filtered to those whose letters equal the slug's name part (`mohammed-aslam-df7f8c62` selects `Mohammed Aslam` over `Mohd Aslam`; `mary-anne-d-souza` selects `Mary Anne D'Souza`). Remaining candidates are ranked by frequency, then by source structure (LinkedIn form > ZoomInfo > Apollo > scraper > event > ads). First and last names come from a record that has structured fields reproducing the chosen name, which is how two-word given names (`Mary Anne`) and two-word surnames (`Singh Rathore`, `De Silva`) and single initials (`R`) are kept intact; otherwise split at the first space.

### E-mail
Each distinct address is scored `((on current employer's domain, is a work address), number of records that contain it, latest date)`; the highest tuple wins. A work address on the current employer's domain therefore beats a personal address and an address at a previous employer. Flags are raised for repaired addresses, personal-only addresses, and a work address on a previous employer's domain.

### Mobile
Numbers are collected with their `kind`. A number seen **only** in Apollo's Work Direct column is excluded and flagged; otherwise the winner is the number that appears in a trusted `mobile` column, then by number of supporting records.

### Result
Groups with no company in any record are dropped; the rest are sorted by company, surname, first name and emitted with `_flags` and `_merged_from` for the audit node.

## 6. Complexity and scaling

| Stage | Cost | n = 283 |
|---|---|---|
| Parse and standardize | O(n) (company matching is O(n x canonical companies)) | negligible |
| Strong-key pass | O(n) with a hash map | negligible |
| Pairwise passes | O(n²) | about 40,000 comparisons, well under 1 s |
| Merge | O(n log n) (sorts) | negligible |

At around 10⁴ records or more, replace the pairwise passes with **blocking**: bucket records by (surname key, canonical company) for pass 2 and (surname key, city) for pass 3, and compare only within buckets. At around 10⁵ and beyond, move to a dedicated matcher (and a database), and consider probabilistic scoring.

## 7. Failure modes

| Risk | When it happens | Current mitigation |
|---|---|---|
| False merge of two same-name colleagues | Both lack LinkedIn slugs *and* have compatible titles | Titles usually differ; flagged review item in the docs |
| Assumed job change is wrong | Pass 3 fires on name + city when the two records are really different people | Logged as `job-change (verify)`; exactly one in the sample |
| Fuzzy company match picks the wrong company | A typo equidistant from two canonical names | Threshold 0.86 and a unique-prefix rule; unknown companies stay unmatched and the record keeps only what it has |
| Phone column mislabelled in a new vendor export | New data source | Re-run the corroboration measurement from ADR-0004 before trusting a column |
| Date format changes in a source | New export version | Each loader owns its format; the Step 1 node would yield `null` dates, which rank oldest, a silent degradation to watch |
| Timezone ambiguity | LinkedIn form dates have no timezone | Used as-is; only relative order matters and the sources overlap by days |
