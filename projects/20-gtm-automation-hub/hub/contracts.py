"""Input contracts for the two inbound payloads. Each validator returns a list of error codes; empty means valid."""

from __future__ import annotations

import math
import re
from typing import Any

SIGNAL_TYPES = ("pricing_page_visit", "demo_request", "job_change", "funding_news")
TIERS = ("A_assist", "B_nudge", "C_none")
ALERT_TIER = "A_assist"

_ID = re.compile(r"[A-Za-z0-9_.:-]{1,80}")
_DOMAIN = re.compile(r"(?=.{4,100}\Z)([a-z0-9]([a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,24}")
_UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")


def _matches(pattern: re.Pattern[str], value: Any) -> bool:
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def _text(value: Any, limit: int) -> bool:
    return isinstance(value, str) and 0 < len(value.strip()) and len(value) <= limit


def signal_errors(event: Any) -> list[str]:
    if not isinstance(event, dict):
        return ["not_an_object"]
    checks = {
        "event_id": _matches(_ID, event.get("event_id")),
        "type": event.get("type") in SIGNAL_TYPES,
        "account_domain": _matches(_DOMAIN, event.get("account_domain")),
        "occurred_at": _matches(_UTC, event.get("occurred_at")),
        "source": _text(event.get("source"), 40),
    }
    return [name for name, ok in checks.items() if not ok]


def _probability(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and 0 <= value <= 1


def pql_errors(event: Any) -> list[str]:
    """Shape of a project 07 routing task, plus the score and decision time a reviewer needs."""
    if not isinstance(event, dict):
        return ["not_an_object"]
    visitor, version = event.get("visitor_key"), event.get("score_version")
    checks = {
        "visitor_key": _matches(_ID, visitor),
        "score_version": _matches(_ID, version),
        "idempotency_key": _matches(_ID, event.get("idempotency_key")) and event.get("idempotency_key") == f"{visitor}:{version}",
        "tier": event.get("tier") in TIERS,
        "action": _text(event.get("action"), 200),
        "score": _probability(event.get("score")),
        "decided_at": _matches(_UTC, event.get("decided_at")),
    }
    return [name for name, ok in checks.items() if not ok]
