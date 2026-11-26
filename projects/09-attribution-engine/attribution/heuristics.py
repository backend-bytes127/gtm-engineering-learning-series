"""Rule-based attribution. Each rule only decides the weight of every touch in a converting journey."""
from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd

from .allocate import allocate_by_group
from .journeys import DAY, Prepared

HALF_LIFE_DAYS = 7.0
U_END_SHARE = 0.4


def _positions(converting: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    grouped = converting.groupby("journey_id", sort=False)
    return grouped.cumcount().to_numpy(), grouped["ts"].transform("size").to_numpy()


def first_touch(converting: pd.DataFrame) -> np.ndarray:
    index, _ = _positions(converting)
    return (index == 0).astype(float)


def last_touch(converting: pd.DataFrame) -> np.ndarray:
    index, size = _positions(converting)
    return (index == size - 1).astype(float)


def linear(converting: pd.DataFrame) -> np.ndarray:
    return np.ones(len(converting))


def time_decay(converting: pd.DataFrame, half_life_days: float = HALF_LIFE_DAYS) -> np.ndarray:
    if half_life_days <= 0:
        raise ValueError("half_life_days must be positive")
    age = (converting["end_ts"] - converting["ts"]) / DAY
    # Measured from each journey's newest touch: same ratios, and no journey can underflow to all zeros.
    newest = age.groupby(converting["journey_id"]).transform("min")
    return np.power(0.5, ((age - newest) / half_life_days).to_numpy())


def u_shaped(converting: pd.DataFrame) -> np.ndarray:
    """Position based 40/20/40. One touch takes all; two touches take half each. This is not W-shaped."""
    index, size = _positions(converting)
    middle = (1 - 2 * U_END_SHARE) / np.maximum(size - 2, 1)
    weights = np.where((index == 0) | (index == size - 1), U_END_SHARE, middle)
    weights = np.where(size == 2, 0.5, weights)
    return np.where(size == 1, 1.0, weights)


RULES: dict[str, Callable[[pd.DataFrame], np.ndarray]] = {
    "first_touch": first_touch,
    "last_touch": last_touch,
    "linear": linear,
    "time_decay": time_decay,
    "u_shaped": u_shaped,
}


def touch_units(prepared: Prepared) -> pd.DataFrame:
    """Converting touches with one integer-unit column per rule; each journey sums to one conversion."""
    converting = prepared.touches[prepared.touches["converted"]].reset_index(drop=True)
    groups = converting["journey_id"].to_numpy()
    units = {name: allocate_by_group(rule(converting), groups) for name, rule in RULES.items()}
    return converting.assign(**units)


def channel_units(prepared: Prepared) -> pd.DataFrame:
    """Channel by rule table of integer units."""
    channels = sorted(prepared.touches["channel"].unique().tolist())
    table = touch_units(prepared).groupby("channel")[list(RULES)].sum()
    return table.reindex(channels, fill_value=0).astype(np.int64)
