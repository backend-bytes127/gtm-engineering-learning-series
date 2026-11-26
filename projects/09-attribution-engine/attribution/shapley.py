"""Exact Shapley values over channels, with two different value functions.

"Shapley attribution" is not one method: the answer depends on what a coalition is worth.

* count game: v(S) = conversions from journeys whose channels all lie in S. It never looks at
  non-converting journeys and equals an equal split across each journey's distinct channels.
* rate game: v(S) = conversion rate of journeys whose channels all lie in S. It uses
  non-converting journeys, ignores volume, and can give a channel a negative value.
"""
from __future__ import annotations

from math import factorial

import numpy as np
import pandas as pd

MAX_PLAYERS = 14


def exact_shapley(values: np.ndarray, n: int) -> np.ndarray:
    """`values[mask]` is the worth of the coalition whose bits are set in `mask`."""
    if n > MAX_PLAYERS:
        raise ValueError(f"exact Shapley is limited to {MAX_PLAYERS} channels; group the rare ones first")
    if len(values) != 1 << n:
        raise ValueError("values must have one entry per coalition")
    masks = np.arange(1 << n)
    sizes = np.array([bin(m).count("1") for m in masks])
    weight = np.array([factorial(s) * factorial(n - s - 1) / factorial(n) if s < n else 0.0 for s in sizes])
    result = np.zeros(n)
    for player in range(n):
        without = masks[(masks >> player) & 1 == 0]
        result[player] = np.sum(weight[without] * (values[without | (1 << player)] - values[without]))
    return result


def path_masks(paths: list[tuple[str, ...]], channels: list[str]) -> np.ndarray:
    bit = {c: 1 << i for i, c in enumerate(channels)}
    return np.array([sum(bit[c] for c in set(path)) for path in paths], dtype=np.int64)


def subset_sums(by_mask: np.ndarray, n: int) -> np.ndarray:
    """For every coalition S, the sum of `by_mask[T]` over all T inside S."""
    out = by_mask.astype(float).copy()
    masks = np.arange(1 << n)
    for player in range(n):
        has = masks[(masks >> player) & 1 == 1]
        out[has] += out[has ^ (1 << player)]
    return out


def coalition_values(masks: np.ndarray, conversions: np.ndarray, nulls: np.ndarray, n: int, game: str) -> np.ndarray:
    conv = subset_sums(np.bincount(masks, weights=conversions, minlength=1 << n), n)
    if game == "count":
        return conv
    if game == "rate":
        seen = conv + subset_sums(np.bincount(masks, weights=nulls, minlength=1 << n), n)
        return np.divide(conv, seen, out=np.zeros_like(conv), where=seen > 0)
    raise ValueError(f"unknown game: {game}")


def shapley_raw(table: pd.DataFrame, channels: list[str], game: str) -> dict[str, float]:
    n = len(channels)
    if n > MAX_PLAYERS:
        raise ValueError(f"exact Shapley is limited to {MAX_PLAYERS} channels; group the rare ones first")
    masks = path_masks(table["path"].tolist(), channels)
    values = coalition_values(masks, table["conversions"].to_numpy(), table["nulls"].to_numpy(), n, game)
    return dict(zip(channels, exact_shapley(values, n).tolist()))


def clipped_shares(raw: dict[str, float]) -> dict[str, float]:
    """Shares of the positive part. Negative values are set to zero; callers must report that they were."""
    positive = {k: max(0.0, v) for k, v in raw.items()}
    total = sum(positive.values())
    if total <= 0:
        return {k: 0.0 for k in raw}
    return {k: v / total for k, v in positive.items()}
