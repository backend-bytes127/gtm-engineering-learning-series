# Project 16 — Enrichment Waterfall Engine

> **Status:** 📋 Specced, not started | **Priority:** P1 | **Effort estimate:** ~3 days

## Problem

One data provider rarely covers a whole list. Teams either accept the gaps or pay several vendors for the same contact.

## Proposed solution

A Python service that tries providers in cost order for each contact, stops at the first verified result, caches answers, and records which provider found what and at what cost. Providers sit behind one interface, with a fake provider so the whole pipeline runs without keys.

## What it must prove

- Coverage (email found and verified) per provider and combined
- Cost per verified contact, and spend avoided by stopping early and caching
- Bounce rate on a seed test, only if a real send is ever approved

## Rules

- No provider is called twice for the same contact
- A hard spend cap stops the run
- Tests run on synthetic data with fake providers; real keys stay in environment variables

Why this project is on the list: see [the research notes](../../docs/research.md).
