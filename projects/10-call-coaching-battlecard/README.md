# Project 10 — AI Call Coaching & Battlecard Generator

> **Status:** 📋 Specced, not started | **Priority:** P2 | **Effort:** ~3 days

## Problem

Sales reps handle objections inconsistently. When a prospect raises "we already use Competitor X," one rep handles it well and another stumbles. Gong records every call, but no one watches recordings systematically to extract objection patterns and update playbooks.

## Proposed Solution

A Python pipeline that ingests call transcripts, extracts objections and competitor mentions using Claude Sonnet, and generates/updates a battlecard document automatically.

## Data Sources

| Source | What it provides | Access |
|---|---|---|
| **Gong API** | Call transcripts, metadata, participants | `GET https://api.gong.io/v2/calls/transcript` — requires OAuth2; Gong API access gated to paid plans |
| **Fireflies.ai API** (alternative) | Meeting transcripts (Zoom, Meet, Teams) | `POST https://api.fireflies.ai/graphql` — GraphQL API; free tier available |
| **Otter.ai API** (alternative) | Meeting transcripts | REST API — cheaper than Gong for demos |
| **Synthetic transcripts** | For testing without a Gong account | Generate with Claude: `"Write a 10-minute sales call transcript where the prospect raises price, competitor X, and timing objections"` |
| **Claude Sonnet** | Objection extraction, battlecard generation | `anthropic.messages.create(model="claude-sonnet-4-6")` |
| **Google Docs / Notion** | Battlecard storage and sharing | Composio Google Drive connector already available in stack |

## Claude Prompts

**Objection extractor:**
```
Extract all objections raised by the prospect in this transcript.
For each objection: {quote, category (price/timing/competitor/need), rep_response, effective (yes/no/partial)}.
Return JSON array.
Transcript: {transcript}
```

**Battlecard generator:**
```
Given these objection patterns from {n} calls, write a battlecard section for "{category}".
Include: the core objection, what NOT to say, what DOES work (from effective responses above), one-liner reframe.
Format as markdown.
```

## Tests

```python
test_transcript_parser_extracts_speaker_turns()
test_objection_extractor_returns_correct_schema()
test_competitor_mention_detection()
test_battlecard_markdown_format()
test_no_hallucinated_quotes()  # verify every quote appears verbatim in transcript
```
