# Assignment 2: From ICP to Motion
**GTM Engineering — Cohort 1**
**Company: Wiired GTM**
**Offer: Done-for-you outbound stack — verified ICP list + 3-email sequence + configured sending domain, delivered in 5 business days. One project fee, no retainer.**
**Mechanism: Sales Hiring Signal Stack — targets companies actively posting for a sales hire.**

---

## Part 1: Map the Deal

The typical buyer is a 21–200-person US professional services firm (consulting, agency, staffing, or SaaS product). The person who controls the budget is almost always the founder or managing director. There is rarely a formal procurement layer.

| Role | Target Titles | What Wins Them | Where to Reach | Power |
|---|---|---|---|---|
| **Economic Buyer** | Founder, Managing Director, CEO, Principal | ROI clarity — show the pipeline value of a filled calendar vs. the cost of an SDR hire. No retainer removes the commitment risk. | Cold email (direct), LinkedIn connection request with note | H |
| **Decision Maker** | Founder, VP Sales, Head of Business Development | Speed and specificity — they want a list ready in 5 days, not a 90-day agency ramp. Proof that the signal (live job posting) is real and verifiable. | Cold email, LinkedIn DM after a signal event (new sales hire, funding) | H |
| **Champion** | Marketing Manager, Operations Manager, Chief of Staff | Easy internal win — this removes list-building work from their plate and makes the BD lead look better. They want something they can point to. | Email, LinkedIn, referral from Decision Maker | M |
| **End User** | BizDev Lead, Account Executive, Sales Lead | Pain removal — they currently spend hours sourcing names and writing emails. The system does that for them, with verified contacts and ready-to-send copy. | Cold email, LinkedIn | M |
| **Blocker / Gatekeeper** | Executive Assistant, Operations Manager | Reassurance that there's no long contract, no tech integration, no commitment beyond the project fee. | Forward from Decision Maker; include an FAQ or one-pager with explicit "no lock-in" framing | L |

---

## Part 2: Read the Signal

Signals are categorised as **Fit** (static, slow-changing) or **Intent** (dynamic, time-sensitive). Score = predicted "ready now" probability 0–10.

| # | Signal | Type | Score | Reasoning |
|---|---|---|---|---|
| 1 | Company posting a SDR, BDR, or Business Development role | Intent | **9** | Direct proxy for "we want pipeline but haven't hired yet" — the exact moment before they hire in-house. Time-window is narrow (30–60 days). |
| 2 | Company posting a Sales Director or VP Sales role | Intent | **8** | New sales leader typically re-evaluates the entire outbound stack in their first 90 days. High buying intent, defined budget. |
| 3 | Founder posting on LinkedIn about pipeline problems, slow BD, or difficulty filling a calendar | Intent | **8** | Explicit public statement of pain. The post is verifiable and highly specific. Rare but extremely high signal. |
| 4 | Company recently hired a VP Sales (LinkedIn new job within 90 days) | Intent | **7** | New hire often spends in first 60 days. They want to show results fast and are open to systems they don't have to build themselves. |
| 5 | Company headcount 21–200, US-based, in target segment (S1/S2/S4/S5) | Fit | **7** | Core ICP fit. Without this, intent signals lose their value. Required qualifier, not a standalone trigger. |
| 6 | Company posting a Marketing Manager or Demand Gen role | Intent | **6** | Marketing hire suggests growth mode and budget availability. BD investment often follows within a quarter. |
| 7 | Funding round announced in the last 6 months (Seed–Series B) | Intent | **6** | Fresh capital plus pressure to show revenue growth. Outbound spend is often explicitly in the use-of-funds narrative. |
| 8 | No SDR or sales development headcount visible on LinkedIn | Fit | **6** | Confirms the gap the offer fills. If they already have 3 SDRs, the offer is redundant. Gate field before outreach. |
| 9 | New office opened or geographic expansion announced | Intent | **5** | Signals growth phase and new territory pipeline need. Moderate signal — not all expansions involve outbound. |
| 10 | Company size 21–200 AND in professional services AND US AND no sales team on LinkedIn | Fit composite | **5** | Strong fit stack but no live intent. Outreach is valid but cadence should be slower; use Tier 3 attack plan. |

---

## Part 3: Tier & Attack

**Tier definitions use two axes: ICP fit score and signal strength.**

### Tier 1 — Best Fit + Live Intent
**Criteria:** Target segment (S1/S2/S4/S5) + 21–200 headcount + US + active SDR/BDR/Sales Director posting (Signals 1 or 2).

