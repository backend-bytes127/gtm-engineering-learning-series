# Project 17 — Signal and Fit Account Scoring with Backtest

> **Status:** 📋 Specced, not started | **Priority:** P1 | **Effort estimate:** ~3 days

## Problem

Most scoring models are never checked against outcomes, and an old signal counts as much as a new one.

## Proposed solution

Score accounts on fit x time-decayed intent, route by tier, and backtest the weights against outcome labels. Every score shows the evidence behind it.

## What it must prove

- Conversion rate of the top tier against the whole list, on data held out from weight tuning
- How the ranking changes when each signal is removed
- Share of scored signals that carry a source and a date

## Rules

- A missing signal is reported as unknown, not as absent
- Weights are configuration, not code
- Synthetic outcome data is labelled as synthetic in every report

Why this project is on the list: see [the research notes](../../docs/research.md).
