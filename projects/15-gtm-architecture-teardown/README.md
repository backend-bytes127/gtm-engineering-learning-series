# Project 15 — Public GTM Architecture Teardown

> **Status:** 📋 In analysis  
> **Priority:** P1 (portfolio piece — written output, no code required)  
> **Effort:** ~1 day  
> **Output:** Written analysis + diagrams published to repo `docs/` and GitHub Pages

---

## Purpose

Break down how 3 leading AI-era companies structure their GTM motion: pricing tiers, PLG funnel mechanics, credit systems, free-to-paid triggers, and expansion levers. The goal is to build a reusable mental model for GTM engineers.

---

## Companies Analysed

1. **Notion** — freemium SaaS, seat-based with AI as upgrade lever
2. **Linear** — PLG issue tracker, per-seat with minimal sales motion
3. **Anthropic (Claude API)** — credit-based API billing, consumption-led expansion

---

## Data Sources

| Source | What it provides |
|---|---|
| Public pricing pages | Tier structure, seat/usage metrics, feature gates |
| Sacra research reports | ARR estimates, growth rates, go-to-market commentary |
| Orb / Metronome pricing index | Pricing model classification, billing mechanics |
| Company blogs + changelogs | Historical pricing changes, packaging experiments |
| G2 / Capterra reviews | Customer-reported friction points in the buying journey |
| SEC / Crunchbase | Funding context, revenue tier estimates |

---

---

# Teardown 1: Notion

## Pricing Structure (as of 2025)

| Tier | Price | Value Metric | Key Gate |
|---|---|---|---|
| Free | $0 | Per member | Block limit for multi-member workspaces |
| Plus | $10/member/month | Per member | Unlimited blocks, basic collaboration |
| Business | $20/member/month | Per member | AI Meeting Notes, Enterprise Search, Research Mode |
| Enterprise | Custom | Per member | SSO, audit logs, SCIM, advanced security |
| AI add-on | $10/1,000 credits | Credit | Custom Agents beyond the free trial |

## PLG Funnel Mechanics

```
Individual signs up (free)
  ↓ Uses Notion solo → hits no limit
  ↓ Invites teammates → workspace hits block limit
  ↓ UPGRADE TRIGGER: team needs to upgrade to continue
    → Plus: unlimited blocks (removes friction)
    → Business: AI features become essential (creates pull)
      → AI Meeting Notes tried on free → gated after trial
      → Research Mode limited on free → power users want more
  ↓ Enterprise: IT/procurement enters, deal becomes sales-led
```

## Key Design Decisions

**Upgrade trigger is team-level, not individual.** The free block limit is not per-user — it hits the workspace when multiple members are active. This means Notion converts entire teams (5–20 seats) rather than individuals. One power user inside a company drives a multi-seat expansion.

**AI as the Business-tier moat.** In May 2025, Notion moved AI Meeting Notes, Research Mode, and Enterprise Search from Plus to Business. This is a deliberate expansion play: existing Plus customers who adopted AI features (available as trials) must upgrade their entire team to keep them. The packaging change is itself a GTM motion.

**Credit model for agents.** Custom Agents use credits ($10/1,000 credits) on top of the seat subscription. This is the usage-based layer that lets Notion capture more revenue from power users without raising headline per-seat prices.

## Growth Levers

| Lever | Mechanism |
|---|---|
| Viral adoption | Individual use → teammate invites → team conversion |
| AI trial → upgrade | AI features available as "limited trial" on Free/Plus; upgrade to Business to keep them |
| Template gallery | Community-built templates drive top-of-funnel signups |
| Integrations | Slack, GitHub, Figma integrations make Notion stickier; each integration is a moat |
| Enterprise land-and-expand | IT standardises on Notion after a team lands; seat count grows with org size |

## GTM Engineer's Takeaway

Notion's architecture is a master class in **multi-stage conversion**. The Free tier is not a loss leader — it is the awareness and adoption vehicle. The block limit is not a paywall — it is a natural friction point that only activates when the product has proven its value to a team. The AI packaging change is the equivalent of a mid-market sales motion executed through a product update.

---

# Teardown 2: Linear

