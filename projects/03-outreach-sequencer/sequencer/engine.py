"""The engine: launch gate, the send loop (`tick`), and stop rules (`record_event`).

Everything here takes the clock as an argument (`now`) and talks to the outside world only through a `Provider`,
so the whole loop is deterministic and testable. The three rules that matter most:

* Nothing goes live until `launch_checklist` is all green (validated list, approved templates, personalised drafts,
  sender profile, limits and stop rules set).
* A message is sent only if its template is approved *as it is now*, the window is open and the daily limit has room.
* Reply, bounce or booked meeting stops the contact immediately; an unsubscribe always does.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from . import constants as C
from .models import Checklist, Contact, Resolved, Sender, Step, Template
from .provider import Provider
from .rules import SendingRules, window_verdict
from .sequence import sequence_errors
from .store import Store, Tracked
from .templates import approval_hash, check_draft, render

MAX_SEND_ATTEMPTS = 3
ALREADY_CONNECTED = "already_connected"
DRAFT_CHECK = "Every draft personalised and within channel limits"
STATUS_RANK = {C.NOT_STARTED: 0, C.IN_SEQUENCE: 1, C.COMPLETED: 2, C.STOPPED: 2, C.REPLIED: 3, C.MEETING_BOOKED: 4}


class EngineError(RuntimeError):
    pass


@dataclass(frozen=True)
class LaunchResult:
    launched: int
    held: tuple[str, ...] = ()


@dataclass(frozen=True)
class SentTouch:
    contact: Contact
    step: Step
    touch_id: int
    at: datetime


@dataclass(frozen=True)
class TickResult:
    sent: tuple[SentTouch, ...] = ()
    skipped: int = 0
    deferred_limit: int = 0
    deferred_wait: int = 0
    blocked: int = 0
    held: int = 0
    window_closed: str = ""


def get_sender(store: Store) -> Sender | None:
    raw = store.get_setting("sender")
    if not isinstance(raw, dict) or not raw.get("name") or not raw.get("postal_address"):
        return None
    return Sender(raw["name"], raw.get("company", ""), raw["postal_address"], raw.get("reply_to", ""))


# ---------------------------------------------------------------- launch gate


def draft_problems(store: Store, name: str, sender: Sender) -> dict[str, list[str]]:
    seq, templates = store.sequence(name), store.templates()
    problems: dict[str, list[str]] = {}
    if seq is None:
        return problems
    for tracked in store.contacts(sequence=name, status=C.NOT_STARTED):
        for step in seq.steps:
            t = templates.get(step.template)
            if t is None:
                continue
            for issue in check_draft(t, tracked.contact, sender):
                problems.setdefault(tracked.contact.key, []).append(f"step {step.position}: {issue.message.split(': ')[-1]}")
    return problems


def launch_checklist(store: Store, name: str) -> Checklist:
    seq, templates = store.sequence(name), store.templates()
    rules, sender = store.get_rules(), get_sender(store)
    contacts = store.contacts(sequence=name)
    waiting = [c for c in contacts if c.status == C.NOT_STARTED]
    items: list[tuple[str, bool, str]] = []

    validated = store.get_setting("validation_run") is not None and bool(waiting)
    items.append(
        (
            "Contacts imported and validated",
            validated,
            f"{len(waiting)} contact(s) ready" if validated else "run validation, and import contacts for this sequence",
        )
    )

    errs = ["no such sequence"] if seq is None else sequence_errors(seq, templates)
    items.append(("Sequence is well-formed", not errs, "; ".join(errs) or f"{len(seq.steps)} steps"))

    used = {s.template for s in seq.steps} if seq else set()
    stale = sorted(t for t in used if t in templates and store.approved_hash(t) != approval_hash(templates[t]))
    items.append(
        (
            "Every template approved",
            not stale and bool(used),
            f"not approved (or edited since approval): {', '.join(stale)}" if stale else f"{len(used)} template(s) approved",
        )
    )

    if sender and seq and not errs:
        problems = draft_problems(store, name, sender)
        detail = (
            "; ".join(f"{k}: {', '.join(v)}" for k, v in sorted(problems.items())[:8])
            or f"{len(waiting)} contact(s) x {len(seq.steps)} steps"
        )
        items.append((DRAFT_CHECK, not problems, detail))
    else:
        items.append(
            ("Every draft personalised and within channel limits", False, "needs a valid sequence and a sender profile first")
        )

    items.append(
        ("Sender profile set", sender is not None, "name and postal address" if sender else "set sender name and postal address")
    )
    items.append(
        (
            "Sending limits, hours and stop rules set",
            rules is not None,
            f"stop on: {', '.join(rules.stop_on)}" if rules else "set the sending rules",
        )
    )
    return Checklist(tuple(items))


def launch(store: Store, name: str, now: datetime, hold_incomplete: bool = False) -> LaunchResult:
    if store.sequence(name) is None:
        raise EngineError(f"No sequence called '{name}'")
    if store.is_live(name):
        raise EngineError(f"Sequence '{name}' is already live")
    sender = get_sender(store)
    checklist = launch_checklist(store, name)
    blocking = [
        (label, detail) for label, ok, detail in checklist.items if not ok and not (hold_incomplete and label == DRAFT_CHECK)
    ]
    if blocking:
        raise EngineError("Not ready to launch. Fix: " + "; ".join(f"{label} ({detail})" for label, detail in blocking))
    held: list[str] = []
    if sender:  # only reached when every other check passed, so parking never happens on a refused launch
        for key in sorted(draft_problems(store, name, sender)) if hold_incomplete else []:
            store.set_state(key, C.STOPPED, C.REASON_DRAFT_INCOMPLETE)
            held.append(key)
    seq = store.sequence(name)
    first = timedelta(days=seq.steps[0].wait_days)
    waiting = store.contacts(sequence=name, status=C.NOT_STARTED)
    for t in waiting:
        store.set_state(t.contact.key, C.IN_SEQUENCE, next_step=1, next_due=now + first)
    store.mark_live(name, now)
    return LaunchResult(len(waiting), tuple(held))


# ---------------------------------------------------------------- send loop


def day_bounds(rules: SendingRules, now: datetime) -> tuple[datetime, datetime]:
    tz, day = ZoneInfo(rules.timezone), rules.local_date(now)
    return (datetime.combine(day, time.min, tzinfo=tz), datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz))


def _advance(store: Store, seq_len: int, steps: tuple[Step, ...], tracked: Tracked, now: datetime) -> None:
    key, position = tracked.contact.key, tracked.next_step
    if position >= seq_len:
        store.set_state(key, C.COMPLETED, next_step=position + 1)
    else:
        store.set_state(key, C.IN_SEQUENCE, next_step=position + 1, next_due=now + timedelta(days=steps[position].wait_days))


WAIT = "wait"


def _skip_reason(store: Store, c: Contact, step: Step, now: datetime) -> str:
    """Why this step cannot happen for this contact: "" if it can, WAIT if it must wait, else a reason to skip it."""
    if step.channel == C.EMAIL:
        return "" if c.email else "no_email"
    if not c.linkedin_url:
        return "no_linkedin"
    if step.channel == C.LINKEDIN_MESSAGE and not store.has_event(c.key, C.ACCEPTED):
        invite = store.latest_sent_touch(c.key, C.LINKEDIN_INVITE)
        if invite is None or now - invite.at >= timedelta(days=C.INVITE_EXPIRY_DAYS):
            return "invite_not_accepted"
        return WAIT
    return ""


def tick(
    store: Store,
    provider: Provider,
    now: datetime,
    *,
    only: frozenset[str] | None = None,
    caps: dict[str, int] | None = None,
    resolver: Callable[[Contact, Step, Template, Sender, datetime], Resolved | None] | None = None,
) -> TickResult:
    """Send what is due. `only` limits who may be contacted; `caps` can lower (never raise) the daily limits."""
    rules, sender = store.get_rules(), get_sender(store)
    if rules is None:
        raise EngineError("The sending rules are not set")
    if sender is None:
        raise EngineError("The sender profile is not set")
    verdict = window_verdict(rules, now)
    if not verdict.open:
        return TickResult(window_closed=verdict.reason)

    start, end = day_bounds(rules, now)
    used = {ch: store.count_sent(ch, start, end) for ch in C.CHANNELS}
    templates, sequences = store.templates(), {n: store.sequence(n) for n in store.sequence_names() if store.is_live(n)}
    sent: list[SentTouch] = []
    skipped = deferred_limit = deferred_wait = blocked = held = 0

    for tracked in store.due(now):
        if only is not None and tracked.contact.key not in only:
            continue
        c, seq = tracked.contact, sequences.get(tracked.contact.sequence)
        if seq is None or not 1 <= tracked.next_step <= len(seq.steps):
            continue
        step = seq.steps[tracked.next_step - 1]
        template = templates.get(step.template)

        reason = _skip_reason(store, c, step, now)
        if reason == WAIT:
            deferred_wait += 1
            continue
        if reason:
            store.add_touch(c.key, seq.name, step.position, step.channel, step.template, C.SKIPPED, now, reason=reason)
            _advance(store, len(seq.steps), seq.steps, tracked, now)
            skipped += 1
            continue
        if template is None or store.approved_hash(template.id) != approval_hash(template) or check_draft(template, c, sender):
            blocked += 1
            continue
        if used[step.channel] >= min(rules.limit_for(step.channel), (caps or {}).get(step.channel, 10**9)):
            deferred_limit += 1
            continue

        subject, body = render(template.subject, c, sender).text, render(template.body, c, sender).text
        draft_id = None
        if resolver is not None:
            resolved = resolver(c, step, template, sender, now)
            if resolved is not None:
                if resolved.hold:
                    held += 1
                    continue
                subject, body, draft_id = resolved.subject, resolved.body, resolved.draft_id
        result = provider.send(c, step, subject, body, now)
        if result.skip_reason:
            skipped_id = store.add_touch(
                c.key, seq.name, step.position, step.channel, step.template, C.SKIPPED, now, reason=result.skip_reason
            )
            if draft_id is not None:
                store.update_draft(draft_id, status="skipped")
            if result.skip_reason == ALREADY_CONNECTED and step.channel == C.LINKEDIN_INVITE:
                record_event(store, c.key, C.ACCEPTED, now, touch_id=skipped_id, detail="already connected")
            _advance(store, len(seq.steps), seq.steps, tracked, now)
            skipped += 1
            continue
        if result.retry_later:
            deferred_limit += 1
            continue
        if not result.ok:
            store.add_touch(c.key, seq.name, step.position, step.channel, step.template, C.FAILED, now, reason=result.error)
            if store.failed_attempts(c.key, step.position) >= MAX_SEND_ATTEMPTS:
                store.set_state(c.key, C.STOPPED, "send_failed")
            continue
        touch_id = store.add_touch(
            c.key,
            seq.name,
            step.position,
            step.channel,
            step.template,
            C.SENT,
            now,
            subject=subject,
            body=body,
            provider_id=result.provider_id,
        )
        used[step.channel] += 1
        if draft_id is not None:
            store.update_draft(draft_id, status="sent")
        sent.append(SentTouch(c, step, touch_id, now))
        _advance(store, len(seq.steps), seq.steps, tracked, now)
    return TickResult(tuple(sent), skipped, deferred_limit, deferred_wait, blocked, held)


# ---------------------------------------------------------------- events and stop rules


def record_event(store: Store, key: str, kind: str, at: datetime, touch_id: int | None = None, detail: str = "") -> bool:
    """Log what happened and apply the stop rules. Returns False if this exact event was already recorded."""
    if kind not in C.EVENT_KINDS:
        raise EngineError(f"Unknown event '{kind}' (use {', '.join(C.EVENT_KINDS)})")
    tracked = store.contact(key)
    if tracked is None:
        raise EngineError(f"No contact {key}")
    if touch_id is None:
        latest = store.latest_sent_touch(key)
        touch_id = latest.id if latest else None
    if not store.add_event(key, kind, at, touch_id, detail):
        return False

    rules = store.get_rules()
    stop_on = rules.stop_on if rules else C.STOP_RULE_KINDS
    current = tracked.status
    if kind == C.UNSUBSCRIBED:  # legal requirement: always stops, whatever the stop rules say
        store.suppress_contact(tracked.contact, "unsubscribed")
        store.set_state(key, C.STOPPED, C.REASON_OPTED_OUT)
    elif kind == C.BOUNCED and kind in stop_on:
        store.suppress_contact(tracked.contact, "bounced")
        if STATUS_RANK[current] < STATUS_RANK[C.REPLIED]:
            store.set_state(key, C.STOPPED, C.REASON_BOUNCED)
    elif kind == C.REPLY and kind in stop_on:
        if STATUS_RANK[current] < STATUS_RANK[C.REPLIED] and tracked.stop_reason != C.REASON_OPTED_OUT:
            store.set_state(key, C.REPLIED)
    elif kind == C.MEETING and kind in stop_on:
        if current != C.MEETING_BOOKED and tracked.stop_reason != C.REASON_OPTED_OUT:
            store.set_state(key, C.MEETING_BOOKED)
    return True
