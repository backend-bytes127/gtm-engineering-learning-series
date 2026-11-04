# Data-quality catalogue

Every defect pattern found in the six exports, grouped by kind, with how it is handled and where. Use it as a checklist when you meet a new lead source: most real exports contain the same families of problems.

People shown here are fictional; where a specific person is named they are given by initials.

> Figures in this record were measured on the instructor-provided dataset the project was first built on (292 rows). That dataset is **not included** in the repository; a small synthetic sample is (see `projects/02-contact-list-merge/sample-data/README.md`).

## 1. Text and encoding

| Defect | Example | Handling |
|---|---|---|
| Leading/trailing whitespace in any cell | `'  Orbexa Fintech '`, `' name@x.com  '` | trim in every field |
| Case noise | `SRINIVAS KAMATH`, `rajesh menon` | proper-case per token (`D'Souza` aware) |
| Salutations, credentials, pronouns, badges | `Dr. A. Saxena`, `Mr. Mei Iyer`, `CA Anjali ...`, `Name, MBA`, `Name (He/Him)`, `Name (Open to Connect)` | stripped in `clean_name` |
| Emoji and decorations | `Kapoor 🚀` | stripped; also the private-use character n8n's reader substitutes for 4-byte emoji |
| `Last, First` ordering (with credentials in between) | `Joshi, MBA, Gaurav` | credentials dropped first, then swapped |
| Broken first/last split by the scraper | first `Mary Anne`, last `Anne D'Souza` | names are chosen from candidates that match the LinkedIn slug; a structured pair is used only if it reproduces the chosen name |
| Spelling variants of one person | `Mohd`/`Mohammed`, `Kate`/`Katherine`, `Srinivas`/`Shrinivas`, `Laxmi`/`Lakshmi`, `Vicky`/`Vikram` | linked via alias map plus a second check; final spelling follows the LinkedIn slug |

## 2. E-mail

| Defect | Handling |
|---|---|
| Several addresses in one cell (`person@x.com; info@x.com`) | split; generic role mailboxes (`info@`, `sales@`, ...) dropped |
| `mailto:` prefix | stripped |
| Stray space before `@` (`name @x.com`) | inner whitespace removed |
| Doubled `@@` | collapsed |
| TLD typo (`.con`), missing TLD (`@rangoramedia`) | repaired only if the corrected domain is a known company domain; otherwise dropped |
| Vendor placeholder `email_not_unlocked@domain.com` | rejected |
| Test/spam addresses (`.invalid`, `test@test.com`) | rejected, and the record is removed |
| Personal address (gmail) as the only contact | used only if no work address exists, and flagged |
| Work address at a **previous** employer | ranked below the current employer's address |
| Vendor-guessed addresses (Apollo status *Extrapolated*) | treated like any other work address (see "worth a human look" in the README) |

## 3. Phone

| Defect | Example | Handling |
|---|---|---|
| Formatting noise | `98763 18896`, `512.555.0151`, `(415) 555-0125`, `1-617-555-0131` | digits extracted; only parentheses containing letters are removed |
| Annotations | `8698340544 (WhatsApp)` | annotation removed |
| International prefix forms | `006590940021`, `00971501654295`, `919237647520` (no `+`) | `00` and country-code-without-plus recognised |
| Trunk zero | `09408608428` | stripped for India and UAE |
| Excel scientific notation | `9.18772E+11` | rejected; digits already lost |
| Placeholders and junk | `NA`, `-`, `Not shared`, `0000000000`, `1234567890`, `9999999999` | rejected |
| Landlines | `080-43057296` | rejected by STD-code pattern |
| Number typed into a notes column | `Send deck. Mob 9542367611` | extracted as a candidate |
| Leading apostrophe (Apollo text cells) | `'+91 82556 16194` | stripped |
| Wrong column semantics | Apollo *Corporate*, ZoomInfo *Direct*, Apollo *Work Direct* | measured against other sources: [ADR-0004](../../../docs/adr/0004-mobile-only-phone-policy-with-corroboration.md) |
| 8-digit local numbers | `Mob 84728256` (Singapore) | country taken from the person/company |

## 4. Company, title, size, location

