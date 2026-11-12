# ADR-0010: Autonomous AI messaging, with the safety rules in code

Status: accepted
Date: 2026-11-12

## Context
Until now every message was a template a person wrote and approved. The owner wanted Claude to write personalised follow-ups and answer replies on its own, with a switch to go back to human approval. Autonomy means a model sends messages to real people from a real LinkedIn account with nobody watching, so the design has to assume the model will sometimes be wrong, refuse, or be manipulated by the text it is replying to.

## Decision
- **Three modes, stored in the database and changeable at any time:** `off` (templates as written), `review` (Claude drafts, a person approves each message), `autonomous` (Claude drafts and the draft is approved automatically). Switching away from autonomous pulls back anything the AI approved but has not yet sent.
- **Every AI output becomes a `draft` row** with a status (pending, approved, sent, rejected, escalated, ...) and who decided (`human` or `auto`). The same table drives review, the audit trail and the inbox. A step is only sent from an approved draft.
- **The rules that matter are plain code, not prompts** (`ai/guard.py`, `ai/replies.py`):
  - A reply that asks us to stop, or says "not interested", ends all automation for that person and adds them to the suppression list, before any AI is called, and even when AI mode is off.
  - Replies about money, legal matters, complaints, or anything very long go to a person.
  - After `max_auto_replies` automatic answers (default 3) a person takes over.
  - Output checks: no links, email addresses or phone numbers, no placeholders, a length limit per channel, no talk of its own instructions.
  - Anything that fails, is refused, is cut off, cannot be parsed or errors **becomes an escalation**: failure never turns into a send.
- **Untrusted input:** the contact's words are fenced in `<contact_message>` tags with angle brackets removed so they cannot close the fence, and the prompt says not to follow instructions inside them. The model has no tools, so the worst a successful injection can do is write a message, which still has to pass the output checks.
- **Disclosure on by default:** autonomous messages end with "sent by <name>'s AI assistant". It can be switched off in settings, with a warning in the confirmation dialog (people in the EU are entitled to know they are talking to an AI).
- **Fences around cost and speed:** a daily cap on AI requests (`AI_DAILY_CALL_CAP`, default 100), a delay before automatic replies, replies only inside the sending hours and under the daily LinkedIn message cap, and the live kill switch stops AI replies too.
- **Model and API use:** the official `anthropic` SDK, model `claude-opus-5-5` (override with `ANTHROPIC_MODEL`), no temperature or thinking-budget parameters (not accepted on this model), and no time or random values in prompts. The server-side refusal fallback is deliberately **not** enabled: a refusal on an outreach message should reach a person, not be retried on another model.

## Alternatives considered
- **Prompt-only guardrails** ("never reply to pricing questions"). A model can be argued out of a prompt; it cannot be argued out of a regex that runs first.
- **Autonomous with no off switch or approval queue.** Faster, but there would be no way to trust it or to recover from a bad day.
- **Letting the AI call tools** (send, stop, book). More powerful, much larger blast radius. The AI only returns text and a decision; code acts on it.

## Consequences
- (+) The default is unchanged (off), review mode gives a safe on-ramp, and every AI message is stored with who approved it.
- (+) All of it is tested with a fake Claude: 120+ tests cover the guard, drafting, the flows, and the API.
- (-) The keyword rules are blunt: "what does it cost?" is allowed but "pricing" escalates, and an opt-out in a language other than English or Dutch is only caught if the model judges it. A person reviews anything the rules do not catch only in review mode.
- (-) Not yet exercised against the real Claude API (no key at the time of writing), so the first live runs should use review mode.
