"""A seeded, synthetic world with the answers planted, so every result can be checked. Nothing here is real."""
from __future__ import annotations

import random
from dataclasses import dataclass

from .models import (
    CATCH_ALL,
    INVALID,
    MICROS,
    NOT_FOUND,
    PER_CALL,
    PER_HIT,
    VALID,
    Answer,
    Contact,
    RateLimited,
    ServerError,
    Terms,
    TimedOut,
)

TERMS = (
    Terms("alder", 10_000, PER_CALL),
    Terms("birch", 40_000, PER_HIT),
    Terms("cedar", 25_000, PER_HIT),
    Terms("dogwood", 90_000, PER_HIT),
)
# How many of 1,000 contacts each combination of providers can find (A=alder ... D=dogwood). 100 are unfindable.
OVERLAP = {
    "": 100, "A": 150, "B": 90, "C": 80, "D": 70, "AB": 140, "AC": 90, "AD": 30, "BC": 60, "BD": 30, "CD": 30,
    "ABC": 70, "ABD": 20, "ACD": 10, "BCD": 10, "ABCD": 20,
}
FAULTS = ("rate_limit_once", "rate_limit_always", "server_error_once", "server_error_always", "malformed", "timeout")
FAULTS_PER_KIND = 25  # of each kind, for each provider
WRONG_VALID, CATCH, BAD = 0.04, 0.06, 0.03


@dataclass(frozen=True)
class Planted:
    answer: Answer
    fault: str = ""


@dataclass(frozen=True)
class World:
    contacts: tuple[Contact, ...]
    truth: dict[str, str]  # contact key -> real address ("" if unfindable). The engine never reads this.
    table: dict[tuple[str, str], Planted]  # (provider, contact key) -> what that provider will do


def make_world(seed: int = 7) -> World:
    rng = random.Random(seed)
    combos = [combo for combo, n in OVERLAP.items() for _ in range(n)]
    rng.shuffle(combos)
    contacts = tuple(Contact(f"Person{i:04d}", f"Test{i:04d}", f"company{i % 180:03d}.example") for i in range(len(combos)))
    truth, table = {}, {}
    for contact, combo in zip(contacts, combos):
        real = f"{contact.first}.{contact.last}@{contact.domain}".lower()
        truth[contact.key] = real if combo else ""
        for letter, terms in zip("ABCD", TERMS):
            answer = Answer(NOT_FOUND)
            if letter in combo:
                roll = rng.random()
                if roll < WRONG_VALID:  # the provider says "verified" and is wrong
                    answer = Answer(VALID, "info@" + contact.domain)
                elif roll < WRONG_VALID + CATCH:
                    answer = Answer(CATCH_ALL, real)
                elif roll < WRONG_VALID + CATCH + BAD:
                    answer = Answer(INVALID, real)
                else:
                    answer = Answer(VALID, real)
            table[(terms.name, contact.key)] = Planted(answer)
    for terms in TERMS:
        picked = rng.sample(contacts, FAULTS_PER_KIND * len(FAULTS))
        for i, contact in enumerate(picked):
            key = (terms.name, contact.key)
            table[key] = Planted(table[key].answer, FAULTS[i // FAULTS_PER_KIND])
    return World(contacts, truth, table)


class FakeProvider:
    """Behaves as planted, and keeps its own bill so tests can compare it with the engine's ledger."""

    def __init__(self, terms: Terms, world: World):
        self.terms, self._table = terms, world.table
        self.attempts: dict[str, int] = {}
        self.billed: list[tuple[str, int]] = []

    def lookup(self, contact: Contact) -> object:
        planted = self._table[(self.terms.name, contact.key)]
        n = self.attempts[contact.key] = self.attempts.get(contact.key, 0) + 1
        fault = planted.fault
        if fault == "rate_limit_always" or (fault == "rate_limit_once" and n == 1):
            raise RateLimited
        if fault == "server_error_always" or (fault == "server_error_once" and n == 1):
            raise ServerError
        if fault in ("timeout", "malformed"):
            self.billed.append((contact.key, self.terms.price_micros))
            if fault == "timeout":
                raise TimedOut
            return {"unexpected": "<html>"}
        self.billed.append((contact.key, self.terms.cost(planted.answer)))
        return {"status": planted.answer.status, "email": planted.answer.email}


def make_providers(world: World) -> dict[str, FakeProvider]:
    return {t.name: FakeProvider(t, world) for t in TERMS}


def dollars(micros: int) -> str:
    return f"${micros / MICROS:,.2f}"
