"""Reference behaviour of the three webhooks: gate the request, deliver, then settle the state."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from hub import contracts, interactions, messages, signing
from hub import state as st

MAX_BODY_BYTES = 16_384
Send = Callable[[str, dict[str, Any]], bool]  # (target, message) -> delivered
SLACK_TARGET = "slack"


@dataclass(frozen=True)
class Settings:
    webhook_secret: str
    slack_signing_secret: str
    response_url_prefix: str = interactions.SLACK_PREFIX
    approvers: tuple[str, ...] = ()


@dataclass(frozen=True)
class Request:
    headers: Mapping[str, str]
    body: bytes


@dataclass(frozen=True)
class Result:
    status: int
    outcome: str
    state: st.State


def _gate(scheme: signing.Scheme, secret: str, request: Request, state: st.State, now: float) -> Result | st.State:
    """Authentication first. A rejected request leaves no trace, so strangers cannot fill the state."""
    if len(request.body) > MAX_BODY_BYTES:
        return Result(413, "too_large", state)
    check = signing.verify(scheme, secret, request.headers, request.body, now)
    if not check.ok:
        return Result(503 if check.reason == "not_configured" else 401, check.reason, state)
    lowered = {key.lower(): value for key, value in request.headers.items()}
    signature = lowered[scheme.signature_header]
    if st.is_replay(state, signature, now):
        return Result(409, "replay", state)
    return st.remember_signature(state, signature, int(lowered[scheme.timestamp_header]), now)


def _dead(state: st.State, status: int, reason: str, key: str | None, detail: Any, now: float) -> Result:
    return Result(status, reason, st.add_dead_letter(state, reason, key, detail, now))


def _reject_constant(name: str) -> None:
    """``NaN`` and ``Infinity`` are not JSON. JavaScript refuses them, so the reference does too."""
    raise ValueError(name)


def _parse(body: bytes, validate: Callable[[Any], list[str]], state: st.State, now: float) -> dict[str, Any] | Result:
    digest = hashlib.sha256(body).hexdigest()
    try:
        event = json.loads(body.decode("utf-8"), parse_constant=_reject_constant)
    except ValueError:
        return _dead(state, 422, "invalid_json", None, {"sha256": digest}, now)
    errors = validate(event)
    if errors:
        return _dead(state, 422, "invalid_schema", None, {"sha256": digest, "fields": errors}, now)
    return event


def _deliver(
    key: str, event: dict[str, Any], message: dict[str, Any], done: dict[str, Any], state: st.State, send: Send, now: float
) -> Result:
    if send(SLACK_TARGET, message):
        return Result(200, done["status"], st.record_event(state, key, done, now))
    # The key is not recorded, so the sender's next freshly signed attempt is processed again.
    return _dead(state, 502, "delivery_failed", key, {"event": event}, now)


def handle_signal(request: Request, state: st.State, settings: Settings, send: Send, now: float) -> Result:
    gated = _gate(signing.GENERIC, settings.webhook_secret, request, state, now)
    if isinstance(gated, Result):
        return gated
    event = _parse(request.body, contracts.signal_errors, gated, now)
    if isinstance(event, Result):
        return event
    key = event["event_id"]
    if key in gated.events:
        return Result(200, "duplicate", gated)
    return _deliver(key, event, messages.signal_alert(event), {"status": "delivered"}, gated, send, now)


def handle_pql(request: Request, state: st.State, settings: Settings, send: Send, now: float) -> Result:
    gated = _gate(signing.GENERIC, settings.webhook_secret, request, state, now)
    if isinstance(gated, Result):
        return gated
    event = _parse(request.body, contracts.pql_errors, gated, now)
    if isinstance(event, Result):
        return event
    if event["tier"] != contracts.ALERT_TIER:
        return Result(200, "not_routed", gated)
    key = event["idempotency_key"]
    if key in gated.events:
        return Result(200, "duplicate", gated)
    return _deliver(key, event, messages.pql_alert(event), {"status": "pending"}, gated, send, now)


def handle_interaction(request: Request, state: st.State, settings: Settings, send: Send, now: float) -> Result:
    """Slack treats a non-200 reply as an error, so business refusals still answer 200."""
    gated = _gate(signing.SLACK, settings.slack_signing_secret, request, state, now)
    if isinstance(gated, Result):
        return gated
    try:
        click = interactions.parse_click(request.body)
    except interactions.InteractionError:
        return _dead(gated, 200, "unsupported_interaction", None, {"sha256": hashlib.sha256(request.body).hexdigest()}, now)
    if not interactions.user_allowed(click.user_id, settings.approvers):
        return Result(200, "not_allowed", gated)
    record = gated.events.get(click.key)
    if record is None:
        return Result(200, "unknown_lead", gated)
    if record["status"] != "pending":
        return Result(200, "already_decided", gated)
    decided = st.record_event(gated, click.key, {"status": click.decision, "by": click.user_id}, now)
    if interactions.reply_url_allowed(click.response_url, settings.response_url_prefix):
        send(click.response_url, messages.decision_update(click.key, click.decision, click.user_id))
    return Result(200, click.decision, decided)