## Pricing Structure (as of 2025)

| Tier | Price | Value Metric | Key Gate |
|---|---|---|---|
| Free | $0 | Unlimited members, limited history | 250 issues, no analytics |
| Basic | $10/member/month | Per seat | Unlimited issues, integrations |
| Business | $16/member/month | Per seat | Advanced analytics, SLA tracking, AI triage |
| Enterprise | Custom | Per seat | SOC 2, SSO, priority support |

*Source: Sacra estimate + Schematic teardown (May 2026). Not verified against official pricing page.*

## PLG Funnel Mechanics

```
Engineering team discovers Linear (Hacker News / word of mouth)
  ↓ Signs up free → adds whole team (no seat gating on free tier)
  ↓ Hits 250-issue limit → UPGRADE TRIGGER: must go to Basic
    → Basic: immediate team-level upgrade (all seats pay)
  ↓ Team grows → more seats naturally
  ↓ Engineering org matures → needs analytics, SLA tracking, AI triage
    → UPGRADE TRIGGER: Business plan
  ↓ Company gets acquired or scales to enterprise → SSO/SOC 2 needed
    → Enterprise (sales-led)
```

## Key Design Decisions

**No feature-gating on Free.** Unlike Notion, Linear's Free tier is generous — unlimited members, full feature access, just an issue count limit. This is a deliberate choice: engineering teams are skeptical of feature-gated tools. The issue limit is a natural usage ceiling that hits when the product has proven its value. No features withheld = no reason to avoid Linear.

**Seat pricing despite PLG.** Linear charges per seat rather than per usage, which looks odd for a PLG tool. The rationale: engineers talk to other engineers. When an engineering lead changes jobs, they bring Linear with them. Per-seat billing captures the expansion revenue from that movement without needing a sales rep.

**AI triage as Business differentiator.** Linear's AI features (issue auto-categorisation, priority triage) are gated to Business. This is similar to Notion's AI play: introduce AI on the product's most critical workflow (issue management), let users experience it, then price it into the upgrade.

## Growth Levers

| Lever | Mechanism |
|---|---|
| Developer word-of-mouth | Engineers rave about Linear's UX; spreading through Hacker News, Twitter/X |
| Job changes | Engineering leads bring Linear to new companies; compounding acquisition |
| GitHub/Jira migration | Teams leaving Jira bring entire org; migration tool makes switching easy |
| AI triage pull | AI features drive Business tier adoption as orgs scale |
| Transparent pricing | Published per-seat pricing builds trust with engineers who hate opaque sales |

## GTM Engineer's Takeaway

Linear is the clearest example of **bottoms-up, developer-led growth**. No marketing budget. No SDR team (by reputation). The product itself is the sales motion. The key GTM engineering insight: Linear tracks **issue velocity** (how fast teams hit 250 issues) to identify accounts approaching the natural upgrade trigger, then times outreach or in-app prompts to that moment. That is a PQL model executed with a single metric.

---

# Teardown 3: Anthropic (Claude API)

## Pricing Structure (as of Nov 2025)

| Model | Input (per 1M tokens) | Output (per 1M tokens) | Use case |
|---|---|---|---|
| Claude Haiku 4.5 | ~$0.80 | ~$4.00 | High-volume workers, chat |
| Claude Sonnet 4.6 | ~$3.00 | ~$15.00 | Main dev + coding tasks |
| Claude Opus 4.5 | ~$15.00 | ~$75.00 | Complex reasoning |

*Prices are approximate from public sources (Vantage, eWeek). Check console.anthropic.com for current rates.*

**Free trial:** $5 one-time credit, no credit card, SMS verification required. Not an ongoing free tier.

**Startup credits:** Up to $100,000 via Anthropic's startup program or VC-partner tracks.

## PLG Funnel Mechanics

```
Developer discovers Claude via API docs / HN / Twitter
  ↓ Signs up for $5 free credit → first API call
  ↓ Prototype in days (Claude's strength: low time-to-first-output)
  ↓ $5 runs out → adds credit card → usage-based billing begins
  ↓ Usage grows → token volume triggers tier discussions
  ↓ Series A startup → applies for startup credits ($100k)
    → Locks in Anthropic as default LLM provider for 12-18 months
  ↓ Scale → enterprise contract (committed spend, volume discounts, SLAs)
```

