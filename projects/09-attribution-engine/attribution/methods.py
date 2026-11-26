"""Run every attribution method on one prepared dataset."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .allocate import UNITS_PER_CONVERSION, allocate_total
from .heuristics import RULES, channel_units
from .journeys import Prepared, channel_names, path_table
from .markov import markov_shares
from .shapley import clipped_shares, shapley_raw

METHODS = [*RULES, "markov", "shapley_count", "shapley_rate"]
LABELS = {
    "first_touch": "First touch",
    "last_touch": "Last touch",
    "linear": "Linear",
    "time_decay": "Time decay (7d)",
    "u_shaped": "U-shaped 40/20/40",
    "markov": "Markov removal",
    "shapley_count": "Shapley (count game)",
    "shapley_rate": "Shapley (rate game)",
}


@dataclass(frozen=True)
class Attribution:
    units: pd.DataFrame  # channel x method, integer units
    n_conversions: int
    negative_rate_channels: list[str]  # channels whose raw rate-game value was below zero

    def credit(self) -> pd.DataFrame:
        return self.units / UNITS_PER_CONVERSION

    def shares(self) -> pd.DataFrame:
        return self.units / max(1, self.n_conversions * UNITS_PER_CONVERSION)


class CreditError(RuntimeError):
    """Raised when a method's credit does not add up to the number of conversions."""


def check_totals(units: pd.DataFrame, n_conversions: int) -> None:
    expected = n_conversions * UNITS_PER_CONVERSION
    for method in units.columns:
        got = int(units[method].sum())
        if got != expected:
            raise CreditError(f"{method}: credited {got} units, expected {expected}")
        if (units[method] < 0).any():
            raise CreditError(f"{method}: negative credit")


def attribute(prepared: Prepared) -> Attribution:
    if prepared.n_conversions == 0:
        raise ValueError("no conversion has an eligible touch, so there is nothing to attribute")
    channels = channel_names(prepared)
    table = path_table(prepared)
    units = channel_units(prepared)
    rate_raw = shapley_raw(table, channels, "rate")
    aggregate = {
        "markov": markov_shares(table, channels),
        "shapley_count": clipped_shares(shapley_raw(table, channels, "count")),
        "shapley_rate": clipped_shares(rate_raw),
    }
    for method, shares in aggregate.items():
        allocated = allocate_total(shares, prepared.n_conversions)
        units[method] = np.array([allocated[c] for c in channels], dtype=np.int64)
    units = units[METHODS]
    check_totals(units, prepared.n_conversions)
    return Attribution(units, prepared.n_conversions, sorted(c for c, v in rate_raw.items() if v < 0))


def total_variation(a: pd.Series, b: pd.Series) -> float:
    """Share of all credit that would have to move to turn one allocation into the other (0 to 1)."""
    index = a.index.union(b.index)
    return float(0.5 * np.abs(a.reindex(index, fill_value=0) - b.reindex(index, fill_value=0)).sum())
