"""Move the clock forward hour by hour, run the engine, and feed it the events the simulated provider produces."""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from datetime import datetime, timedelta

from . import constants as C
from .engine import record_event, tick
from .provider import SimulatedProvider
from .store import Store


@dataclass(frozen=True)
class SimSummary:
    hours: int
    touches_sent: int
    events: int
    finished_early: bool


def run_simulation(store: Store, provider: SimulatedProvider, start: datetime, days: int) -> SimSummary:
    """Run up to `days` days. Stops early when nobody is left in a sequence and no events are pending."""
    pending: list[tuple[datetime, int, str, str, int]] = []  # (when, order, contact, kind, touch_id)
    order = sent = events = hours = 0
    store.set_setting("mode", {"provider": provider.name, "seed": provider.seed})
    for hour in range(days * 24):
        now = start + timedelta(hours=hour)
        hours = hour + 1
        while pending and pending[0][0] <= now:
            when, _, key, kind, touch_id = heapq.heappop(pending)
            if record_event(store, key, kind, when, touch_id=touch_id):
                events += 1
        for item in tick(store, provider, now).sent:
            sent += 1
            for follow in provider.follow_ups(item.contact, item.step, item.at):
                order += 1
                heapq.heappush(
                    pending, (item.at + timedelta(hours=follow.after_hours), order, item.contact.key, follow.kind, item.touch_id)
                )
        if not pending and not store.contacts(status=C.IN_SEQUENCE):
            return SimSummary(hours, sent, events, True)
    return SimSummary(hours, sent, events, False)
