# Project 12 — Automated QBR Generator

> **Status:** 📋 Specced, not started | **Priority:** P3 | **Effort:** ~2 days

## Problem

Customer Success Managers spend 4–6 hours preparing each Quarterly Business Review deck: pulling usage data from the product, revenue from Stripe, goals from the last QBR, and writing narrative. This is mechanical work that should be automated.

## Proposed Solution

A Python pipeline that gathers account data from 3 sources, writes the narrative using Claude, and generates a Google Slides deck via the Slides API (or a Gamma presentation).

## Data Sources

| Source | What it provides | Access |
|---|---|---|
| **Product usage DB** | Feature adoption, DAU/WAU trend, top users, integrations used | SQLite or Mixpanel export |
| **Stripe** | MRR, payment history, plan tier, renewal date | `GET /v1/subscriptions` + `GET /v1/invoices` |
| **HubSpot** | Account goals (from previous QBR notes), CSM notes, NPS | Custom properties on Company object |
| **Google Slides API** | Deck creation + template fill | `presentations.create` + `presentations.batchUpdate` with `replaceAllText` |
| **Gamma MCP** (alternative) | AI-native deck generation from structured data | `mcp__claude_ai_Gamma__generate` — available in Claude Code MCP stack |
| **Claude Sonnet** | Narrative generation, insight extraction | `anthropic.messages.create` |

## Output

A branded slide deck with:
1. Executive summary (key metrics vs. last quarter)
2. Usage highlights (top 3 features, power users)
3. ROI calculation (time/cost saved vs. benchmark)
4. Goals review (last quarter hit/miss + next quarter goals)
5. Recommended next steps

## Tests

```python
test_data_assembly_from_three_sources()
test_narrative_covers_all_sections()
test_slides_template_fill_no_missing_vars()
test_roi_calculation_accuracy()
```