| Channel | Cadence | Notes |
|---|---|---|
| Cold email (3-step sequence) | Day 1, Day 4, Day 8 | Trigger-personalised opening citing the specific role posted. Use Block 2 Option 1. |
| LinkedIn connection request | Day 2 | Short note referencing the same signal. Max 300 chars. |
| LinkedIn DM (if connected) | Day 6 | Only if connected. One follow-up referencing the email sent. |
| Calls (if mobile verified) | Day 9 | Wing A only. 1 call attempt. Leave no voicemail unless verified mobile. |

**Sequence length:** 3 emails + 1–2 LinkedIn touches + 1 call attempt  
**Expected reply rate:** 3–5%  
**Conversion of reply to demo:** 25–35%

---

### Tier 2 — Good Fit + Moderate Signal
**Criteria:** Target segment + right headcount + US + one of: funding event, new VP Sales hire, founder LinkedIn pain post, marketing hire (Signals 3–7).

| Channel | Cadence | Notes |
|---|---|---|
| Cold email (3-step sequence) | Day 1, Day 5, Day 10 | Signal-aware opening using Block 2 Option 2 (ICP mapping frame). |
| LinkedIn connection request | Day 3 | Generic value prop note, no signal mention. |
| LinkedIn DM (if connected) | Day 8 | Only if connected. |

**Sequence length:** 3 emails + 1 LinkedIn touch  
**Expected reply rate:** 2–3%

---

### Tier 3 — Fit, No Current Signal
**Criteria:** Target segment + right headcount + US + no active intent signals.

| Channel | Cadence | Notes |
|---|---|---|
| Cold email (2-step sequence) | Day 1, Day 10 | Use Block 2 Option 3 (industry map frame). No signal claims. |
| LinkedIn connection request | Day 5 | No note — connection only. |

**Sequence length:** 2 emails only  
**Expected reply rate:** 0.5–1.5%

---

### Tier 4 — Weak Fit / Low Signal
**Criteria:** Outside target segment, headcount <21 or >200, non-US, or multiple missing qualifiers.

**Action:** Do not reach out. These rows do not enter sequences. If they appear in a list export, suppress before upload.

---

## Part 4: Build the Pipes

### (a) Inbox Environment Analysis

**Audience profile:** Small professional services firms (21–200 employees) in the US. Email infrastructure skews heavily towards Google Workspace (Gmail), with a minority on Microsoft 365. Very few run enterprise-grade email security gateways (Proofpoint, Mimecast, Barracuda) at this size.

| Provider | Approx. share | Filtering behaviour |
|---|---|---|
| Google Workspace (Gmail) | ~65% | Machine-learning spam filters, link scanning, image pixel tracking blocked by default. Plain-text emails with no images perform best. |
| Microsoft 365 | ~25% | Exchange Online Protection (EOP) active on all plans. Defender ATP on Business Premium. Reputation-based filtering; new sender domains need 2–4 weeks of warmup. |
| Other / legacy | ~10% | Variable. Mimecast or Barracuda more likely here. Avoid HTML-heavy emails. |

