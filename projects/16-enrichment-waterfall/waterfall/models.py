"""Plain data types. Money is always an integer number of micro-dollars, so totals are exact."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

MICROS = 1_000_000
VALID, CATCH_ALL, INVALID, NOT_FOUND = "valid", "catch_all", "invalid", "not_found"
STATUSES = (VALID, CATCH_ALL, INVALID, NOT_FOUND)
PER_CALL, PER_HIT = "per_call", "per_hit"  # per_hit: charged only when an e-mail is returned


@dataclass(frozen=True)
class Contact:
    first: str
    last: str
    domain: str

    @property
    def key(self) -> str:
        return "|".join(" ".join(part.split()).casefold() for part in (self.first, self.last, self.domain))


@dataclass(frozen=True)
class Answer:
    status: str
    email: str = ""


@dataclass(frozen=True)
class Terms:
    name: str
    price_micros: int
    charge: str

    def cost(self, answer: Answer) -> int:
        return self.price_micros if self.charge == PER_CALL or answer.email else 0


class Provider(Protocol):
    terms: Terms

    def lookup(self, contact: Contact) -> object:
        """Return a mapping {"status": ..., "email": ...} or raise one of the errors below."""


class RateLimited(Exception):
    """429: the request was refused and not billed. Safe to retry."""


class ServerError(Exception):
    """500: assumed not billed by these (fictional) providers. Safe to retry a few times."""


class TimedOut(Exception):
    """No reply. The provider may or may not have billed, so it is counted as spent and never retried."""
