"""One synthetic world, run end to end: simulate, emit raw events, normalise, attribute, compare."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .channels import normalise_pairs
from .journeys import Prepared, prepare
from .methods import Attribution, attribute
from .truth import Truth, causal_truth
from .world import WorldParams, draw, simulate
from .world_events import emit

LOOKBACK_DAYS = 32.0  # longer than the whole synthetic window, so only the point-in-time rule applies


@dataclass(frozen=True)
class Scenario:
    events: pd.DataFrame  # raw landing events plus the normalised `channel`
    journeys: pd.DataFrame
    prepared: Prepared
    attribution: Attribution
    truth: Truth


def run_scenario(params: WorldParams, n_users: int, seed: int, lookback_days: float = LOOKBACK_DAYS) -> Scenario:
    draws = draw(n_users, seed)
    events, journeys = emit(simulate(params, draws), seed + 1)
    events = events.assign(channel=normalise_pairs(events["landing_url"].tolist(), events["referrer"].tolist()))
    prepared = prepare(events, journeys, lookback_days)
    return Scenario(events, journeys, prepared, attribute(prepared), causal_truth(params, draws))
