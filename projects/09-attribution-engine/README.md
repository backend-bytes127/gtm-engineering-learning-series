# Project 09 — Multi-Touch Attribution Engine

> **Status:** 📋 Specced, not started | **Priority:** P2 | **Effort:** ~3 days

## Problem

Marketing teams run ads, send emails, host webinars, and post content. When a deal closes, everyone claims credit. Last-touch attribution is too simple; first-touch ignores nurture. Without a proper attribution model, budget decisions are based on guesses.

## Proposed Solution

A Python pipeline that ingests touchpoints from multiple channels, links them to contacts and deals in HubSpot, and computes W-shaped attribution (40% first, 40% last, 20% distributed across middle touches).

## Data Sources

| Source | What it provides | Access |
|---|---|---|
| **HubSpot Activities API** | Email opens, clicks, meetings, form fills per contact | `GET /crm/v3/objects/contacts/{id}/associations/engagements` |
| **UTM parameters** | Campaign/source/medium on web visits | Google Analytics 4 `GET /v1beta/properties/{id}/runReport` or BigQuery GA4 export |
| **LinkedIn Ads API** | Ad impressions and clicks by company | `GET https://api.linkedin.com/v2/adAnalyticsV2` — requires `r_ads_reporting` scope |
| **Google Ads API** | Clicks, impressions, conversions | `GoogleAdsService.SearchStream` — requires OAuth2 service account |
| **Email Bison** | Email send/open/click events | `GET /api/campaigns/{id}/stats` — already in use in this project stack |
| **HubSpot Deals** | Deal source, stage, close date, amount | `GET /crm/v3/objects/deals` with associations |

## Attribution Model

```python
def w_shaped(touchpoints: list[Touchpoint]) -> dict[str, float]:
    n = len(touchpoints)
    if n == 0: return {}
    if n == 1: return {touchpoints[0].id: 1.0}
    if n == 2: return {touchpoints[0].id: 0.5, touchpoints[-1].id: 0.5}
    # First touch 40%, last touch 40%, middle touches share 20%
    weights = {touchpoints[0].id: 0.40, touchpoints[-1].id: 0.40}
    middle = touchpoints[1:-1]
    per_middle = 0.20 / len(middle) if middle else 0
    for t in middle: weights[t.id] = per_middle
    return weights
```

## Tests

```python
test_w_shaped_single_touch()
test_w_shaped_two_touches()
test_w_shaped_many_touches_sums_to_1()
test_utm_parsing_from_url()
test_touchpoint_dedup()
test_hubspot_deal_association()
```
