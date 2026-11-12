"""Per-visitor working sessions, kept in memory only and discarded after a period of inactivity.

A public copy of the app has no login, so every visitor must get their own isolated session; otherwise one person
could see another's uploaded data. Nothing is written to disk.
"""
from __future__ import annotations

import secrets
import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable
from dataclasses import dataclass, field

from .state import Session

TTL_SECONDS = 30 * 60
MAX_VISITORS = 100
RUNS_PER_MINUTE = 30


@dataclass
class Visitor:
    token: str = field(default_factory=lambda: secrets.token_urlsafe(24))
    session: Session = field(default_factory=Session)
    last_seen: float = 0.0


class VisitorStore:
    def __init__(self, ttl: float = TTL_SECONDS, limit: int = MAX_VISITORS, clock: Callable[[], float] = time.monotonic):
        self._ttl, self._limit, self._clock = ttl, limit, clock
        self._visitors: OrderedDict[str, Visitor] = OrderedDict()
        self._runs: deque[float] = deque()
        self._lock = threading.Lock()

    def _purge(self, now: float) -> None:
        for sid in [s for s, v in self._visitors.items() if now - v.last_seen > self._ttl]:
            del self._visitors[sid]

    def create(self) -> tuple[str, Visitor]:
        with self._lock:
            now = self._clock()
            self._purge(now)
            while len(self._visitors) >= self._limit:
                self._visitors.popitem(last=False)  # drop the least recently used
            sid, visitor = secrets.token_urlsafe(24), Visitor(last_seen=now)
            self._visitors[sid] = visitor
            return sid, visitor

    def get(self, sid: str) -> Visitor | None:
        with self._lock:
            now = self._clock()
            self._purge(now)
            visitor = self._visitors.get(sid)
            if visitor:
                visitor.last_seen = now
                self._visitors.move_to_end(sid)
            return visitor

    def allow_run(self) -> bool:
        """A shared cap on processing runs per minute, so one client cannot keep the server busy."""
        with self._lock:
            now = self._clock()
            while self._runs and now - self._runs[0] > 60:
                self._runs.popleft()
            if len(self._runs) >= RUNS_PER_MINUTE:
                return False
            self._runs.append(now)
            return True