## Credit System Design

Anthropic does not use a traditional SaaS subscription model. The billing is pure consumption (tokens in + tokens out). This is the **usage-based PLG** model, which differs fundamentally from seat-based PLG:

- **No seat gates.** A team of 50 engineers can all call the API; they share a credit balance.
- **Expansion is automatic.** As usage grows, the invoice grows without any sales motion.
- **Model routing is a GTM lever.** The 3-tier model lineup (Haiku/Sonnet/Opus) is not just technical — it is a pricing ladder. Teams start on Haiku (cheapest), experience its limits, and upgrade to Sonnet for production. Opus remains aspirational. This is **good-better-best** packaging expressed as inference cost.

## Key Design Decisions

**Token pricing creates a natural upgrade path.** A developer building a chatbot starts with Haiku at $0.80/1M input tokens. When they need better reasoning for complex tasks, they switch to Sonnet — a 3.75x price increase that happens without a sales call. The model capability difference justifies the price difference, so the customer self-selects into the upgrade.

**Credits expire, creating urgency.** Prepaid credits expire 1 year after purchase. This is not punitive — it is a commitment device that encourages teams to actually use the platform rather than sit on unused credits.

**Startup program is a sales motion.** The $100,000 startup credits program locks in a customer for 12–18 months during their most formative architecture decisions. This is similar to AWS Activate: the credits are expensive for Anthropic in the short term, but the switching cost of migrating away from Claude after building an entire product on top of it is enormous.

## Growth Levers

| Lever | Mechanism |
|---|---|
| Developer adoption | Low time-to-first-output; excellent docs; active Discord/HN presence |
| Model ladder | Haiku → Sonnet → Opus upgrade path is self-serve; no sales needed |
| Startup program | $100k credits locks in architectural commitment during hypergrowth |
| Claude.ai consumer | B2C app drives B2B API awareness; developers use Claude personally, then reach for the API |
| Anthropic partnerships | VC-partner tracks (a16z, Bessemer) funnel portfolio companies directly into startup program |

## GTM Engineer's Takeaway

Anthropic's model is the purest expression of **consumption-led growth**. There are no seats, no features to gate, no upgrade buttons. Revenue grows automatically with usage. The GTM engineering challenge here is not conversion — it is **activation**: getting a developer from first API call to production deployment as fast as possible. That is why Anthropic invests heavily in docs, cookbooks, and prompt examples. Those are not marketing — they are the GTM infrastructure.

---

## Cross-Company Patterns

| Pattern | Notion | Linear | Anthropic |
|---|---|---|---|
| Pricing metric | Seats | Seats | Tokens |
| Free-to-paid trigger | Block limit (team) | Issue limit (usage) | Credit exhaustion |
| AI as upgrade lever | Yes (Business tier) | Yes (Business tier) | Native to product |
| Self-serve expand | Viral seat adds | Job-change mobility | Automatic token growth |
| Enterprise motion | IT procurement | DevOps/Eng leadership | Committed spend contracts |
| Key PLG metric | Workspace member count | Issue velocity | Monthly active tokens |

## For the GTM Engineer

If you are building a SaaS tool, the architecture teardown reveals one consistent insight: **the upgrade trigger must feel natural, not forced**. All three companies let users fully experience the product before hitting a limit. Notion lets teams collaborate freely until they need more. Linear lets engineers ship freely until they outgrow 250 issues. Anthropic lets developers build freely until their $5 runs out.

The GTM engineer's job is to instrument these triggers, track the accounts approaching them, and time the sales or in-product motion to the moment of maximum product-proven value.

---

## Related Projects

- [Project 04 — Contact Cleaning App](../04-contact-cleaning-app/) — HubSpot integration patterns
- [Project 07 — PQL Scorer](../07-pql-scorer/) — operationalising the "approaching the trigger" signal
- [Project 08 — Usage-Based Pricing Meter](../08-usage-pricing-meter/) — building the Anthropic-style consumption tracking
