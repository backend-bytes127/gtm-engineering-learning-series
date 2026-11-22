# Project 06 — AI SDR Research Agent

> **Status:** 📋 Specced, not started  
> **Priority:** P1  
> **Effort:** ~3 days  
> **Stack:** Python + Claude Haiku + Prospeo + Clay MCP + SQLite

---

## Problem

An SDR spends 20–40 minutes researching each prospect before writing a cold email: GitHub activity, recent LinkedIn posts, company news, podcast appearances. That research either does not happen (spray-and-pray) or becomes the SDR's bottleneck. The result is generic copy or slow sequencing.

## Proposed Solution

A Python agent that takes a prospect (name + company + LinkedIn URL) and autonomously:
1. Scrapes public signals across GitHub, LinkedIn, podcast feeds, and news
2. Scores signal relevance against the ICP offer
3. Generates a personalised 3-email cold outreach sequence using the top 2–3 signals
4. Outputs a structured JSON record ready to push into Email Bison or HubSpot

---

## Data Sources

| Source | What it provides | Access method |
|---|---|---|
| **GitHub API** (public) | Repos, stars, recent commits, programming languages, employer listed in profile | `GET https://api.github.com/search/users?q=<name>+<company>` → `GET /users/<login>` → `GET /users/<login>/repos` — no auth needed for public data; 60 req/h unauthenticated, 5000/h with token |
| **Prospeo** | Work email, LinkedIn URL, job title confirmation | `POST https://api.prospeo.io/social-url-search` with `X-KEY` header — already in use in this project stack |
| **Clay MCP** | Company news, funding rounds, headcount changes, job postings, LinkedIn activity signals | `mcp__clay__search-contacts` + `mcp__clay__add-contact-data-points` — authenticated, available in this project's toolset |
| **Podcast Index API** (free) | Podcast appearances by name/company | `GET https://api.podcastindex.org/api/1.0/search/byperson?q=<name>` — free API, needs `X-Auth-Key` + `X-Auth-Date` HMAC headers |
| **NewsAPI** / **Bing News** | Recent company news, product launches, funding | `GET https://newsapi.org/v2/everything?q=<company>&sortBy=publishedAt` — 100 req/day free |
| **LinkedIn public profile** (via scraping) | Recent posts, promotions, role changes | Apify LinkedIn Scraper actor (via Apify API) — `POST https://api.apify.com/v2/acts/apify~linkedin-profile-scraper/runs` |
| **Claude Haiku** | Signal scoring, copy generation | `anthropic.messages.create(model="claude-haiku-4-5")` — cheapest model, ~$0.001 per prospect |

---

## Input → Output Spec

**Input (JSON):**
```json
{
  "first_name": "Alex",
  "last_name": "Chen",
  "company": "Runway ML",
  "linkedin_url": "https://linkedin.com/in/alex-chen-runway",
  "offer": "Outbound prospecting-as-a-service for AI/ML companies"
}
```

**Processing pipeline:**
```
1. Prospeo → confirm email + title
2. GitHub API → repos / language / activity
3. Clay → company news + job postings
4. Podcast Index → appearances
5. Claude Haiku (signal scorer) → rank signals by relevance, pick top 3
6. Claude Haiku (copywriter) → generate 3-email sequence using top signals
7. Output structured JSON
```

**Output (JSON):**
```json
{
  "prospect": { "name": "Alex Chen", "email": "alex@runwayml.com", "title": "Head of ML" },
  "signals": [
    { "type": "github", "detail": "Built open-source video diffusion repo, 1.2k stars, last commit 3 days ago" },
    { "type": "news", "detail": "Runway raised $141M Series C, March 2024" },
    { "type": "podcast", "detail": "Guest on Latent Space podcast, episode on data pipelines, Oct 2024" }
  ],
  "emails": {
    "email1": { "subject": "...", "body": "..." },
    "email2": { "subject": "...", "body": "..." },
    "email3": { "subject": "...", "body": "..." }
  },
  "research_cost_usd": 0.003
}
```

---

## Claude Haiku Prompts

**Signal scorer prompt:**
```
You are a GTM research analyst. Given these raw signals about a prospect, 
rank the top 3 by relevance to this offer: "{offer}".
Return JSON: [{type, detail, relevance_score (1-10), why}]
Signals: {signals_json}
```

**Copywriter prompt:**
```
Write a 3-email cold outreach sequence. Rules:
- No em dashes, no exclamation marks
- Each email ≤150 words
- Use exactly 1 signal per email, the most relevant signal first
- Opening line references the signal naturally, no "I saw that..."
- CTA: one soft ask per email
Prospect: {name}, {title} at {company}
Offer: {offer}
Signals: {top_3_signals}
Return JSON: {email1: {subject, body}, email2: ..., email3: ...}
```

---

## n8n Workflow (batch mode)

```
Schedule Trigger (daily 6am)
  → SQLite: fetch pending_research queue
  → Loop over prospects (batch of 20)
    → HTTP: Prospeo enrich
    → HTTP: GitHub search
    → Clay node: company signals
    → HTTP: Podcast Index
    → Python: build signals list
    → Claude Haiku: score + write copy
    → SQLite: save output
    → HTTP: push to Email Bison (optional)
```

---

## Test Approach

```python
test_github_search_found()       # known developer → returns repos
test_github_search_not_found()   # no GitHub account → returns empty list, no crash
test_signal_scorer_returns_top3() # given 6 signals → returns exactly 3
test_signal_scorer_ranks_by_relevance() # more specific signal scores higher
test_copy_no_em_dashes()         # assert '—' not in output
test_copy_no_exclamation_marks() # assert '!' not in output
test_copy_word_count()           # each email body ≤150 words
test_full_pipeline_mock()        # mock all APIs → check output schema
test_cost_tracker()              # token count → USD cost calculation correct
```

---

## Effort Estimate

| Task | Hours |
|---|---|
| Data source integrations (GitHub, Podcast Index, NewsAPI) | 3h |
| Prospeo + Clay integration (already partially built) | 1h |
| Signal scorer Claude prompt + parser | 2h |
| Copywriter Claude prompt + parser | 2h |
| SQLite schema (research_queue, research_results) | 1h |
| n8n batch workflow | 2h |
| Tests | 3h |
| Docs + README | 1h |
| **Total** | **~15h** |

---

## Priority Rationale

This is the highest-leverage project in the series: it replaces 20–40 min of manual SDR research per prospect with a $0.003 automated run. It directly extends Projects 01–03 (the ICP list → sequencer pipeline) with AI-powered personalisation. It also demonstrates multi-step agent reasoning (research → score → write) using Claude Haiku, which is the most cost-efficient model for high-volume worker tasks.
