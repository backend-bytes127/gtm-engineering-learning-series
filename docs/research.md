# Research: what strong GTM engineering projects look like

Web and GitHub search, November 2026. Most written advice here comes from vendors, course sellers and job-market blogs, so treat it as opinion, not evidence. Nothing in the linked repositories was run or code-reviewed. Star counts and licences change; check them before reusing code.

## Recurring advice

- A few small, public, documented projects beat one large one, and each should lead with a measured result.
- The project types that recur: enrichment waterfall, lead scoring and routing, intent or signal-based outbound, CRM cleanup with a before-and-after report, revenue or attribution reporting, AI research agents, and tools that non-technical reps can run (for example over MCP).
- Commonly named skills: SQL, Python or JavaScript, APIs and webhooks, waterfall enrichment, deduplication and data quality, signal selection. Sources disagree on how much coding is required.

Sources: [Databar: portfolio guide](https://databar.ai/blog/article/how-to-build-a-gtm-engineering-portfolio-that-gets-you-hired), [GTM Pulse: portfolio examples](https://gtmepulse.com/insights/gtm-engineer-portfolio-examples/), [Landed: GTM engineer roadmap](https://www.landed.jobs/resources/roadmaps/gtm-engineer), [Clay community: sales-team projects](https://community.clay.com/x/share-resources/msg_WoeX9opqxwcf/5-practical-gtm-engineering-projects-for-sales-tea), [Apollo: technical skills](https://www.apollo.io/insights/what-programming-or-technical-skills-should-a-gtm-engineer-have), [gtminds: becoming a GTM engineer](https://www.gtminds.io/blog/how-to-become-gtm-engineer), [Explorium: role checklist](https://www.explorium.ai/blog/data-for-gtm/gtm-engineer-role-skills-and-structure-2026-checklist-for-revops-leaders/).

## Compared with this series

| Project type | Covered by | Gap |
|---|---|---|
| CRM cleanup and deduplication | [02](../projects/02-contact-list-merge/), [04](../projects/04-contact-cleaning-app/) | Built |
| Sequencing and outreach | [03](../projects/03-outreach-sequencer/) | Built |
| Prospect sourcing | [01](../projects/01-linkedin-icp-scraper/) | Built |
| Intent routing | [05](../projects/05-intent-webhook-router/) | Specced |
| AI research agent | [06](../projects/06-ai-sdr-research-agent/) | Specced |
| Lead and product-usage scoring | [07](../projects/07-pql-scorer/) | Specced |
| Attribution and revenue reporting | [09](../projects/09-attribution-engine/) | Specced |
| Enrichment waterfall | [16](../projects/16-enrichment-waterfall/) | **Was missing**; added |
| Fit and signal scoring checked against outcomes | [17](../projects/17-signal-fit-scoring/) | **Was missing**; added (the backtest requirement is our own bar) |
| Tools reps can call from an AI assistant | [18](../projects/18-gtm-mcp-server/) | **Was missing**; added |

## Open-source repositories worth studying

Stars as seen in November 2026.

| Repository | What it is | Stars | Licence |
|---|---|---|---|
| [debpalash/OpenGTM](https://github.com/debpalash/OpenGTM) | Self-hosted Clay alternative: enrichment waterfalls, research, signals | 134 | AGPL-3.0 |
| [Othmane-Khadri/gtm-engineer-playbook](https://github.com/Othmane-Khadri/gtm-engineer-playbook) | Claude Code skills for ICP, signals, scoring, outreach | 61 | MIT |
| [SantaJordan/gtm-engineer-starter](https://github.com/SantaJordan/gtm-engineer-starter) | A GTM engineering method packaged as agent skills | 38 | MIT |
| [Astoriel/LeadGenius](https://github.com/Astoriel/LeadGenius) | Lead scoring and routing with waterfall enrichment | 28 | none stated (do not reuse code) |
| [getcargohq/cargo-skills](https://github.com/getcargohq/cargo-skills) | Agent skills for list building, enrichment, scoring, CRM sync | 27 | MIT |
| [Clay-Bootcamp/gtme-goldmine](https://github.com/Clay-Bootcamp/gtme-goldmine) | Collection of GTM engineering projects | 25 | MIT |
| [landedjobs/become-a-gtm-engineer](https://github.com/landedjobs/become-a-gtm-engineer) | Staged learning roadmap with portfolio projects | 25 | MIT |
| [getaero-io/gtm-signal-scoring](https://github.com/getaero-io/gtm-signal-scoring) | Account signal scoring on PostgreSQL | 8 | MIT |
| [rahulnkm/auto-gtme](https://github.com/rahulnkm/auto-gtme) | Signal-based outreach stack run from Claude Code | 4 | MIT |
| [Hasee10/gtm-waterfall-enrichment](https://github.com/Hasee10/gtm-waterfall-enrichment) | FastAPI and Postgres waterfall enrichment with HubSpot sync | 1 | MIT |

Curated lists: [marketinguys/awesome-gtm-engineering](https://github.com/marketinguys/awesome-gtm-engineering), [eliasstravik/awesome-gtm-engineering](https://github.com/eliasstravik/awesome-gtm-engineering), [loootai/awesome-gtm](https://github.com/loootai/awesome-gtm).
