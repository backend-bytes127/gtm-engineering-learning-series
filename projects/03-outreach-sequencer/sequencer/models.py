"""Immutable records passed between steps. Functions return new objects; nothing is edited in place."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Contact:
    """One person. `row` is the 1-based data row in the source file, kept so every decision can be traced back."""

    row: int
    name: str = ""
    first_name: str = ""
    last_name: str = ""
    company: str = ""
    title: str = ""
    email: str = ""
    linkedin_url: str = ""
    sequence: str = ""
    source_status: str = ""
    flags: tuple[str, ...] = ()

    @property
    def key(self) -> str:
        return f"r{self.row:04d}"


@dataclass(frozen=True)
class Removed:
    """A record taken out of the list, with the reason (audit trail, like project 02's Removed Records)."""

    contact: Contact
    reason: str
    detail: str = ""


@dataclass(frozen=True)
class Step:
    position: int
    channel: str
    wait_days: int
    template: str


@dataclass(frozen=True)
class Sequence:
    name: str
    steps: tuple[Step, ...] = ()


@dataclass(frozen=True)
class Template:
    id: str
    channel: str
    body: str
    subject: str = ""


@dataclass(frozen=True)
class Sender:
    """Who the messages come from. Email needs a name and a postal address in the footer."""

    name: str
    company: str
    postal_address: str
    reply_to: str = ""


@dataclass(frozen=True)
class Issue:
    severity: str  # "error" blocks approval or launch; "warning" is shown but does not block
    code: str
    message: str


@dataclass(frozen=True)
class SendResult:
    """Outcome of one send attempt.

    `skip_reason` means this step cannot or need not happen for this person (the sequence moves on).
    `retry_later` means a temporary block such as a rate limit (nothing is logged and nothing counts as a failure).
    """

    ok: bool
    provider_id: str = ""
    error: str = ""
    skip_reason: str = ""
    retry_later: bool = False


@dataclass(frozen=True)
class FollowUp:
    """An event the (simulated) outside world will produce some hours after a touch."""

    kind: str
    after_hours: float


@dataclass(frozen=True)
class Checklist:
    items: tuple[tuple[str, bool, str], ...] = field(default_factory=tuple)  # (label, passed, detail)

    @property
    def ready(self) -> bool:
        return all(ok for _, ok, _ in self.items)


@dataclass(frozen=True)
class Resolved:
    """What an AI/review layer decided for one step: text to send, or a reason to hold it back for now."""

    subject: str = ""
    body: str = ""
    draft_id: int | None = None
    hold: str = ""
