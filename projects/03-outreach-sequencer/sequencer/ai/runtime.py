"""AI settings: the operator's mode (stored in the database) and the credentials (environment only, never in the database)."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from ..store import Store
from .client import DEFAULT_MODEL, AIClient

MODES = ("off", "review", "autonomous")
SDK_OVERRIDE: object | None = None  # tests put a fake SDK here
DEFAULT_DAILY_CALL_CAP = 100


@dataclass(frozen=True)
class AIEnv:
    api_key: str
    model: str
    daily_call_cap: int

    @property
    def configured(self) -> bool:
        return bool(self.api_key) or SDK_OVERRIDE is not None


@dataclass(frozen=True)
class AIMode:
    mode: str = "off"
    max_auto_replies: int = 3
    reply_delay_minutes: int = 2
    disclose: bool = True


def ai_env(env: Mapping[str, str] | None = None) -> AIEnv:
    e = os.environ if env is None else env
    try:
        cap = int(e.get("AI_DAILY_CALL_CAP", DEFAULT_DAILY_CALL_CAP))
    except ValueError:
        cap = DEFAULT_DAILY_CALL_CAP
    return AIEnv(
        e.get("ANTHROPIC_API_KEY", "").strip(), e.get("ANTHROPIC_MODEL", "").strip() or DEFAULT_MODEL, max(0, min(cap, 2000))
    )


def make_ai(env: Mapping[str, str] | None = None) -> AIClient | None:
    cfg = ai_env(env)
    if not cfg.configured:
        return None
    return AIClient(cfg.api_key, cfg.model, client=SDK_OVERRIDE)


def get_ai_mode(store: Store) -> AIMode:
    raw = store.get_setting("ai")
    if not isinstance(raw, dict) or raw.get("mode") not in MODES:
        return AIMode()
    return AIMode(
        raw["mode"],
        _bounded(raw.get("max_auto_replies"), 3, 0, 10),
        _bounded(raw.get("reply_delay_minutes"), 2, 0, 120),
        raw.get("disclose") is not False,
    )


def _bounded(value: object, default: int, low: int, high: int) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and low <= value <= high else default


def set_ai_mode(
    store: Store, mode: str, max_auto_replies: int, reply_delay_minutes: int, disclose: bool, now: datetime
) -> AIMode:
    """Save the mode. Leaving autonomous pulls back anything the AI approved on its own and has not sent yet."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {', '.join(MODES)}")
    if not 0 <= max_auto_replies <= 10:
        raise ValueError("max_auto_replies must be between 0 and 10")
    if not 0 <= reply_delay_minutes <= 120:
        raise ValueError("reply_delay_minutes must be between 0 and 120")
    if mode != "autonomous":
        for draft in store.drafts(status="approved"):
            if draft.decided_by == "auto":
                store.update_draft(draft.id, status="pending", decided_by="", decided_at=None, send_after=None)
    store.set_setting(
        "ai",
        {"mode": mode, "max_auto_replies": max_auto_replies, "reply_delay_minutes": reply_delay_minutes, "disclose": disclose},
    )
    return get_ai_mode(store)
