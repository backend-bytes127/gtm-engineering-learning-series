# ADR-0009: Sending goes through a provider interface; the bundled provider only simulates

Status: accepted
Date: 2026-11-10

## Context
A sequencer's logic (timing, limits, stop rules, status, reporting) can be written and tested without ever sending a message, but a demo with no outcomes shows nothing. Real sending needs credentials for a mailbox and a LinkedIn automation service, and real recipients. outbound-os keeps sending behind adapters (one module per provider) for the same reason.

## Decision
- The engine depends only on `Provider.send(contact, step, subject, body, now) -> SendResult`. Time is an argument, never read from the clock inside the engine.
- `SimulatedProvider` sends nothing. Given a seed it deterministically decides, per contact and step, whether the message bounces, is opened, replied to, accepted (invites) or leads to a meeting, and after how many hours. The simulator replays those as events at the right simulated time. Rates are explicit, adjustable and **made up**; every report built from them is labelled "Simulated results".
- A real provider implements `send`, and its webhooks (reply, bounce, connection accepted, unsubscribe) call `engine.record_event`. Nothing else in the engine changes.

## Alternatives considered
- **Mock the network in tests only.** Tests pass, but there is no runnable demo and no realistic report to design against.
- **Integrate a real sender now.** Needs live credentials and contacts, cannot be reproduced by someone cloning the repo, and risks real sends from a learning project.

## Consequences
- (+) The whole loop is deterministic: the same seed gives the same report, so a golden file can guard it (`expected-output/`).
- (+) Rule compliance can be proved over a 60-day run: no send outside hours or active days, none over a daily limit, none after a stop event.
- (-) The numbers in the demo say nothing about real campaign performance. The summary says so in its first line.
