"""What happens when someone writes back. The first checks are plain code and run before any AI is involved:

1. Asking us to stop (or "not interested") ends all automation for that person immediately.
2. Money, legal, complaints, or very long messages go to a human.
3. After `max_auto_replies` automatic answers in a row, a human takes over.
Only then is Claude asked to draft a reply, and what it writes still has to pass the output checks.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from .. import constants as C
from ..engine import record_event
from ..models import Sender
from ..store import Store
from .client import AIClient
from .drafting import draft_reply
from .guard import DM_MAX, is_opt_out, needs_human
from .runtime import get_ai_mode
from .steps import calls_left, disclosure_line, thread_history

LIVE_DRAFT_STATES = ("pending", "approved")


def _supersede(store: Store, contact_key: str, now: datetime) -> None:
    for draft in store.drafts(kind="reply", contact_key=contact_key):
        if draft.status in LIVE_DRAFT_STATES:
            store.update_draft(draft.id, status="superseded", reason="they wrote again", decided_at=now)


def _escalate(store: Store, key: str, reason: str, now: datetime, in_reply_to: int | None = None, model: str = "") -> str:
    store.add_draft(key, "reply", None, C.LINKEDIN_MESSAGE, "", "", "escalated", reason, model, now, in_reply_to=in_reply_to)
    return "escalated"


def handle_inbound(
    store: Store, ai: AIClient | None, daily_cap: int, sender: Sender, contact_key: str, text: str, now: datetime
) -> str:
    """Returns what was done: opted_out, off, escalated, pending, approved or ignored."""
    tracked = store.contact(contact_key)
    if tracked is None:
        return "ignored"
    if is_opt_out(text):
        _supersede(store, contact_key, now)
        record_event(store, contact_key, C.UNSUBSCRIBED, now, detail="asked to stop")
        return "opted_out"
    mode = get_ai_mode(store)
    if mode.mode == "off":
        return "off"
    _supersede(store, contact_key, now)
    if needs_human(text):
        return _escalate(store, contact_key, "This reply needs you (price, legal, a complaint or a long message).", now)
    sent_replies = [d for d in store.drafts(kind="reply", contact_key=contact_key) if d.status == "sent"]
    if mode.mode == "autonomous" and len(sent_replies) >= mode.max_auto_replies:
        return _escalate(store, contact_key, f"The AI has already answered {len(sent_replies)} times. Over to you.", now)
    if ai is None:
        return _escalate(store, contact_key, "AI is on but no API key is set.", now)
    rules = store.get_rules()
    if calls_left(store, daily_cap, now, rules.timezone if rules else "UTC") <= 0:
        return _escalate(store, contact_key, "The daily AI limit was reached.", now)

    autonomous = mode.mode == "autonomous"
    extra = [disclosure_line(sender)] if autonomous and mode.disclose else []
    limit = DM_MAX - sum(len(x) + 2 for x in extra)
    result = draft_reply(
        ai,
        contact=tracked.contact,
        sender=sender,
        channel=C.LINKEDIN_MESSAGE,
        history=thread_history(store, contact_key),
        limit=limit,
    )
    if result.decision == "stop":
        record_event(store, contact_key, C.UNSUBSCRIBED, now, detail="the AI judged they want no more contact")
        return "opted_out"
    if result.decision != "send":
        return _escalate(store, contact_key, result.reason, now, model=result.model)
    body = "\n\n".join([result.message, *extra])
    if autonomous:
        send_after = now + timedelta(minutes=mode.reply_delay_minutes)
        store.add_draft(
            contact_key,
            "reply",
            None,
            C.LINKEDIN_MESSAGE,
            "",
            body,
            "approved",
            result.reason,
            result.model,
            now,
            send_after=send_after,
            decided_by="auto",
        )
        return "approved"
    store.add_draft(contact_key, "reply", None, C.LINKEDIN_MESSAGE, "", body, "pending", result.reason, result.model, now)
    return "pending"
