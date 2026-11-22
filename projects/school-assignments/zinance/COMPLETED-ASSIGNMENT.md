# Zinance Assignment — Clay System Design for 100K Accounts

**Course:** GTM Engineering — Cohort 1 (GTME.SCHOOL)
**Assignment:** Sep 7th Zinance Assignment
**Company:** Zinance (outsourced finance: AI + human accountants for SMBs)
**Challenge:** Design a Clay-based system to process 100K prospect accounts, find 2 DMs per account, and generate personalized outbound copy.

---

## Overview

Zinance sells outsourced bookkeeping and finance operations to small US businesses whose founders are still doing their own books. The bottleneck is not finding prospects — it is qualifying 100K raw accounts down to ones that actually fit, finding the right person at each one, and writing copy that doesn't read like a template.

This document designs the full Clay table system: qualification, contact discovery, personalization variable generation, and the 3-email sequence.

---

## Section 1: Account Qualification System

### Target Profile

Zinance's ideal account is a US business where the founder is still the de facto head of finance because they can't afford or don't yet need a full-time CFO. That means:

| Dimension | In | Out |
|---|---|---|
| Headcount | 1–50 employees | >100 (finance dept likely exists) |
| Funding | Bootstrapped, pre-seed, seed | Series B+ (they have a CFO) |
| Geography | United States | International |
| Industries | Construction, professional services, e-commerce, law firms, healthcare practices, real estate agencies, creative agencies, logistics/freight brokers | SaaS (usually VC-backed, finance-forward), enterprise, government |
| Finance team | 0–1 people in finance/accounting on LinkedIn | Has a CFO, Controller, or Head of Finance on LinkedIn |

### Clay Table: Account Qualification Steps

**Input:** 100K company rows (name, domain, headcount, industry, location, funding round, LinkedIn URL)

**Step 1 — Hard filters (Clay filter view)**
Apply before running any enrichment to avoid wasting credits:
```
headcount <= 50
AND country = "United States"
AND industry NOT IN ["Enterprise Software", "Defense", "Government", "Pharmaceuticals"]
AND funding_stage NOT IN ["Series B", "Series C", "Series D", "IPO"]
```
Expected output: ~40K accounts pass (60% filtered out on hard criteria)

**Step 2 — LinkedIn headcount enrichment (Clay → LinkedIn)**
Pull headcount breakdown by department. Focus column: employees in Finance, Accounting, or Operations titles.
- Clay column: `finance_dept_count` (integer, sourced from LinkedIn headcount data)
- Filter: `finance_dept_count <= 1`

Expected output: ~25K accounts pass

**Step 3 — Negative signal check (Clay → LinkedIn People Search)**
Check if the company has any of these titles currently on LinkedIn:
- CFO / Chief Financial Officer
- Controller / VP of Finance / Head of Finance
- VP Finance

Clay column: `has_finance_exec` (true/false via "People at Company" enrichment, filtered to finance titles)
Filter: `has_finance_exec = false`

Expected output: ~18K accounts pass

**Step 4 — AI qualification score (Clay → Claude via AI Ark)**

Prompt template for each row:
```
Company: {{company_name}}
Industry: {{industry}}
Headcount: {{headcount}}
Funding: {{funding_stage}}
Finance team size (LinkedIn): {{finance_dept_count}}

Score this company 1–10 on how likely it is that the founder is personally handling finance and would benefit from outsourced bookkeeping. 10 = perfect fit (small, no finance staff, founder-led). 1 = poor fit (large, finance team exists, VC-backed).

Return JSON: {"score": <integer>, "reasoning": "<one sentence>"}
```

Clay columns: `ai_score` (integer), `ai_reasoning` (text)
Filter: `ai_score >= 7`

Expected output: ~12K accounts advance to contact discovery (~12% of original 100K)

### Expected Pass Rate Summary

| Stage | Accounts Remaining | % of 100K |
|---|---|---|
| Raw input | 100,000 | 100% |
| Hard filters (headcount, geo, funding) | 40,000 | 40% |
| Finance dept headcount ≤ 1 | 25,000 | 25% |
| No finance exec on LinkedIn | 18,000 | 18% |
| AI score ≥ 7 | 12,000 | 12% |

---

## Section 2: Decision-Maker Discovery

