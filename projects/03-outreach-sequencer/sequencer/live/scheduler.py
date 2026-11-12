"""Background loop for live mode. One iteration is `step`, so it can be tested without threads or sleeping."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone

from ..ai.runtime import ai_env, get_ai_mode, make_ai
from ..ai.steps import StepResolver
from ..store import to_iso
from .config import live_settings
from .runner import get_live, poll_accepts, run_live_tick, send_approved_replies
from .unipile import Transport, UnipileClient, UnipileProvider, urllib_transport

log = logging.getLogger("sequencer.live")
TICK_SECONDS = 60
ACCEPT_POLL_MINUTES = 10


def step(ws, now: datetime, transport: Transport = urllib_transport, last_poll: datetime | None = None) -> datetime | None:
    """Run one live iteration. Returns the time of the last accept-poll. Never raises: problems are recorded for the UI."""
    cfg = live_settings()
    with ws.store() as s:
        live = get_live(s)
        if not (live.get("enabled") and cfg.configured):
            return last_poll
        try:
            client = UnipileClient(cfg.api_key, cfg.account_id, transport=transport)
            resolver = StepResolver(s, make_ai(), ai_env().daily_call_cap) if get_ai_mode(s).mode != "off" else None
            run_live_tick(s, UnipileProvider(client, remember=s.set_provider_id), now, cfg.caps, resolver=resolver)
            send_approved_replies(s, client, now, cfg.max_messages)
            if last_poll is None or now - last_poll >= timedelta(minutes=ACCEPT_POLL_MINUTES):
                poll_accepts(s, client, now)
                last_poll = now
            status = s.get_setting("live_status") or {}
            s.set_setting("live_status", {**status, "error": ""})
        except Exception as exc:  # keep the loop alive; the UI shows the last error
            log.exception("live iteration failed")
            status = s.get_setting("live_status") or {}
            s.set_setting("live_status", {**status, "at": to_iso(now), "error": f"{type(exc).__name__}: {str(exc)[:160]}"})
    return last_poll


class Scheduler(threading.Thread):
    def __init__(self, ws, transport: Transport = urllib_transport):
        super().__init__(daemon=True, name="live-scheduler")
        self._ws, self._transport, self._stop_event, self._last_poll = ws, transport, threading.Event(), None

    def run(self) -> None:
        while not self._stop_event.wait(TICK_SECONDS):
            try:
                self._last_poll = step(self._ws, datetime.now(timezone.utc), self._transport, self._last_poll)
            except Exception:  # a bad iteration must never end the loop
                log.exception("scheduler iteration crashed")

    def stop(self) -> None:
        self._stop_event.set()
