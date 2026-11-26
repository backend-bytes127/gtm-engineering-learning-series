"""Apply the holdout design to every switchable channel in the planted world."""
from __future__ import annotations

import pandas as pd

from .holdout import naive_exposed_gap, replay_holdouts, required_total
from .world import SWITCHABLE, WorldParams, draw, simulate

HOLDOUT_FRACTION = 0.2


def holdout_table(params: WorldParams, n_users: int, seed: int, reps: int = 500) -> pd.DataFrame:
    draws = draw(n_users, seed)
    everything = simulate(params, draws)
    rows = []
    for channel in SWITCHABLE:
        without = simulate(params, draws, frozenset({channel})).converted
        replay = replay_holdouts(everything.converted, without, HOLDOUT_FRACTION, reps, seed + 1)
        rate_with, rate_without = float(everything.converted.mean()), float(without.mean())
        needed = None
        if rate_with != rate_without:
            needed = required_total(rate_with, rate_without, HOLDOUT_FRACTION)
        rows.append(
            {
                "channel": channel,
                "true_effect_pp": 100 * replay.true_difference,
                "holdout_mean_pp": 100 * replay.mean_estimate,
                "holdout_sd_pp": 100 * replay.sd_estimate,
                "interval_coverage": replay.coverage,
                "detected": replay.detected,
                "naive_exposed_gap_pp": 100 * naive_exposed_gap(everything.exposed[channel], everything.converted),
                "users_needed_80pct_power": needed,
            }
        )
    return pd.DataFrame(rows).set_index("channel").astype({"users_needed_80pct_power": "Int64"})
