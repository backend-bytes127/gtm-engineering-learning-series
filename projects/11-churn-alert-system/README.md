# Project 11 — Predictive Churn & NRR Alert System

> **Status:** 📋 Specced, not started | **Priority:** P1 | **Effort:** ~2 days

## Problem

Customer success teams find out about at-risk accounts at renewal time — when it is too late. By then, the champion has changed jobs, the team has stopped logging in, and the competitor has already done a pilot. Churn prediction needs to run weekly, not at renewal.

## Proposed Solution

A Python pipeline that tracks weekly usage signals per customer, computes a churn risk score, and alerts the CSM in Slack when an account crosses the risk threshold before their renewal date.

## Data Sources

| Source | What it provides | Access |
|---|---|---|
| **Product usage DB** | Weekly active users, feature adoption, login frequency per account | Direct DB query or Mixpanel/Amplitude export — synthetic data for demo |
| **Stripe** | MRR, subscription status, upcoming renewal dates | `GET /v1/subscriptions` with `expand[]=customer` — test mode |
| **HubSpot** | CSM owner, account health notes, NPS score | `GET /crm/v3/objects/companies/{id}` with custom properties |
| **Email Bison** | Email engagement for nurture sequences | `GET /api/campaigns/{id}/stats` — already in stack |
| **Slack Incoming Webhook** | CSM alert delivery | Slack App → Incoming Webhooks |

## Churn Risk Score

```python
RISK_SIGNALS = {
    "no_login_14d":           +30,
    "no_login_7d":            +15,
    "dau_dropped_50pct":      +25,
    "key_feature_unused_14d": +20,
    "support_tickets_spiked": +10,
    "champion_left":          +35,
    "nps_below_6":            +20,
    "renewal_in_30d":         +15,  # urgency multiplier
}
# RISK THRESHOLD: score >= 50 → alert CSM immediately
# Score 30-49 → flag in weekly digest
```

## Tests

```python
test_risk_score_no_login()
test_risk_score_champion_departure()
test_threshold_triggers_immediate_alert()
test_renewal_date_urgency_multiplier()
test_no_duplicate_alerts_within_7d()
test_slack_message_includes_renewal_date()
```