| Defect | Example | Handling |
|---|---|---|
| Legal suffixes | `Pvt Ltd`, `Private Limited`, `Inc.`, `Pte. Ltd.`, `LLC` | stripped before matching |
| Typos | `Oakmere Sofwtare`, `Tarangi oFods`, `Dunecrest Tehcnologies` | fuzzy match (threshold 0.86; measured margin in [algorithms.md](algorithms.md#company-names-match_company)) |
| Short forms | `Zentrova`, `Marinabay`, `Veltrix` | unique word-prefix match |
| Abbreviated titles | `Mktg Manager`, `Sr Mgr - Sales`, `V.P. Sales`, `C.M.O.`, `CRO` | expansion table |
| Different word order | `Marketing Director` / `Director - Marketing` / `Dir. of Mktg` | structural templates give one canonical form |
| Headline text glued to the title | `Mgr - Marketing \| Building in public` | cut at `\|` |
| Synonyms | `Purchase Manager` / `Procurement Manager` | mapped (review item) |
| Founder prefixes | `Founder & CEO`, `Co-Founder & CTO` | dropped (review item) |
| Size as words or ranges | `201 to 500`, `1001-5000 employees`, `SMB`, `Enterprise`, `Mid-Market` | numbers/ranges bucketed; labels with no number yield nothing |
| Conflicting sizes between sources | 340 (ZoomInfo) vs 512 (Apollo) | ZoomInfo wins |
| City aliases | `Bangalore`, `BLR`, `Madras`, `Calcutta`, `Gurgaon`, `Amdavad`, `DXB`, `SF` | alias table to the current official name |
| LinkedIn region strings | `Greater Chennai Area`, `Pune/Pimpri-Chinchwad Area`, `Delhi NCR` | keyword detection |
| Contact's city mistaken for HQ | a contact lives in one city, the employer's HQ is another | HQ taken only from company-level columns |
| Website variants | `www.x.com`, `http://www.x.com/path?utm=...` | root domain |

## 5. LinkedIn

| Defect | Handling |
|---|---|
| Country subdomain (`uk.`, `in.`), `http`, no scheme | normalized to `https://www.linkedin.com/in/<slug>` |
| `/en` suffix, trailing slash, `utm_*` parameters | stripped |
| Sales Navigator lead URLs (`/sales/lead/ACwAA...,NAME_SEARCH,...`) | not a public identity; the `ACwAA` id is kept only as a linking key |
| Profile URL is an `ACwAA` id but another column has the real slug | the real slug is used |
| Hidden profiles (`LinkedIn Member`) | removed |

## 6. Dates

| Defect | Handling |
|---|---|
| Four formats (ISO, `dd/mm/yyyy HH:MM`, `mm/dd/yyyy, hh:mm AM`, `yyyy-mm-dd HH:MM:SS IST`) | one parser per source |
| Event delegate rows have no date | the event's last day |
| ZoomInfo has no dates at all | treated as oldest for employer/title; still first for company facts |
| Apollo date is an e-mail verification stamp, sometimes empty | used when present; empty ranks oldest |

## 7. Structure and layout

| Defect | Handling |
|---|---|
| Event workbook has two sheets (delegates, booth scans) in different schemas | read as two sources |
| Title banner rows above the header and a summary footer (`Total Delegates: 37`) | header offset of 4 rows (numeric range in the Extract node); rows without a numeric `S.No` skipped |
| Fully blank rows | skipped |

## 8. Entities

| Pattern | Handling |
|---|---|
| Exact duplicate rows within one export | collapsed by the grouping step |
| Same person in up to 8 records across files | strong keys, then name + company + title |
| Several scraper snapshots of one person (same Sales Nav id, different timestamps and slightly different titles) | linked by `ACwAA` id; the latest snapshot wins for title |
| Same name, same company, different people | kept apart (different titles; different LinkedIn slugs; merge refused) |
| Same name, different company | kept apart unless same city and flagged as a job change |
| Personal-e-mail record and work-e-mail record of one person | linked through the shared mobile |
| Employer changed between exports | latest dated source decides employer, title and which e-mail is "current" |

## 9. Invalid or out-of-scope rows (9 removed + deferred checks)

| Pattern | Count | Reason logged |
|---|---|---|
| Test flag / test strings (`Is test = TRUE`, `asdf`) | 3 | test/spam lead |
| Student or freelancer, company `Student` / `Self` | 2 | job seeker / freelancer |
| Hidden `LinkedIn Member` | 4 | hidden LinkedIn Member |
| Event delegates with a blank organisation | 7 (**kept**) | company filled from another source; dropped after merge only if no source has one |
