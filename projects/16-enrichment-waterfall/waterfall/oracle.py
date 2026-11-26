"""A second, deliberately simple calculation of what a correct run must produce. Shares no code with the engine."""
from __future__ import annotations

from collections.abc import Sequence

from .world import TERMS, World

NO_ANSWER_FREE = ("rate_limit_always", "server_error_always")


def expected(world: World, order: Sequence[str]) -> tuple[int, int, dict[str, str]]:
    """(billed calls, spend in micros, accepted e-mail per contact) for an uncapped first run."""
    price = {t.name: (t.price_micros, t.charge) for t in TERMS}
    calls = spend = 0
    accepted: dict[str, str] = {}
    for contact in world.contacts:
        for name in order:
            planted = world.table[(name, contact.key)]
            if planted.fault in NO_ANSWER_FREE:
                continue
            calls += 1
            amount, charge = price[name]
            if planted.fault in ("timeout", "malformed"):
                spend += amount
                continue
            if charge == "per_call" or planted.answer.email:
                spend += amount
            if planted.answer.status == "valid":
                accepted[contact.key] = planted.answer.email
                break
    return calls, spend, accepted
