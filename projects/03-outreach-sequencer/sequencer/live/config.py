"""Live-mode settings, read from environment variables (never from the database, never from the browser)."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from .. import constants as C

DEFAULT_INVITES = 3
DEFAULT_MESSAGES = 5


@dataclass(frozen=True)
class LiveSettings:
    api_key: str
    account_id: str
    webhook_secret: str
    max_invites: int
    max_messages: int

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.account_id)

    @property
    def caps(self) -> dict[str, int]:
        return {C.LINKEDIN_INVITE: self.max_invites, C.LINKEDIN_MESSAGE: self.max_messages}


def _cap(raw: str | None, default: int, ceiling: int) -> int:
    try:
        value = int(raw) if raw else default
    except ValueError:
        value = default
    return max(0, min(value, ceiling))


def live_settings(env: Mapping[str, str] | None = None) -> LiveSettings:
    e = os.environ if env is None else env
    return LiveSettings(
        e.get("UNIPILE_API_KEY", "").strip(),
        e.get("UNIPILE_ACCOUNT_ID", "").strip(),
        e.get("UNIPILE_WEBHOOK_SECRET", "").strip(),
        _cap(e.get("LIVE_MAX_INVITES_PER_DAY"), DEFAULT_INVITES, C.HARD_CAP_INVITES_PER_DAY),
        _cap(e.get("LIVE_MAX_MESSAGES_PER_DAY"), DEFAULT_MESSAGES, C.HARD_CAP_MESSAGES_PER_DAY),
    )
