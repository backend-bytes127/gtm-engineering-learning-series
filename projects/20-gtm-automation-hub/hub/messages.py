"""Slack Block Kit payloads. ``hub/js`` builds the same JSON; the end-to-end run checks they are equal."""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import date
from typing import Any

from hub.churn import Account, by_reason

TOP_ACCOUNTS = 5
STALE_AFTER_DAYS = 8
APPROVE = "pql_approve"
DISMISS = "pql_dismiss"


def escape(text: str) -> str:
    """Slack's three control characters. Without this, input such as ``<!channel>`` would notify a whole channel."""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def pounds(pence: int) -> str:
    return f"£{(pence + 50) // 100:,}"


def three_decimals(value: float) -> str:
    """Round half up, as JavaScript's Math.round does."""
    return f"{math.floor(value * 1000 + 0.5) / 1000:.3f}"


def _section(text: str) -> dict[str, Any]:
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}


def _context(text: str) -> dict[str, Any]:
    return {"type": "context", "elements": [{"type": "mrkdwn", "text": text}]}


def _header(text: str) -> dict[str, Any]:
    return {"type": "header", "text": {"type": "plain_text", "text": text}}


def churn_digest(accounts: Sequence[Account], as_of: str, today: date) -> dict[str, Any]:
    total = sum(account.value_at_risk_pence for account in accounts)
    summary = f"Churn-risk queue as of {as_of}: {len(accounts)} accounts, {pounds(total)} score-weighted trailing revenue"
    reasons = "\n".join(f"• {escape(name)}: {count} ({pounds(pence)})" for name, count, pence in by_reason(accounts))
    top = "\n".join(
        f"{a.rank}. `{escape(a.customer_id)}` {escape(a.primary_reason)}, {pounds(a.value_at_risk_pence)}: {escape(a.suggested_action)}"
        for a in accounts[:TOP_ACCOUNTS]
    )
    blocks = [
        _header("Weekly churn-risk digest"),
        _section(summary),
        _section(f"*By primary reason*\n{reasons}"),
        _section(f"*Top {min(TOP_ACCOUNTS, len(accounts))} to review*\n{top}"),
        _context("A ranking aid, not a forecast of lost money. Reasons describe behaviour; they do not prove a cause."),
    ]
    age = (today - date.fromisoformat(as_of)).days
    if age > STALE_AFTER_DAYS:
        blocks = [*blocks, _context(f":warning: This queue is {age} days old. Check that the scoring job ran.")]
    return {"text": summary, "blocks": blocks}


def pql_alert(event: dict[str, Any]) -> dict[str, Any]:
    key = event["idempotency_key"]
    summary = f"PQL for review: {escape(event['visitor_key'])} (tier {event['tier']})"
    detail = (
        f"*Account key:* `{escape(event['visitor_key'])}`\n*Score:* {three_decimals(event['score'])} ({escape(event['score_version'])})\n"
        f"*Suggested action:* {escape(event['action'])}\n*Decided at:* {event['decided_at']}"
    )
    buttons = [_button("Approve", APPROVE, key, "primary"), _button("Dismiss", DISMISS, key, "danger")]
    return {
        "text": summary,
        "blocks": [
            _header("Product-qualified lead: needs a human"),
            _section(detail),
            {"type": "actions", "elements": buttons},
            _context("Approving records a decision only. Nothing is sent to the lead."),
        ],
    }


def _button(label: str, action_id: str, value: str, style: str) -> dict[str, Any]:
    return {"type": "button", "text": {"type": "plain_text", "text": label}, "action_id": action_id, "value": value, "style": style}


def signal_alert(event: dict[str, Any]) -> dict[str, Any]:
    summary = f"New signal: {event['type']} at {escape(event['account_domain'])}"
    detail = f"*{summary}*\n*Source:* {escape(event['source'])}\n*Occurred at:* {event['occurred_at']}"
    return {"text": summary, "blocks": [_section(detail), _context(f"Event `{escape(event['event_id'])}`")]}


def decision_update(key: str, decision: str, user_id: str) -> dict[str, Any]:
    text = f"PQL `{escape(key)}` {decision} by <@{user_id}>. Nothing was sent to the lead."
    return {"replace_original": True, "text": text, "blocks": [_section(text)]}
