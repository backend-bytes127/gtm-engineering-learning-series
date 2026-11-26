"""Compare every provider order on the synthetic world. The numbers describe this invented world only."""
from __future__ import annotations

from dataclasses import dataclass
from itertools import permutations

from .engine import run, unresolved
from .ledger import Ledger
from .world import TERMS, World, dollars, make_providers

BANNER = "SYNTHETIC DATA: invented providers, prices and contacts. Not a comparison of any real vendor."


@dataclass(frozen=True)
class OrderResult:
    order: tuple[str, ...]
    accepted: int
    correct: int
    spend: int
    calls: int
    unresolved: int
    marginal: tuple[tuple[str, int], ...]

    @property
    def per_correct(self) -> int:
        return self.spend // self.correct if self.correct else 0


def evaluate(world: World, order: tuple[str, ...]) -> OrderResult:
    providers, ledger = make_providers(world), Ledger()
    outcomes = run(world.contacts, [providers[n] for n in order], ledger)
    hits = [o for o in outcomes if o.email]
    correct = sum(1 for o in hits if o.email == world.truth[o.contact])
    marginal = tuple((n, sum(1 for o in hits if o.provider == n)) for n in order)
    result = OrderResult(order, len(hits), correct, ledger.committed(),
                         sum(len(p.billed) for p in providers.values()), unresolved(ledger), marginal)
    ledger.close()
    return result


def all_orders(world: World) -> list[OrderResult]:
    return sorted((evaluate(world, o) for o in permutations(t.name for t in TERMS)), key=lambda r: (r.per_correct, r.order))


def call_everyone_spend(world: World) -> int:
    """Baseline for 'spend avoided': ask every provider about every contact."""
    providers = make_providers(world)
    total = 0
    for contact in world.contacts:
        for p in providers.values():
            planted = world.table[(p.terms.name, contact.key)]
            if planted.fault in ("rate_limit_always", "server_error_always"):
                continue
            total += p.terms.price_micros if planted.fault else p.terms.cost(planted.answer)
    return total


def markdown(world: World) -> str:
    results = all_orders(world)
    cheapest, dearest = results[0], results[-1]
    findable = sum(1 for v in world.truth.values() if v)
    cheap_first = tuple(t.name for t in sorted(TERMS, key=lambda t: t.price_micros))
    rank = next(i for i, r in enumerate(results, 1) if r.order == cheap_first)
    base = call_everyone_spend(world)
    lines = [f"> {BANNER}", "", f"Contacts: {len(world.contacts)}; findable by at least one provider: {findable}.",
             f"Asking every provider about every contact would cost {dollars(base)}.",
             f"Cheapest-price-first ({' > '.join(cheap_first)}) ranks {rank} of {len(results)} on cost per correct e-mail.",
             f"Spread between best and worst order: ${cheapest.per_correct / 1e6:.4f} to ${dearest.per_correct / 1e6:.4f} per correct e-mail.",
             "", "| Order | Accepted | Correct | Wrong but 'verified' | Precision | Spend | Per accepted | Per correct | Unresolved |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        lines.append(f"| {' > '.join(r.order)} | {r.accepted} | {r.correct} | {r.accepted - r.correct} | "
                     f"{100 * r.correct / r.accepted:.1f}% | {dollars(r.spend)} | ${r.spend / r.accepted / 1e6:.4f} | "
                     f"${r.per_correct / 1e6:.4f} | {r.unresolved} |")
    lines += ["", "Marginal accepted per provider for the first order: " + ", ".join(f"{n} {c}" for n, c in cheapest.marginal) + "."]
    return "\n".join(lines) + "\n"
