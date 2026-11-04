# ADR-0006: Scraper actor selection under a free-tier constraint

Status: accepted
Date: 2026-11-03

## Context
Project 01 needs LinkedIn people search by job title and location from n8n. The course reference flow used a PhantomBuster agent driven by a Sales Navigator search URL. We evaluated Apify actors because they are callable as a plain HTTP API.

## Decision
Use `automly/linkedin-people-search-scraper` through the synchronous endpoint `run-sync-get-dataset-items`.

| Option | Facets (headcount / industry) | Login / cookie | Free-plan limit | Outcome |
|---|---|---|---|---|
| PhantomBuster + Sales Navigator URL | Yes (Sales Nav filters) | Needs a LinkedIn session cookie | Not evaluated | Rejected: account-ban risk from a session cookie; Apify is a plain HTTP API |
| `harvestapi/linkedin-profile-search` | Yes | No | **Run cap for free users** ("free user run limit reached") | Worked in tests, then blocked |
| `neuralverge/...-people-search` | Yes | No | **3 runs per month** on Free | Rejected on its documentation |
| `automly/linkedin-people-search-scraper` | **No** | No | No cap | Selected |

Headcount and industry stay in the keyword matrix as reference columns; the ICP is applied through title and location only.

## Consequences
- (+) No LinkedIn credentials in the system; about $0.0015 per profile; the full 15-search run costs about $0.40 and returns 255 profiles.
- (-) No server-side company-size or industry filtering, so results include out-of-ICP companies. Mitigation (roadmap): enrich with a company lookup and filter downstream.
- The full raw record is stored in `raw_json` so that a better filter can be applied later without re-scraping.
