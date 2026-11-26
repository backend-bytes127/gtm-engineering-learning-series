"""What each channel really caused in the synthetic world, by replaying users with channels off."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .shapley import exact_shapley
from .world import CHANNELS, SWITCHABLE, Draws, WorldParams, simulate


@dataclass(frozen=True)
class Truth:
    table: pd.DataFrame  # one row per channel
    conversions_all_on: int
    conversions_all_off: int

    @property
    def incremental_total(self) -> int:
        return self.conversions_all_on - self.conversions_all_off

    def share(self) -> pd.Series:
        """Each channel's share of what marketing caused (all zeros if it caused nothing)."""
        causal = self.table["causal_shapley"]
        total = causal.sum()
        return causal / total if total > 0 else causal * 0.0


def causal_truth(params: WorldParams, draws: Draws, players: tuple[str, ...] = SWITCHABLE) -> Truth:
    """Two truths, both in conversions.

    leave_one_out: conversions lost if only this channel is switched off (what a holdout measures).
    causal_shapley: a fair split of (all on - all off) across channels; unlike leave-one-out it adds up.
    """
    n = len(players)
    values = np.zeros(1 << n)
    for mask in range(1 << n):
        off = frozenset(c for i, c in enumerate(players) if not (mask >> i) & 1)
        values[mask] = simulate(params, draws, off).converted.sum()
    full = (1 << n) - 1
    loo = {c: values[full] - values[full ^ (1 << i)] for i, c in enumerate(players)}
    shapley = dict(zip(players, exact_shapley(values, n)))
    table = pd.DataFrame(
        {"leave_one_out": [loo.get(c, 0.0) for c in CHANNELS], "causal_shapley": [shapley.get(c, 0.0) for c in CHANNELS]},
        index=pd.Index(CHANNELS, name="channel"),
    )
    return Truth(table, int(values[full]), int(values[0]))
