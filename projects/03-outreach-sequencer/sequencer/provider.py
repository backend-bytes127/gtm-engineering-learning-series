"""Providers: how a touch actually leaves. The engine only knows the `Provider` protocol.

`SimulatedProvider` sends nothing. It returns success and, for the demo and the tests, generates the replies,
bounces, accepts and meetings the outside world would produce, deterministically from a seed. Its rates are
made-up illustration values, not benchmarks. A real provider (a connected mailbox, Unipile, HeyReach, Instantly)
would implement `send` and feed real events back through `engine.record_event` from webhooks.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from . import constants as C
from .models import Contact, FollowUp, SendResult, Step


class Provider(Protocol):
    name: str

    def send(self, contact: Contact, step: Step, subject: str, body: str, now: datetime) -> SendResult: ...


@dataclass(frozen=True)
class SimProfile:
    """Probability of each outcome per touch. Reply odds fall for later steps by `step_decay` (multiplied per step)."""

    email_bounce: float = 0.04
    email_open: float = 0.55
    email_reply: float = 0.07
    email_unsubscribe: float = 0.01
    invite_accept: float = 0.38
    dm_reply: float = 0.20
    meeting_given_reply: float = 0.35
    step_decay: float = 0.8


class SimulatedProvider:
    name = "simulated"

    def __init__(self, seed: int = 7, profile: SimProfile | None = None, fail_keys: frozenset[str] = frozenset()):
        self.seed = seed
        self.profile = profile or SimProfile()
        self._fail_keys = fail_keys  # contact keys whose sends fail, to exercise the retry path

    def _u(self, contact: Contact, step: Step, label: str) -> float:
        digest = hashlib.sha256(f"{self.seed}|{contact.key}|{step.position}|{label}".encode()).digest()
        return int.from_bytes(digest[:8], "big") / 2**64

    def send(self, contact: Contact, step: Step, subject: str, body: str, now: datetime) -> SendResult:
        if contact.key in self._fail_keys:
            return SendResult(False, error="simulated provider failure")
        return SendResult(True, provider_id=f"sim-{contact.key}-s{step.position}")

    def follow_ups(self, contact: Contact, step: Step, sent_at: datetime) -> list[FollowUp]:
        """What happens next, as events with a delay in hours. Never starts a reply from a bounced or accepted-less touch."""
        p = self.profile
        decay = p.step_decay ** (step.position - 1)
        out: list[FollowUp] = []

        def hours(label: str, low: float, high: float) -> float:
            return round(low + self._u(contact, step, label + ".t") * (high - low), 2)

        replied = False
        if step.channel == C.EMAIL:
            if self._u(contact, step, "bounce") < p.email_bounce:
                return [FollowUp(C.BOUNCED, hours("bounce", 0.1, 2))]
            if self._u(contact, step, "open") < p.email_open:
                out.append(FollowUp(C.OPENED, hours("open", 1, 30)))
            if self._u(contact, step, "reply") < p.email_reply * decay:
                out.append(FollowUp(C.REPLY, hours("reply", 6, 72)))
                replied = True
            elif self._u(contact, step, "unsub") < p.email_unsubscribe:
                out.append(FollowUp(C.UNSUBSCRIBED, hours("unsub", 2, 48)))
        elif step.channel == C.LINKEDIN_INVITE:
            if self._u(contact, step, "accept") < p.invite_accept:
                out.append(FollowUp(C.ACCEPTED, hours("accept", 6, 120)))
        elif step.channel == C.LINKEDIN_MESSAGE and self._u(contact, step, "dm") < p.dm_reply * decay:
            out.append(FollowUp(C.REPLY, hours("dm", 4, 96)))
            replied = True
        if replied and self._u(contact, step, "meeting") < p.meeting_given_reply:
            reply_at = next(f.after_hours for f in out if f.kind == C.REPLY)
            out.append(FollowUp(C.MEETING, round(reply_at + hours("meeting", 12, 72), 2)))
        return out