For each of the 12K qualified accounts, find 2 contacts using Clay's "Contact at Company" enrichment, run twice with different title targeting.

### Primary DM — Founder / CEO / Owner

**Clay step:** "Contact at Company" enrichment
**Target titles:** Founder, Co-Founder, CEO, Owner, President, Managing Director
**Priority logic:** If multiple matches, prefer: Founder > CEO > Owner > President

Output fields per row:
| Field | Source |
|---|---|
| `dm1_first_name` | Clay contact data |
| `dm1_last_name` | Clay contact data |
| `dm1_title` | Clay contact data |
| `dm1_email` | Apollo waterfall → Prospeo fallback |
| `dm1_email_status` | Prospeo verification (verified / unverified / risky) |
| `dm1_linkedin_url` | Clay contact data |

### Secondary DM — Operations / Finance-Adjacent

**Clay step:** "Contact at Company" enrichment (second run)
**Target titles:** VP Operations, Operations Manager, COO, Head of Operations, Office Manager, Director of Operations
**Priority logic:** Skip if same email as DM1

Output fields per row:
| Field | Source |
|---|---|
| `dm2_first_name` | Clay contact data |
| `dm2_last_name` | Clay contact data |
| `dm2_title` | Clay contact data |
| `dm2_email` | Apollo waterfall → Prospeo fallback |
| `dm2_email_status` | Prospeo verification |
| `dm2_linkedin_url` | Clay contact data |

### Email Validation Waterfall

For each contact, run in this order and stop when verified:
1. **Apollo** — `POST /v1/people/match` with LinkedIn URL
2. **Prospeo** — `bulk-enrich-person` with `only_verified_email: true`
3. If neither returns verified — mark `email_status = unverified`, include in sequence but monitor bounce rate separately

### Duplicate Detection

After both enrichment runs:
- If `dm1_email == dm2_email` → blank out DM2 fields, flag `dm2_duplicate = true`
- Expected duplicate rate: ~8% of accounts

---

## Section 3: Personalization Variables

Shubh's key insight: personalization that scales must use **fixed variables** — data points you can pull programmatically for every row — not one-off research. The AI's job is to turn those data points into natural-language sentences, not to invent facts.

### Variables and Sources

| Variable | Description | Clay Source |
|---|---|---|
| `{{headcount}}` | Total employee count | Clay company data / LinkedIn |
| `{{finance_dept_headcount}}` | Estimated finance/accounting team size | AI Ark estimate from LinkedIn headcount breakdown |
| `{{funding}}` | Funding stage or "bootstrapped" | Crunchbase via Clay enrichment |
| `{{employee_name}}` | Name of a recently-hired ops or finance employee | "Recent hires" enrichment or LinkedIn new hire data |
| `{{industry_label}}` | Human-readable industry (e.g. "construction firm") | Clay company category, reformatted |

### AI Ark: Finance Headcount Estimation

Clay column: `finance_headcount_line`

Prompt:
```
Company: {{company_name}}
Total headcount: {{headcount}}
Industry: {{industry}}
Known finance/accounting employees on LinkedIn: {{finance_dept_count}}

Write a single natural sentence (under 15 words) about the size of their finance team for use in a cold email.
Examples:
- "most {{headcount}}-person {{industry_label}}s run finance with one or two people"
- "with {{headcount}} people, you're probably still the one reconciling the books"
- "at {{headcount}} employees, most {{industry_label}}s don't have a dedicated finance team yet"

Return only the sentence, no quotes.
```

### AI Ark: Research Line Generation

Clay column: `research_line`

Prompt:
```
Company: {{company_name}}
Industry: {{industry_label}}
Headcount: {{headcount}}
Funding: {{funding}}
Recent hire: {{employee_name}} ({{employee_title}}) — leave blank if none

Write a single opening line (under 20 words) that shows you looked at this company.
It must reference a verifiable fact, not a compliment.
Examples:
- "found {{company_name}} while mapping {{headcount}}-person {{industry_label}}s in the US"
- "noticed {{company_name}} just brought on {{employee_name}} as {{employee_title}}"
- "came across {{company_name}} while looking at bootstrapped {{industry_label}}s"

Return only the sentence.
```

---

## Section 4: Outbound Copy System

