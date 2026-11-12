"""Step 5: the sending rules. Daily limits, sending hours and active days, and which events stop a contact.

The ceilings in `constants` are hard caps: rules may lower them, never raise them. Following outbound-os, the
LinkedIn defaults are conservative, because a restricted LinkedIn account is the sender's real profile.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import constants as C

_DEFAULT_STOP = (C.REPLY, C.BOUNCED, C.MEETING)


class RulesError(ValueError):
    pass


@dataclass(frozen=True)
class SendingRules:
    timezone: str
    email_per_day: int
    linkedin_invites_per_day: int
    linkedin_messages_per_day: int
    start_hour: int
    end_hour: int
    active_days: tuple[int, ...]  # ISO weekdays, 1 = Monday ... 7 = Sunday
    stop_on: tuple[str, ...] = _DEFAULT_STOP

    def limit_for(self, channel: str) -> int:
        return {
            C.EMAIL: self.email_per_day,
            C.LINKEDIN_INVITE: self.linkedin_invites_per_day,
            C.LINKEDIN_MESSAGE: self.linkedin_messages_per_day,
        }[channel]

    def local(self, moment: datetime) -> datetime:
        if moment.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware")
        return moment.astimezone(ZoneInfo(self.timezone))

    def local_date(self, moment: datetime) -> date:
        return self.local(moment).date()

    def to_dict(self) -> dict:
        return {
            "timezone": self.timezone,
            "email_per_day": self.email_per_day,
            "linkedin_invites_per_day": self.linkedin_invites_per_day,
            "linkedin_messages_per_day": self.linkedin_messages_per_day,
            "start_hour": self.start_hour,
            "end_hour": self.end_hour,
            "active_days": list(self.active_days),
            "stop_on": list(self.stop_on),
        }


def _int_in(raw: dict, key: str, low: int, high: int) -> int:
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise RulesError(f"{key} is required and must be a whole number")
    if not low <= value <= high:
        raise RulesError(f"{key} must be between {low} and {high}, got {value}")
    return value


def parse_rules(raw: dict) -> SendingRules:
    tz = raw.get("timezone")
    try:
        ZoneInfo(str(tz))
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise RulesError(f"timezone '{tz}' is not a valid IANA timezone (e.g. Asia/Dubai)") from exc
    email = _int_in(raw, "email_per_day", 1, C.HARD_CAP_EMAIL_PER_DAY)
    invites = _int_in(raw, "linkedin_invites_per_day", 1, C.HARD_CAP_INVITES_PER_DAY)
    messages = _int_in(raw, "linkedin_messages_per_day", 1, C.HARD_CAP_MESSAGES_PER_DAY)
    start = _int_in(raw, "start_hour", 0, 23)
    end = _int_in(raw, "end_hour", 1, 24)
    if start >= end:
        raise RulesError(f"start_hour ({start}) must be before end_hour ({end})")
    days = raw.get("active_days")
    if not isinstance(days, list) or not days or not all(isinstance(d, int) and 1 <= d <= 7 for d in days):
        raise RulesError("active_days must be a non-empty list of weekdays 1 (Mon) to 7 (Sun)")
    stop = raw.get("stop_on", list(_DEFAULT_STOP))
    if not isinstance(stop, list) or not all(s in C.STOP_RULE_KINDS for s in stop):
        raise RulesError(f"stop_on may only contain: {', '.join(C.STOP_RULE_KINDS)}")
    return SendingRules(str(tz), email, invites, messages, start, end, tuple(sorted(set(days))), tuple(stop))


@dataclass(frozen=True)
class WindowVerdict:
    open: bool
    reason: str = ""


def window_verdict(rules: SendingRules, now: datetime) -> WindowVerdict:
    local = rules.local(now)
    if local.isoweekday() not in rules.active_days:
        return WindowVerdict(False, "outside_active_days")
    if not rules.start_hour <= local.hour < rules.end_hour:
        return WindowVerdict(False, "outside_hours")
    return WindowVerdict(True)
