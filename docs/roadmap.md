# GTM Engineering Learning Series — Project Roadmap

Inspired by [Aditya Kanodia's LinkedIn post on 15 GTM Engineering projects](https://www.linkedin.com/feed/update/urn:li:activity:7529476323678027776).

Status below says what is built and what is only specced. The stack at the end is the plan for unbuilt projects, not a list of what has been used.

## Status Legend

| Icon | Meaning |
|---|---|
| ✅ | Built & shipped |
| 🚧 | In progress |
| 📋 | Specced, not started |
| 💡 | Idea only |

---

## Built Projects (01–04)

| # | Project | Status | Key Output |
|---|---|---|---|
| 01 | [LinkedIn ICP Scraper](../projects/01-linkedin-icp-scraper/) | ✅ | ICP → keyword matrix → LinkedIn profiles → spreadsheet |
| 02 | [Contact List Merge](../projects/02-contact-list-merge/) | ✅ | 6 lead exports → clean deduped list (111 tests, 97% coverage) |
| 03 | [Outreach Sequencer](../projects/03-outreach-sequencer/) | ✅ | Clean list → multi-step email/LinkedIn sequence (518 tests) |
| 04 | [Contact Cleaning App](../projects/04-contact-cleaning-app/) | ✅ | Web app over #02, deployed on Railway; HubSpot push written but not run against a live account |

---

## Roadmap: Next 14 Projects

| # | Project | Priority | Effort | Status | Data Sources |
|---|---|---|---|---|---|
| 05 | [Real-Time Intent Webhook Router](../projects/05-intent-webhook-router/) | 🔴 P1 | 2 days | 📋 | Clearbit Reveal / Unify API, Slack Webhooks |
| 06 | [AI SDR Research Agent](../projects/06-ai-sdr-research-agent/) | 🔴 P1 | 3 days | 📋 | GitHub API, Prospeo, Clay, Claude Haiku |
| 07 | [PQL Scorer](../projects/07-pql-scorer/) | 🟡 P2 | 2 days | 📋 | Product event webhooks, Mixpanel/Amplitude export |
| 08 | [Usage-Based Pricing Meter](../projects/08-usage-pricing-meter/) | 🟡 P2 | 2 days | 📋 | Stripe Metered Billing API, internal event log |
| 09 | [Multi-Touch Attribution Engine](../projects/09-attribution-engine/) | 🟡 P2 | 3 days | 📋 | UTM params, HubSpot Activities API, ad platform webhooks |
| 10 | [AI Call Coaching & Battlecard Generator](../projects/10-call-coaching-battlecard/) | 🟡 P2 | 3 days | 📋 | Gong API / Fireflies.ai transcripts, Claude Sonnet |
| 11 | [Predictive Churn & NRR Alert System](../projects/11-churn-alert-system/) | 🔴 P1 | 2 days | 📋 | Product usage DB, Stripe MRR feed, HubSpot |
| 12 | [Automated QBR Generator](../projects/12-qbr-generator/) | 🟢 P3 | 2 days | 📋 | HubSpot, Stripe, usage metrics DB, Google Slides API |
| 13 | [Dark Social Attribution Bot](../projects/13-dark-social-attribution/) | 🟢 P3 | 1 day | 📋 | HubSpot forms, inbound lead webhook, Claude |
| 14 | [Competitor Battlecard Auto-Updater](../projects/14-competitor-battlecard-updater/) | 🟡 P2 | 2 days | 📋 | G2 RSS, competitor sitemap diff, Claude summariser |
| 15 | [GTM Architecture Teardown](../projects/15-gtm-architecture-teardown/) | 🔴 P1 | 1 day | 📋 | Public pricing pages, SEC filings, Sacra research |
| 16 | [Enrichment Waterfall Engine](../projects/16-enrichment-waterfall/) | 🔴 P1 | 3 days | 📋 | Enrichment provider APIs (fake provider for tests) |
| 17 | [Signal and Fit Account Scoring](../projects/17-signal-fit-scoring/) | 🔴 P1 | 3 days | 📋 | Account signals, outcome labels |
| 18 | [GTM MCP Server](../projects/18-gtm-mcp-server/) | 🟡 P2 | 2 days | 📋 | Projects 02, 16, 17 |

---

## Also in Repo

| Project | Status |
|---|---|
| [School Assignments](../projects/school-assignments/) | 🚧 GTM Engineering Cohort 1 — GTME.SCHOOL |

---

## Build Order Rationale

**Start with 16:** the research ([research.md](research.md)) names an enrichment waterfall as a core portfolio project, and the series did not have one.

**P1 first:** Projects 05, 06, 11 produce the most demonstrable "GTM engineer" work for a portfolio — real signals, real routing, real research automation. Project 15 (architecture teardown) is a written analysis that doubles as a blog post.

**P2 next:** Projects 07–10, 14 require mocking a product event stream or a sales call transcript. They are still buildable with synthetic data but have more setup overhead.

**P3 last:** Projects 12–13 are more "polish" than foundational — a QBR generator and a word-of-mouth attributor are valuable but depend on having the upstream data systems (P1–P2) in place first.

---

## Shared Stack

```
Language:    Python 3.11+
Automation:  n8n (Docker, pinned image)
Storage:     SQLite for dev, Postgres (Neon) for prod
AI:          Claude Haiku (workers) / Sonnet (orchestrator) via Anthropic API
Enrichment:  Prospeo + Clay
Email:       Email Bison
CRM:         HubSpot (sandbox)
Billing:     Stripe (test mode)
CI:          GitHub Actions
Tests:       pytest, 80%+ coverage mandatory
```
