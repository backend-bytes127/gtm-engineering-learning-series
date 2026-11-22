# Project 08 — Usage-Based Pricing Meter

> **Status:** 📋 Specced, not started | **Priority:** P2 | **Effort:** ~2 days

## Problem

API-first products that charge by consumption (tokens, API calls, storage) need a reliable meter that tracks usage per customer and pushes it to Stripe for invoicing. Without this, revenue leaks or billing errors break customer trust.

## Proposed Solution

A Python service that listens to internal usage events, aggregates them per customer per billing period, and reports to Stripe Metered Billing at the end of each period.

## Data Sources

| Source | Access |
|---|---|
| **Internal event log** | SQLite `usage_events` table: `(customer_id, event_type, quantity, timestamp)` |
| **Stripe Metered Billing API** | `POST /v1/subscription_items/{id}/usage_records` with `quantity` and `timestamp` — test mode key from Stripe dashboard |
| **Stripe Webhook** | `customer.subscription.updated` / `invoice.created` events to reconcile billing |
| **Stripe Meter API** (new) | `POST /v1/billing/meters` — Stripe's 2024 metering API, cleaner than legacy usage records |

## Input → Output

- **Input:** Usage event: `{customer_id, feature, quantity, ts}`
- **Processing:** Aggregate by customer + billing period → deduplicate → batch report to Stripe
- **Output:** Stripe usage record created; invoice preview matches expected amount

## Key Engineering Decisions

1. **Idempotency keys** on every Stripe API call — prevents double-billing on retry
2. **Local buffer** in SQLite — if Stripe is down, events queue locally and flush on reconnect
3. **Reconciliation job** — daily cron compares local totals vs. Stripe invoice preview; alerts on mismatch

## Tests

```python
test_aggregation_by_period()
test_idempotency_key_prevents_duplicate()
test_buffer_flushes_on_reconnect()
test_reconciliation_mismatch_alert()
test_stripe_payload_format()
```

## Effort

~10h: event ingestion (2h) + Stripe integration (3h) + reconciliation (2h) + tests (2h) + docs (1h)
