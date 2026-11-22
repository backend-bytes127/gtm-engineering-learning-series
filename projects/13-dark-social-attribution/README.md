# Project 13 — Dark Social Attribution Bot

> **Status:** 📋 Specced, not started | **Priority:** P3 | **Effort:** ~1 day

## Problem

30–50% of B2B inbound leads come from "dark social" — Slack communities, private Discord servers, LinkedIn DMs, podcast recommendations, word-of-mouth. These channels show up as "direct" in Google Analytics, making it impossible to attribute revenue to community investment, thought leadership, or referral programs.

## Proposed Solution

A micro-survey triggered on the HubSpot form "thank you" page or first login that asks: "Where did you first hear about us?" Responses are stored and linked to the contact, enabling dark social attribution across the pipeline.

## Data Sources

| Source | What it provides | Access |
|---|---|---|
| **HubSpot Forms API** | Trigger survey after form submit; read responses | `GET /marketing/v3/forms/{formId}/submissions` |
| **Typeform API** (alternative) | More flexible survey UX | `GET https://api.typeform.com/forms/{id}/responses` |
| **HubSpot Contact API** | Save `dark_social_source` custom property | `PATCH /crm/v3/objects/contacts/{id}` |
| **SQLite** | Aggregate channel counts, link to deal outcomes | Local analytics table |
| **Claude Haiku** | Normalise free-text responses to canonical channels | "twitter" / "twitter/x" / "saw on X" → `twitter_x` |

## Channel Taxonomy

```python
CHANNELS = [
    "twitter_x", "linkedin", "slack_community", "discord",
    "podcast", "newsletter", "word_of_mouth", "google_search",
    "youtube", "reddit", "referral_partner", "other"
]
```

## Tests

```python
test_response_normalisation_twitter_variants()
test_custom_property_update_hubspot()
test_channel_aggregation_report()
test_dark_social_pct_of_total_inbound()
```