### ICP Summary
Founders and owners of 1–50 person US businesses. They handle their own bookkeeping or have one part-time bookkeeper. They're spending 5–10 hours a week on tasks that don't generate revenue: reconciliation, invoices, payroll prep, expense categorization.

### Offer
Zinance replaces their bookkeeping and finance ops with a combination of AI automation and a dedicated human accountant. The founder pays a flat monthly fee and gets clean books, monthly reports, and a CFO-level contact they can call.

### Subject Line (same across all 3 emails)
`{finance timing|quick note|books question}`

---

### Email 1 — Decision Maker (Founder/CEO)

**Hook:** H6 Insider Question — make them think before they reply

**Word count target:** under 90 words

```
Hi {{firstName}},

{{research_line}}

{{finance_headcount_line}} — which usually means the founder's still the one closing the books at month end.

Zinance replaces that with AI-assisted bookkeeping and a dedicated accountant, for a flat fee. No onboarding calls, no annual contract.

Worth a quick look for {{companyName}}?

{{sendingAccountName}}

P.S. {happy to be pointed to whoever handles this if it isn't you|no worries if the timing's off, just let me know}
```

---

### Email 2 — End User (Operations Manager / COO)

**Hook:** H2 Second Job — name the hidden workload

**Word count target:** under 100 words

```
Hi {{firstName}},

Found {{companyName}} while mapping {{headcount}}-person {{industry_label}}s — most ops leads I talk to end up carrying a chunk of the finance work even when that's not in the job description.

Zinance takes the reconciliation, payroll prep, and monthly close off the team. AI handles the data layer, a human accountant handles the judgment calls.

We've set this up for a few {{industry_label}}s. It usually takes a week to be fully live.

Worth a conversation?

{{sendingAccountName}}

P.S. {easy to point me to the right person if that's helpful|no pressure, just let me know either way}
```

---

### Email 3 — Champion (Office Manager / Admin)

**Hook:** H9 Two Quick Things — lowest friction ask

**Word count target:** under 60 words

```
Hi {{firstName}},

Two quick things:

1 — Zinance handles bookkeeping and finance ops for {{headcount}}-person businesses like {{companyName}}, flat fee, no long contract.

2 — We only charge once the books are clean and the founder's signed off.

Would it make sense to put together a one-page breakdown for {{companyName}}?

{{sendingAccountName}}
```

---

### Pre-Send Checklist

Before any row goes to the sequencer:
- [ ] `research_line` is about them, not a compliment
- [ ] `finance_headcount_line` does not state something that could be wrong (e.g. "you have 0 finance staff" when `finance_dept_count` is null — use a softer inference)
- [ ] No em dashes, colons, or exclamation marks in any body field
- [ ] `{{sendingAccountName}}` stripped before Email Bison push
- [ ] `dm1_email_status` is verified or explicitly reviewed if unverified
- [ ] Word count verified per email (use AI Ark: "count the words in this email body")

---

## Section 5: Clay Table Architecture

### Full Column Map

