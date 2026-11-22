# Project 07 — PQL Scorer (Product Qualified Lead)

> **Status:** 📋 Specced, not started | **Priority:** P2 | **Effort:** ~2 days

## Problem

Sales teams get handed MQLs (marketing qualified leads) based on form fills and email opens — not on actual product usage. Reps waste time on leads that filled out a form once but never activated, while power users who hit the product hard never get a call.

## Proposed Solution

A Python service that reads product event data, computes a PQL score based on feature adoption milestones, and pushes high-score leads to HubSpot as `PQL` with a task for the SDR.

## Data Sources

| Source | Access |
|---|---|
| **Product event stream** | Segment webhooks (`identify`, `track` events) or direct DB query on `events` table — synthetic data acceptable for demo |
| **Mixpanel Export API** | `GET https://data.mixpanel.com/api/2.0/export` — raw event export by date range, requires project token + secret |
| **Amplitude Analytics API** | `GET https://amplitude.com/api/2/events/segmentation` — event counts by user, requires API key + secret |
| **HubSpot Contacts API** | `PATCH /crm/v3/objects/contacts/{id}` — update `pql_score` custom property + create task |
| **SQLite (local)** | Store computed scores + score history for trend analysis |

## Scoring Model (example)

```python
MILESTONES = {
    "signed_up":          1,
    "completed_onboarding": 5,
    "invited_teammate":   10,
    "connected_integration": 8,
    "exported_data":      7,
    "used_core_feature_3x": 15,
    "used_core_feature_7d": 20,
}
# PQL threshold: score >= 30 → alert sales
```

## Input → Output

- **Input:** Product events JSON (from Segment webhook or Mixpanel export)
- **Output:** HubSpot contact updated with `pql_score`, `pql_tier` (cold/warm/hot), SDR task created

## Tests

```python
test_score_calculation_from_events()
test_pql_threshold_triggers_alert()
test_hubspot_update_payload()
test_no_duplicate_tasks()
test_score_trend_stored_correctly()
```

## Effort

~10h: event parser (2h) + scoring engine (2h) + HubSpot integration (2h) + tests (3h) + docs (1h)
