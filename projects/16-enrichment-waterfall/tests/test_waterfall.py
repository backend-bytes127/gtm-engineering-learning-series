from itertools import permutations

import pytest

from waterfall import report
from waterfall.__main__ import main
from waterfall.engine import enrich, run, unresolved
from waterfall.ledger import DONE, RESERVED, UNKNOWN, Ledger
from waterfall.models import PER_CALL, VALID, Contact, RateLimited, Terms
from waterfall.oracle import expected
from waterfall.world import FAULTS, OVERLAP, TERMS, make_providers, make_world

WORLD = make_world(7)
NAMES = tuple(t.name for t in TERMS)


def go(order, ledger=None, cap=None, providers=None):
    providers = providers or make_providers(WORLD)
    ledger = ledger or Ledger()
    return run(WORLD.contacts, [providers[n] for n in order], ledger, cap), ledger, providers


def billed(providers):
    return sum(len(p.billed) for p in providers.values()), sum(m for p in providers.values() for _, m in p.billed)


@pytest.mark.parametrize("order", list(permutations(NAMES)))
def test_calls_spend_and_results_match_the_independent_oracle_for_every_order(order):
    outcomes, ledger, providers = go(order)
    calls, spend, accepted = expected(WORLD, order)
    assert billed(providers) == (calls, spend)
    assert ledger.committed() == spend
    assert {o.contact: o.email for o in outcomes if o.email} == accepted


def test_the_world_has_the_planted_overlap_and_every_failure_state():
    assert sum(OVERLAP.values()) == len(WORLD.contacts) == 1000
    assert sum(1 for v in WORLD.truth.values() if not v) == OVERLAP[""]
    for kind in FAULTS:
        assert sum(1 for p in WORLD.table.values() if p.fault == kind) >= 20


@pytest.mark.parametrize("cap", [0, 9_999, 10_000, 1_234_567, 20_000_000])
def test_the_spend_cap_is_never_exceeded(cap):
    outcomes, ledger, providers = go(NAMES, cap=cap)
    assert ledger.committed() <= cap and billed(providers)[1] <= cap
    assert any(o.stopped_by_cap for o in outcomes)


def test_money_already_reserved_counts_against_the_cap():
    ledger = Ledger()
    ledger.reserve("alder", "someone-else", 10_000, None)
    out = enrich(WORLD.contacts[0], [make_providers(WORLD)["alder"]], ledger, cap=15_000)
    assert out.stopped_by_cap


def test_a_second_run_makes_no_billable_call_and_costs_nothing():
    first, ledger, providers = go(NAMES)
    before_calls, before_spend = billed(providers)[0], ledger.committed()
    second, _, _ = go(NAMES, ledger=ledger, providers=providers)
    assert billed(providers)[0] == before_calls and ledger.committed() == before_spend
    assert [o.email for o in first] == [o.email for o in second]


class Crashes:
    """Bills, then the process dies before the answer can be recorded."""

    def __init__(self):
        self.terms, self.bills = Terms("crash", 5_000, PER_CALL), 0

    def lookup(self, contact):
        self.bills += 1
        raise KeyboardInterrupt


def test_a_run_stopped_after_a_call_never_pays_for_it_again(tmp_path):
    path, provider = str(tmp_path / "ledger.sqlite"), Crashes()
    contact = Contact("A", "B", "c.example")
    ledger = Ledger(path)
    with pytest.raises(KeyboardInterrupt):
        enrich(contact, [provider], ledger)
    ledger.close()
    restarted = Ledger(path)
    assert enrich(contact, [provider], restarted).email == ""
    assert provider.bills == 1 and restarted.count(RESERVED) == 1 and unresolved(restarted) == 1
    assert restarted.committed() == 5_000


def test_timeouts_are_counted_as_spent_and_marked_unknown():
    _, ledger, _ = go(NAMES)
    assert ledger.count(UNKNOWN) > 0 and ledger.count(RESERVED) == 0


def test_refused_calls_are_unbilled_bounded_and_may_be_retried_later():
    class Refuses:
        terms, tries = Terms("busy", 7_000, PER_CALL), 0

        def lookup(self, contact):
            self.tries += 1
            raise RateLimited

    provider, ledger = Refuses(), Ledger()
    contact = Contact("A", "B", "c.example")
    enrich(contact, [provider], ledger)
    assert provider.tries == 3 and ledger.committed() == 0 and ledger.count(DONE) == 0
    enrich(contact, [provider], ledger)
    assert provider.tries == 6


@pytest.mark.parametrize("payload", [None, [], {"status": "maybe"}, {"status": VALID, "email": 5}])
def test_a_malformed_reply_is_billed_once_and_not_accepted(payload):
    class Odd:
        terms, tries = Terms("odd", 3_000, PER_CALL), 0

        def lookup(self, contact):
            self.tries += 1
            return payload

    provider, ledger = Odd(), Ledger()
    contact = Contact("A", "B", "c.example")
    assert enrich(contact, [provider], ledger).email == "" == enrich(contact, [provider], ledger).email
    assert provider.tries == 1 and ledger.committed() == 3_000


def test_spacing_and_case_do_not_create_a_second_paid_lookup():
    assert Contact("Ana ", "LOPEZ", "X.example").key == Contact("ana", "lopez", "x.example").key


def test_wrong_but_verified_answers_are_reported_not_hidden():
    result = report.evaluate(WORLD, NAMES)
    assert 0 < result.correct < result.accepted
    assert sum(n for _, n in result.marginal) == result.accepted


def test_the_report_is_identical_for_the_same_seed_and_says_it_is_synthetic(tmp_path):
    a, b = tmp_path / "a.md", tmp_path / "b.md"
    assert main(["--out", str(a)]) == 0 == main(["--out", str(b)])
    assert a.read_bytes() == b.read_bytes() and "SYNTHETIC" in a.read_text()
    assert report.call_everyone_spend(WORLD) > report.evaluate(WORLD, NAMES).spend
