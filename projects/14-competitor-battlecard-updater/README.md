# Project 14 — Competitor Battlecard Auto-Updater

> **Status:** 📋 Specced, not started | **Priority:** P2 | **Effort:** ~2 days

## Problem

Competitor battlecards go stale within weeks. Pricing changes, new features launch, messaging shifts. Sales reps either use outdated battlecards or skip them entirely. Keeping battlecards current requires a full-time competitive intelligence analyst — or automation.

## Proposed Solution

A Python pipeline that monitors competitor pricing pages, G2 reviews, and product changelogs daily, detects changes, and updates a shared battlecard document automatically.

## Data Sources

| Source | What it provides | Access |
|---|---|---|
| **Competitor pricing pages** | Tier structure, pricing, feature lists | Weekly HTTP GET + HTML diff (BeautifulSoup) — public pages |
| **G2 Reviews API** | Recent competitor reviews, common praise/complaints | `GET https://data.g2.com/api/v1/products/{id}/reviews` — requires G2 API access (contact G2) |
| **Google Alerts RSS** | Competitor news, funding, product launches | RSS feed per competitor: `https://www.google.com/alerts/feeds/{key}/{id}` |
| **Competitor sitemap / changelog** | New product docs, feature releases | `GET /sitemap.xml` → parse new URLs → fetch new changelog entries |
| **Hacker News Algolia API** | HN posts mentioning competitor | `GET https://hn.algolia.com/api/v1/search?query=<competitor>&tags=story` — free, no auth |
| **Claude Sonnet** | Summarise changes, update battlecard sections | `anthropic.messages.create` |
| **Google Drive / Notion** | Battlecard storage | Composio Google Drive connector already in stack |

## Detection Logic

```python
def detect_pricing_change(old_html: str, new_html: str) -> list[Change]:
    # 1. Extract price tables from both versions
    # 2. Diff the structured data (not raw HTML)
    # 3. If tier name, price, or key feature changed → flag as Change
    # 4. Return list of Change objects with before/after
```

## Tests

```python
test_pricing_page_diff_detects_price_change()
test_pricing_page_diff_ignores_whitespace()
test_g2_review_sentiment_extraction()
test_changelog_new_entry_detected()
test_battlecard_section_update_preserves_structure()
test_no_hallucinated_pricing_numbers()  # Claude output must cite source URL
```
