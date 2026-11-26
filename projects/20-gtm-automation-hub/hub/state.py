"""Replay, dedupe and dead-letter bookkeeping as pure functions: every change returns a new state."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from hub.signing import TOLERANCE_SECONDS

EVENT_RETENTION_SECONDS = 7 * 24 * 3600
MAX_EVENTS = 2000
MAX_DEAD_LETTERS = 100


@dataclass(frozen=True)
class State:
    signatures: Mapping[str, int] = field(default_factory=dict)  # signature -> expiry (epoch seconds)
    events: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)  # dedupe key -> record
    dead_letters: tuple[Mapping[str, Any], ...] = ()


def is_replay(state: State, signature: str, now: float) -> bool:
    return state.signatures.get(signature, -1) >= now


def remember_signature(state: State, signature: str, timestamp: int, now: float) -> State:
    """Keep a signature for as long as its timestamp could still pass the freshness check."""
    live = {key: expiry for key, expiry in state.signatures.items() if expiry >= now}
    return replace(state, signatures={**live, signature: timestamp + TOLERANCE_SECONDS})


def record_event(state: State, key: str, record: Mapping[str, Any], now: float) -> State:
    live = {k: v for k, v in state.events.items() if now - v["at"] <= EVENT_RETENTION_SECONDS and k != key}
    kept = list(live.items())[-(MAX_EVENTS - 1) :]
    return replace(state, events={**dict(kept), key: {**record, "at": int(now)}})


def add_dead_letter(state: State, reason: str, key: str | None, detail: Any, now: float) -> State:
    """Bounded, newest last. Only authenticated requests may reach this."""
    entry = {"reason": reason, "key": key, "detail": detail, "at": int(now)}
    return replace(state, dead_letters=(*state.dead_letters, entry)[-MAX_DEAD_LETTERS:])
