# Project 05 — Real-Time Intent Webhook Router

> **Status:** 📋 Specced, not started  
> **Priority:** P1  
> **Effort:** ~2 days  
> **Stack:** Python + n8n + Slack Webhooks + SQLite

---

## Problem

Marketing drives traffic to a pricing page. Sales has no idea a target account just visited. By the time the rep checks their CRM, the buying moment has cooled. There is no real-time signal connecting anonymous web behaviour to the sales motion.

## Proposed Solution

A lightweight Python service that:
1. Receives a webhook from a visitor-identification tool (Clearbit Reveal / Unify) whenever a known company visits the pricing or demo page
2. Looks up whether that company is in the ICP list (from Project 01) and not already a customer
3. Fires a Slack alert to the SDR channel with firmographic context + link to CRM record
4. Logs the event to SQLite for de-duplication (no double-pinging the same company within 48h)

---

## Data Sources

| Source | What it provides | How to get it |
|---|---|---|
| **Clearbit Reveal API** | IP → company name, domain, industry, headcount, Alexa rank | JavaScript snippet on the page; `GET https://reveal.clearbit.com/v1/companies/find?domain=<domain>` with API key. Now part of HubSpot Breeze Intelligence — legacy API key still works for standalone use. |
| **Unify GTM** (alternative) | IP → company, with higher match rate (~40–50%) | `POST https://api.unifygtm.com/v1/identify` with Bearer token; returns company + intent page list |
| **RB2B** (free tier) | Person-level de-anonymisation for US traffic | JavaScript pixel; pushes identified visitors to a Slack/webhook destination directly |
| **ICP list** | Target company domains from Project 01 output | Local SQLite `icp_companies` table seeded from `01-linkedin-icp-scraper` output |
| **HubSpot CRM** | Existing customer/deal check | `GET /crm/v3/objects/companies/search` — search by domain; if deal stage = `closed won`, skip alert |
| **Slack Incoming Webhook** | Alert delivery | Create a Slack App → Incoming Webhooks → `POST https://hooks.slack.com/services/…` |

---

## Input → Output Spec

**Input:** HTTP POST from visitor-identification vendor
```json
{
  "ip": "104.18.2.1",
  "page": "/pricing",
  "timestamp": "2025-11-22T14:30:00Z",
  "company": {
    "name": "Acme Corp",
    "domain": "acme.com",
    "industry": "SaaS",
    "employees": 120,
    "country": "US"
  }
}
```

**Processing:**
1. Check `icp_companies` table: is `acme.com` in ICP?
2. Check `alert_log` table: has `acme.com` been alerted in the last 48h?
3. Check HubSpot: is there a `closed won` deal for `acme.com`?
4. If pass all checks → build Slack message → POST to webhook → log to `alert_log`

**Output (Slack message):**
```
🎯 ICP Account on /pricing
Company: Acme Corp (acme.com)
Industry: SaaS | Employees: 120 | Country: US
Page visited: /pricing at 2:30 PM UTC

[View in HubSpot] [LinkedIn]
```

**Output (SQLite log row):**
```
alert_log: id, domain, page, alert_sent_at, suppressed_until
```

---

## n8n Workflow

```
Webhook Trigger (POST /intent)
  → Python node: ICP lookup + de-dup check
  → HTTP node: HubSpot company search
  → IF node: all checks pass?
    → YES → Slack message node + SQLite insert
    → NO  → SQLite insert (suppressed = true)
```

---

## Test Approach

```python
# Unit tests (pytest)
test_icp_lookup_hit()         # domain in ICP table → returns True
test_icp_lookup_miss()        # domain not in ICP → returns False
test_dedup_within_48h()       # domain alerted 24h ago → suppressed
test_dedup_after_48h()        # domain alerted 72h ago → alert fires
test_hubspot_customer_skip()  # closed-won deal → no alert
test_slack_payload_format()   # assert all required fields in Slack body

# Integration test
test_end_to_end_webhook()     # POST to /intent → mock Slack → verify row in alert_log
```

**Coverage target:** 80%+

---

## Effort Estimate

| Task | Hours |
|---|---|
| SQLite schema + ICP seed script | 1h |
| Webhook receiver (Flask/FastAPI) | 1h |
| ICP + de-dup + HubSpot check logic | 2h |
| Slack alert builder | 1h |
| n8n workflow wiring | 1h |
| Tests | 2h |
| Docs + README | 1h |
| **Total** | **~9h** |

---

## Priority Rationale

This is the simplest system that produces a live, real-time sales signal. It requires no product instrumentation, no CRM custom objects — just a JS pixel + a webhook endpoint. It is the most "show, don't tell" project in the portfolio: a working Slack bot that fires when a named account visits your pricing page is immediately understood by any SDR, AE or GTM leader.