```
INPUT COLUMNS
─────────────
company_name          | string  | raw import
domain                | string  | raw import
headcount             | integer | raw import
industry              | string  | raw import
location_country      | string  | raw import
funding_stage         | string  | raw import (bootstrapped / pre-seed / seed / Series A / etc.)
linkedin_company_url  | string  | raw import

QUALIFICATION COLUMNS
──────────────────────
finance_dept_count    | integer | Clay → LinkedIn headcount by dept
has_finance_exec      | boolean | Clay → LinkedIn People Search (CFO/Controller check)
ai_score              | integer | AI Ark → Claude (1–10)
ai_reasoning          | string  | AI Ark → Claude (one sentence)
qualification_status  | string  | formula: IF(ai_score>=7 AND NOT has_finance_exec, "QUALIFIED", "REJECTED")

ENRICHMENT COLUMNS
───────────────────
industry_label        | string  | AI Ark → plain-language label ("construction firm", "law firm")
funding_label         | string  | formula: IF(funding_stage="bootstrapped","bootstrapped","{{funding_stage}}-funded")
recent_hire_name      | string  | Clay → LinkedIn new hires (last 90 days, ops/finance title)
recent_hire_title     | string  | Clay → LinkedIn new hires

CONTACT — DM1 (FOUNDER / CEO)
───────────────────────────────
dm1_first_name        | string  | Clay "Contact at Company" (Founder/CEO/Owner)
dm1_last_name         | string  | same
dm1_title             | string  | same
dm1_email             | string  | Apollo waterfall → Prospeo fallback
dm1_email_status      | string  | Prospeo verification
dm1_linkedin_url      | string  | Clay contact data

CONTACT — DM2 (OPS / COO)
────────────────────────────
dm2_first_name        | string  | Clay "Contact at Company" (VP Ops / COO / Office Manager)
dm2_last_name         | string  | same
dm2_title             | string  | same
dm2_email             | string  | Apollo waterfall → Prospeo fallback
dm2_email_status      | string  | Prospeo verification
dm2_linkedin_url      | string  | Clay contact data
dm2_duplicate         | boolean | formula: IF(dm2_email=dm1_email, TRUE, FALSE)

PERSONALIZATION COLUMNS
─────────────────────────
finance_headcount_line| string  | AI Ark → Claude (natural-language finance team size sentence)
research_line         | string  | AI Ark → Claude (company-specific opening line)

OUTPUT COLUMNS
───────────────
email1_body           | string  | formula: assembled from template + variables
email2_body           | string  | formula: assembled from template + variables
email3_body           | string  | formula: assembled from template + variables
sequence_assigned     | string  | "DM1" / "DM2" / "SKIP" (DM2_DUPLICATE or no verified email)
push_status           | string  | "pending" / "pushed" / "bounced"
```

### Operational Setup

**Filter views to maintain:**
- `qualification_status = REJECTED` — review a sample to validate AI scoring quality
- `dm1_email_status = unverified` — manual review before sending; monitor bounce rate closely
- `dm2_duplicate = TRUE` — confirm before skipping; sometimes the ops person IS the founder
- `push_status = bounced` — investigate domain/inbox issues

**Duplicate detection rule:**
After both "Contact at Company" enrichment runs complete, add a Clay formula column:
`IF(dm2_email <> "" AND dm2_email = dm1_email, TRUE, FALSE)`
If true, blank the DM2 row fields before export.

**Push to sequencer:**
Export two CSV files:
1. `zinance_dm1_verified.csv` — `qualification_status=QUALIFIED, sequence_assigned=DM1, dm1_email_status=verified`
2. `zinance_dm2_verified.csv` — `qualification_status=QUALIFIED, sequence_assigned=DM2, dm2_email_status=verified, dm2_duplicate=FALSE`

Upload to Email Bison or Apollo sequences with custom variables: `email1_body`, `email2_body`, `email3_body`, `subject`.

---

## Credit Cost Estimate

| Step | Tool | Credits per row | 12K rows total |
|---|---|---|---|
| LinkedIn headcount enrichment | Clay | ~1–2 | 12,000–24,000 |
| LinkedIn People Search (finance exec check) | Clay | ~2 | 24,000 |
| AI qualification score | AI Ark (Claude) | ~1 | 12,000 |
| Contact at Company × 2 (DM1 + DM2) | Clay | ~2 each | 48,000 |
| Email verification × 2 | Apollo + Prospeo | ~1–2 each | 24,000–48,000 |
| AI Ark personalization × 2 | AI Ark (Claude) | ~1 each | 24,000 |
| **Total** | | | **~144K–180K credits** |

Recommend running qualification on a 1K sample first to validate AI score quality and credit burn before full scale.

---

## Key Design Decisions

1. **Why two DMs per account?** Founders often don't respond to outbound. The ops person at a 20-person firm is frequently the one who actually evaluates vendors and brings the recommendation to the founder. Two contacts doubles response surface without doubling the account list.

2. **Why fixed variables over row-by-row research?** At 100K accounts, manual research is impossible. Fixed variables (headcount, funding, industry) are always available, never wrong if pulled from a verified source, and AI Ark can generate natural-language sentences from them that feel researched without being invented.

3. **Why score ≥ 7 as the threshold?** Scores 6 and below typically correspond to companies with any finance staff or VC backing. Setting the bar at 7 reduces the passing pool from 25K to ~12K, which makes per-row enrichment credits manageable while maintaining list quality.

4. **Why strip `{{sendingAccountName}}` before push?** Email Bison appends the sender's name automatically. If it's also in the body variable, it prints twice. This is a known bug in the Wiired GTM pipeline — always strip before push.
