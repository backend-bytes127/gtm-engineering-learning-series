"""Run the waterfall. Sequential on purpose: no claim is made about concurrent use."""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from .ledger import DONE, RESERVED, UNKNOWN, CapReached, Ledger
from .models import STATUSES, VALID, Answer, Contact, Provider, RateLimited, ServerError, TimedOut

MAX_ATTEMPTS = 3
ERROR = "error"


@dataclass(frozen=True)
class Outcome:
    contact: str
    email: str = ""
    provider: str = ""
    stopped_by_cap: bool = False
    tried: tuple[str, ...] = ()


def _parse(raw: object) -> Answer:
    if not isinstance(raw, dict) or raw.get("status") not in STATUSES or not isinstance(raw.get("email", ""), str):
        raise ValueError("malformed provider payload")
    return Answer(raw["status"], raw.get("email", ""))


def _call(provider: Provider, contact: Contact, ledger: Ledger, cap: int | None) -> Answer | None:
    """The answer for one provider, from the ledger if we already asked. None means no usable answer."""
    name, key, terms = provider.terms.name, contact.key, provider.terms
    row = ledger.get(name, key)
    if row is not None:  # includes cached misses, and unresolved rows that must never be called again
        return row.answer if row.state == DONE and row.answer.status != ERROR else None
    ledger.reserve(name, key, terms.price_micros, cap)
    for _ in range(MAX_ATTEMPTS):
        try:
            raw = provider.lookup(contact)
        except (RateLimited, ServerError):
            continue
        except TimedOut:
            ledger.settle(name, key, UNKNOWN, Answer(""), terms.price_micros)
            return None
        try:
            answer = _parse(raw)
        except ValueError:  # it replied, so assume it billed; do not ask again
            ledger.settle(name, key, DONE, Answer(ERROR), terms.price_micros)
            return None
        ledger.settle(name, key, DONE, answer, terms.cost(answer))
        return answer
    ledger.release(name, key)  # every attempt was refused unbilled, so a later run may try again
    return None


def enrich(contact: Contact, providers: Sequence[Provider], ledger: Ledger, cap: int | None = None) -> Outcome:
    tried: list[str] = []
    for provider in providers:
        try:
            answer = _call(provider, contact, ledger, cap)
        except CapReached:
            return Outcome(contact.key, stopped_by_cap=True, tried=tuple(tried))
        tried.append(provider.terms.name)
        if answer is not None and answer.status == VALID and answer.email:  # catch_all and invalid are not accepted
            return Outcome(contact.key, answer.email, provider.terms.name, tried=tuple(tried))
    return Outcome(contact.key, tried=tuple(tried))


def run(contacts: Iterable[Contact], providers: Sequence[Provider], ledger: Ledger, cap: int | None = None) -> list[Outcome]:
    return [enrich(c, providers, ledger, cap) for c in contacts]


def unresolved(ledger: Ledger) -> int:
    """Calls whose billing is not known: timeouts, and reservations left behind by a stopped run."""
    return ledger.count(UNKNOWN) + ledger.count(RESERVED)
