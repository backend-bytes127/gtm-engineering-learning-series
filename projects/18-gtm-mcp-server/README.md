# Project 18 — GTM MCP Server

> **Status:** 📋 Specced, not started | **Priority:** P2 | **Effort estimate:** ~2 days

## Problem

Useful GTM scripts stay with whoever wrote them; reps cannot run them safely.

## Proposed solution

An MCP server that exposes enrichment, scoring and list-cleaning (built on projects 02, 16 and 17) as tools an AI assistant can call, read-only by default.

## What it must prove

- Tool calls that succeed on a fixed set of test requests
- Invalid or risky requests correctly refused

## Rules

- Anything that writes to a CRM or sends a message is off by default and needs explicit confirmation
- Inputs are schema-validated; spend and rate limits are enforced in the server, not in the prompt

Why this project is on the list: see [the research notes](../../docs/research.md).