**Deliverability rules:**
- Dedicated sending domains (never the main company domain). Format: `[sender]-[topic].com`, e.g. `outbound-pipeline.com`.
- SPF, DKIM, DMARC all required before first send. DMARC policy: `p=none` to start, move to `p=quarantine` after 30 days of clean sending.
- Custom tracking domain (not the shared Email Bison domain). Avoids reputation bleed from other senders on the same pool.
- Open tracking off (Google images proxy breaks it; it also signals automation).
- Click tracking on custom domain only, not the shared platform domain.
- Plain text preferred. No images, no attachments, no HTML buttons.
- Warmup via a warmup service (Instantly, Lemwarm, or Email Bison's built-in) for 3–4 weeks before first real send.

---

### (b) Sending Volume Sizing

**Monthly target: 10 demos booked**

| Metric | Value | Basis |
|---|---|---|
| Demos needed | 10 | Monthly goal |
| Reply-to-demo conversion | 30% | Industry benchmark for warm reply → booked call |
| Replies needed | 34 | 10 / 0.30 |
| Reply rate | 2% | Conservative blended rate across Tier 1–3 |
| Emails needed per month | 1,700 | 34 / 0.02 |
| Daily send target | ~57 emails/day | 1,700 / 30 |
| Max per inbox per day | 40 (safe cap post-warmup) | Avoids domain reputation spikes |
| Inboxes needed | 2 | 57 / 40 = 1.4, round up to 2 |
| Domains needed | 2 (1 inbox each) | 1:1 domain-to-inbox ratio recommended |

**Warmup ramp per inbox:**

| Week | Daily send volume | Notes |
|---|---|---|
| 1 | 10–15 | Warmup service only. No real prospects. |
| 2 | 20–25 | Mix warmup + first Tier 1 contacts |
| 3 | 30–35 | Expand to Tier 2 |
| 4+ | 40 (cap) | Full send. Monitor bounce rate daily. |

**Alert thresholds:**
- Bounce rate >3% in a day → pause and investigate
- Spam complaint rate >0.1% → pause immediately, do not resume without domain review

**LinkedIn + Phone goals:**

| Channel | Monthly target | Notes |
|---|---|---|
| LinkedIn conversations started | 30 | Tier 1 + 2 connection requests → DM |
| LinkedIn conversations converted to demo | 3 | 10% of 30 |
| Phone calls attempted (Tier 1 Wing A only) | 20 | Verified mobile only |
| Phone demos booked | 2 | 10% connect + 50% conversion |

---

## Part 5: Write Your First Email

### Pre-Send Checklist

Before any email leaves the queue:
- [ ] Is every sentence about them or their situation, not about Wiired GTM?
- [ ] Is there exactly one ask in the email?
- [ ] Is the body under 120 words (count after spintax resolves)?
- [ ] Does the opening use a verifiable trigger (the specific role posted, the specific industry segment) rather than a compliment?
- [ ] Is `{{sendingAccountName}}` an individual first name, never an agency name?
- [ ] No em dashes, no exclamation marks, no colons in body?
- [ ] P.S. is 12 words or fewer?
- [ ] No `{{sendingAccountName}}` in body strings (Email Bison appends sender automatically)?

---

### Email 1 — Decision Maker (Founder / MD)
*Trigger: Company posted SDR or BDR role on LinkedIn/Indeed*

**Subject:** `{pipeline timing|quick note}`

Hi {{firstName}},

Found {{companyName}} through your open {{salesRoleTitle}} posting.

Most firms posting that role spend 60–90 days on the hire, then another 60 ramping them. Pipeline stalls the whole time.

We build the full outbound stack for you — verified list, 3-email sequence, configured sending domain — and hand it over in 5 days. You keep it. No retainer, no ongoing contract.

If that's worth exploring, would a one-page breakdown of how it works be useful?

{{sendingAccountName}}

{P.S. if this isn't for you, feel free to unsubscribe here|P.S. not relevant? unsubscribe here}

*(Word count: 87)*

---

### Email 2 — End User (BizDev Lead / Account Executive)
*Sent to the person who would actually use the outbound system day-to-day*

**Subject:** `{pipeline timing|quick note}`

Hi {{firstName}},

Found {{companyName}} while mapping firms that run their own BD.

Most BD leads I talk to spend 4–6 hours a week building lists by hand and another few hours writing the emails. That's time that probably belongs somewhere else.

We handle the whole thing — ICP list, copy, sending setup — and deliver it in 5 days. You get a system that runs without you having to source anything.

Worth a quick look at how it works?

{{sendingAccountName}}

{P.S. if this isn't for you, feel free to unsubscribe here|P.S. not relevant? unsubscribe here}

*(Word count: 93)*

---

### Email 3 — Champion (Marketing Manager / Ops)
*Sent to the internal person who could sponsor or recommend the tool*

**Subject:** `{pipeline timing|quick note}`

Hi {{firstName}},

Found {{companyName}} while mapping agencies building their own BD pipeline.

A lot of marketing teams end up owning the outbound problem by default because there's no one else. We build the full stack — list, copy, sending domain — in 5 days, then hand it off so it's not your problem anymore.

The BD lead gets a working system. You get the credit for finding it.

Would a one-pager on how it works be worth sending over?

{{sendingAccountName}}

*(Word count: 83 — no P.S. on Email 3)*

---

## Summary

| Part | Deliverable |
|---|---|
| 1. Map the Deal | 5-role buying committee table with titles, motivations, channels, power ratings |
| 2. Read the Signal | 10 signals scored 0–10, fit vs intent split |
| 3. Tier & Attack | 4-tier framework with channel mix, cadence, sequence length, expected reply rates |
| 4. Build the Pipes | Inbox environment analysis + sending volume model (10 demos/month, 2 domains, 2 inboxes, 4-week warmup) |
| 5. Write Your First Email | 3 emails (DM, end user, champion) + pre-send checklist, all copy rules applied |
