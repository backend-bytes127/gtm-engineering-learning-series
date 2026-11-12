"""Live mode: send for real, but only to a short list you choose, under caps you cannot exceed from the UI.

State lives in the `live` setting: {"enabled": bool, "contacts": [keys]}. Stopping flips `enabled` off, which halts all
sending on the next tick (the kill switch). Replies arrive by webhook; accepted invites are found by polling the
account's connection list, and only while someone's invite is waiting.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from .. import constants as C
from ..engine import TickResult, day_bounds, record_event, tick
from ..provider import Provider
from ..report import CONVERSATION_STEP
from ..rules import window_verdict
from ..store import Store, to_iso
from .unipile import LinkedInLimit, UnipileClient, UnipileError, parse_webhook

HARD_MAX_CONTACTS = 10
DETAIL_MAX = 200


class LiveError(Exception):
    pass


def get_live(store: Store) -> dict:
    raw = store.get_setting("live")
    return raw if isinstance(raw, dict) else {"enabled": False, "contacts": []}


def start_live(store: Store, contacts: list[str], now: datetime) -> None:
    if not any(store.is_live(n) for n in store.sequence_names()):
        raise LiveError("Launch a sequence first")
    if store.get_setting("mode") not in (None, {"provider": "unipile"}):
        raise LiveError("A simulation was already run on this project. Reset the results to send for real.")
    if not contacts:
        raise LiveError("Choose at least one contact to send to")
    if len(set(contacts)) > HARD_MAX_CONTACTS:
        raise LiveError(f"Live sending is limited to {HARD_MAX_CONTACTS} contacts at a time")
    for key in contacts:
        tracked = store.contact(key)
        if tracked is None or tracked.status != C.IN_SEQUENCE:
            raise LiveError(f"{key} is not in the sequence (unknown, held back or already finished)")
    store.set_setting("mode", {"provider": "unipile"})
    store.set_setting("live", {"enabled": True, "contacts": sorted(set(contacts)), "started_at": to_iso(now)})


def stop_live(store: Store) -> None:
    live = get_live(store)
    store.set_setting("live", {**live, "enabled": False})


def run_live_tick(
    store: Store, provider: Provider, now: datetime, caps: dict[str, int], resolver: Callable | None = None
) -> TickResult | None:
    live = get_live(store)
    if not live.get("enabled"):
        return None
    result = tick(store, provider, now, only=frozenset(live["contacts"]), caps=caps, resolver=resolver)
    store.set_setting(
        "live_status",
        {
            "at": to_iso(now),
            "sent": len(result.sent),
            "skipped": result.skipped,
            "deferred_limit": result.deferred_limit,
            "window_closed": result.window_closed,
            "held": result.held,
        },
    )
    return result


def poll_accepts(store: Store, client: UnipileClient, now: datetime) -> int:
    """Record `accepted` for chosen contacts whose invite we sent and who now appear in our connections."""
    waiting: dict[str, tuple[str, int]] = {}
    for key in get_live(store).get("contacts", []):
        invite = store.latest_sent_touch(key, C.LINKEDIN_INVITE)
        pid = store.provider_id_for(key)
        if invite and pid and not store.has_event(key, C.ACCEPTED):
            waiting[pid] = (key, invite.id)
    if not waiting:
        return 0
    recorded = 0
    for pid in client.list_relation_ids(100) & waiting.keys():
        key, touch_id = waiting[pid]
        recorded += int(record_event(store, key, C.ACCEPTED, now, touch_id=touch_id, detail="connection found"))
    return recorded


def apply_webhook(
    store: Store,
    envelope: object,
    account_id: str,
    now: datetime,
    on_inbound: Callable[[str, str, str, datetime], None] | None = None,
) -> bool:
    """A verified inbound message from a chosen contact counts as a reply. Anyone else is ignored.

    Every new message from a chosen contact is stored and passed to `on_inbound` (the AI/safety layer). The return value
    says whether this message changed the contact's status to Replied.
    """
    event = parse_webhook(envelope, account_id)
    if event is None:
        return False
    key = store.contact_key_for_provider_id(event.provider_id)
    if key is None or key not in get_live(store).get("contacts", []):
        return False
    if not store.add_inbound(key, event.text, now, event.message_id, event.chat_id):
        return False  # the same message delivered twice
    recorded = False
    tracked = store.contact(key)
    if tracked is not None and tracked.status not in (C.REPLIED, C.MEETING_BOOKED):
        latest = store.latest_sent_touch(key)
        recorded = record_event(store, key, C.REPLY, now, touch_id=latest.id if latest else None, detail=event.text[:DETAIL_MAX])
    if on_inbound is not None:
        on_inbound(key, event.text, event.chat_id, now)
    return recorded


def send_approved_replies(store: Store, client: UnipileClient, now: datetime, message_cap: int) -> int:
    """Send approved replies that are due. Honours the kill switch, the sending hours and the daily cap."""
    live = get_live(store)
    rules = store.get_rules()
    if not live.get("enabled") or rules is None or not window_verdict(rules, now).open:
        return 0
    start, end = day_bounds(rules, now)
    sent_today = store.count_sent(C.LINKEDIN_MESSAGE, start, end)
    sent = 0
    for draft in store.drafts(status="approved", kind="reply"):
        if draft.contact_key not in live.get("contacts", []) or (draft.send_after and draft.send_after > now):
            continue
        tracked = store.contact(draft.contact_key)
        if tracked is None or tracked.status == C.STOPPED:
            store.update_draft(draft.id, status="cancelled", reason="the contact has stopped")
            continue
        if sent_today >= message_cap:
            break
        chats = [m.chat_id for m in store.inbound(draft.contact_key) if m.chat_id]
        if not chats:
            store.update_draft(draft.id, status="failed", reason="no chat to reply in")
            continue
        try:
            client.send_chat_message(chats[-1], draft.body)
        except LinkedInLimit:
            break
        except UnipileError as exc:
            store.update_draft(draft.id, status="failed", reason=str(exc)[:200])
            continue
        store.add_touch(
            draft.contact_key,
            "(conversation)",
            CONVERSATION_STEP + draft.id,
            C.LINKEDIN_MESSAGE,
            "ai_reply",
            C.SENT,
            now,
            body=draft.body,
            provider_id=f"reply:{draft.id}",
        )
        store.update_draft(draft.id, status="sent")
        sent_today += 1
        sent += 1
    return sent
