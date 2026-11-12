"""Turn a due sequence step into AI-written text, according to the mode.

off          nothing changes: the template is sent as written.
review       Claude drafts it; it waits for a person to approve (and optionally edit) it.
autonomous   Claude drafts it and it is approved automatically, as long as every code-level check passes.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from .. import constants as C
from ..models import Contact, Resolved, Sender, Step, Template
from ..store import Store
from ..templates import render
from .client import AIClient
from .drafting import draft_step
from .guard import DM_MAX, EMAIL_BODY_MAX, INVITE_MAX
from .runtime import AIMode, get_ai_mode

CHANNEL_LIMIT = {C.LINKEDIN_INVITE: INVITE_MAX, C.LINKEDIN_MESSAGE: DM_MAX, C.EMAIL: EMAIL_BODY_MAX}


def disclosure_line(sender: Sender) -> str:
    return f"— sent by {sender.name}'s AI assistant"


def thread_history(store: Store, contact_key: str) -> list[tuple[str, str]]:
    """Everything said so far, oldest first: what we sent and what they wrote back."""
    items = [(t.at, "out", t.body) for t in store.touches(contact_key) if t.status == C.SENT and t.body]
    items += [(m.at, "in", m.text) for m in store.inbound(contact_key)]
    return [(who, text) for _, who, text in sorted(items, key=lambda i: i[0])]


def day_start(now: datetime, timezone_name: str) -> tuple[datetime, datetime]:
    tz = ZoneInfo(timezone_name)
    day = now.astimezone(tz).date()
    return datetime.combine(day, time.min, tzinfo=tz), datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz)


def calls_left(store: Store, cap: int, now: datetime, timezone_name: str) -> int:
    start, end = day_start(now, timezone_name)
    return cap - store.count_ai_calls(start, end)


class StepResolver:
    def __init__(self, store: Store, ai: AIClient | None, daily_cap: int):
        self.store, self.ai, self.daily_cap = store, ai, daily_cap

    def __call__(self, contact: Contact, step: Step, template: Template, sender: Sender, now: datetime) -> Resolved | None:
        mode = get_ai_mode(self.store)
        if mode.mode == "off":
            return None
        existing = self.store.step_draft(contact.key, step.position)
        if existing is not None:
            if existing.status == "approved":
                return Resolved(existing.subject, existing.body, existing.id)
            return Resolved(hold=f"draft is {existing.status}")
        if self.ai is None:
            return Resolved(hold="AI is on but no API key is set")
        rules = self.store.get_rules()
        if calls_left(self.store, self.daily_cap, now, rules.timezone if rules else "UTC") <= 0:
            return Resolved(hold="daily AI limit reached")
        return self._draft(contact, step, template, sender, now, mode)

    def _draft(self, contact: Contact, step: Step, template: Template, sender: Sender, now: datetime, mode: AIMode) -> Resolved:
        seq = self.store.sequence(contact.sequence)
        autonomous = mode.mode == "autonomous"
        extras = [disclosure_line(sender)] if autonomous and mode.disclose else []
        if step.channel == C.EMAIL:
            extras.append(render("{{unsubscribe_line}}", contact, sender).text)
        reserved = sum(len(x) + 2 for x in extras)
        limit = CHANNEL_LIMIT[step.channel] - reserved
        brief = render(template.body, contact, sender).text
        if template.subject:
            brief = f"Subject idea: {render(template.subject, contact, sender).text}\n\n{brief}"
        result = draft_step(
            self.ai,
            contact=contact,
            sender=sender,
            channel=step.channel,
            position=step.position,
            total=len(seq.steps) if seq else step.position,
            brief=brief,
            history=thread_history(self.store, contact.key),
            limit=limit,
        )
        if result.decision != "send":
            self.store.add_draft(
                contact.key, "step", step.position, step.channel, "", "", "escalated", result.reason, result.model, now
            )
            return Resolved(hold="handed to you")
        body = "\n\n".join([result.message, *extras])
        status = "approved" if autonomous else "pending"
        draft_id = self.store.add_draft(
            contact.key,
            "step",
            step.position,
            step.channel,
            result.subject,
            body,
            status,
            result.reason,
            result.model,
            now,
            decided_by="auto" if autonomous else "",
        )
        return Resolved(result.subject, body, draft_id) if autonomous else Resolved(hold="awaiting your review")
