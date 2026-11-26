"""A seeded synthetic world with planted incrementality. Every user and number here is invented.

Causal structure: a hidden intent score drives both who sees what and who buys (confounding).
Paid social, webinars and non-brand search also raise later interest, which causes more site
visits, brand searches and direct visits (mediation). Brand search and direct have no effect
on buying. All random draws are made once, so switching a channel off replays the same users
and gives their counterfactual outcome.

Attribution code must never import this module's parameters; only evaluation reads them.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np

CHANNELS = ("paid_social", "display", "nonbrand_search", "webinar", "retargeting", "email", "brand_search", "direct")
SWITCHABLE = ("paid_social", "display", "nonbrand_search", "webinar", "retargeting", "email", "brand_search")
# Direct is not something a team buys or can switch off, so it is never a "player" in the causal truth.


@dataclass(frozen=True)
class WorldParams:
    base_logit: float = -4.2
    intent_on_conversion: float = 1.0
    targeting: float = 1.0  # 0 makes every exposure independent of hidden intent
    cascade: float = 1.0  # 0 removes the path from earlier channels into later ones
    lift: dict[str, float] = field(
        default_factory=lambda: {
            "paid_social": 0.25,
            "display": 0.05,
            "nonbrand_search": 0.40,
            "webinar": 0.90,
            "retargeting": 0.10,
            "email": 0.35,
            "brand_search": 0.0,
            "direct": 0.0,
        }
    )
    awareness: dict[str, float] = field(default_factory=lambda: {"paid_social": 0.5, "nonbrand_search": 0.3, "webinar": 0.4})


def null_params(params: WorldParams) -> WorldParams:
    """No channel changes anything: every attributed conversion would have happened anyway."""
    return replace(params, lift={c: 0.0 for c in CHANNELS}, awareness={})


def untargeted_params(params: WorldParams) -> WorldParams:
    """The friendliest case for attribution: no channel is aimed at keen people or triggered by another."""
    return replace(params, targeting=0.0, cascade=0.0)


def closer_params(params: WorldParams) -> WorldParams:
    """The mirror image of the base world: late channels (including brand search) do the real work."""
    lift = {"paid_social": 0.05, "display": 0.02, "nonbrand_search": 0.10, "webinar": 0.15}
    lift |= {"retargeting": 0.70, "email": 0.70, "brand_search": 0.60, "direct": 0.0}
    return replace(params, lift=lift, awareness={})


@dataclass(frozen=True)
class Draws:
    intent: np.ndarray
    exposure: dict[str, np.ndarray]
    visit: np.ndarray
    convert: np.ndarray


def draw(n_users: int, seed: int) -> Draws:
    if n_users <= 0:
        raise ValueError("n_users must be positive")
    rng = np.random.default_rng(seed)
    return Draws(rng.standard_normal(n_users), {c: rng.random(n_users) for c in CHANNELS}, rng.random(n_users), rng.random(n_users))


@dataclass(frozen=True)
class Outcome:
    exposed: dict[str, np.ndarray]
    converted: np.ndarray


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-x))


def simulate(params: WorldParams, draws: Draws, off: frozenset[str] = frozenset()) -> Outcome:
    """Run the same users with the channels in `off` switched off for everybody."""
    unknown = off - set(CHANNELS)
    if unknown:
        raise ValueError(f"unknown channels: {sorted(unknown)}")
    seen_intent = params.targeting * draws.intent
    u, exposed = draws.exposure, {}

    def expose(channel: str, probability: np.ndarray | float) -> None:
        exposed[channel] = np.zeros(len(draws.intent), dtype=bool) if channel in off else u[channel] < probability

    expose("paid_social", 0.35)
    expose("display", 0.45)
    expose("nonbrand_search", _sigmoid(-1.4 + 0.8 * seen_intent))
    expose("webinar", _sigmoid(-3.0 + 0.7 * seen_intent))
    interest = seen_intent + params.cascade * sum(w * exposed[c] for c, w in params.awareness.items())
    visit = (draws.visit < _sigmoid(-0.8 + 1.2 * interest)) | (exposed["nonbrand_search"] & (params.cascade > 0))
    gate = visit if params.cascade > 0 else draws.visit < 0.4
    expose("retargeting", 0.65 * gate)
    expose("email", _sigmoid(-0.5 + 0.5 * seen_intent) * (0.7 if params.cascade == 0 else gate * 0.9 + 0.1))
    follow = 0.8 * visit * (params.cascade > 0)
    expose("brand_search", _sigmoid(-2.4 + 1.5 * interest + follow))
    expose("direct", _sigmoid(-2.0 + 1.2 * interest + follow))
    logit = params.base_logit + params.intent_on_conversion * draws.intent
    for channel in CHANNELS:
        logit = logit + params.lift.get(channel, 0.0) * exposed[channel]
    return Outcome(exposed, draws.convert < _sigmoid(logit))
