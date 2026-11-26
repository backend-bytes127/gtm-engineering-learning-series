"""Bootstrap intervals: resample rows inside each month, so the monthly mix stays fixed."""
from __future__ import annotations

from collections.abc import Callable

import numpy as np

from .metrics import group_indices

Statistic = Callable[[np.ndarray, np.ndarray, list], np.ndarray]


def month_stratified_bootstrap(groups: np.ndarray, statistic: Statistic, reps: int, seed: int) -> np.ndarray:
    """`statistic(rows, resampled_groups, group_indices)` returns a vector. Result has shape (reps, len(vector))."""
    rng = np.random.default_rng(seed)
    indices = group_indices(groups)
    sizes = np.cumsum([0] + [len(i) for i in indices])
    positions = [np.arange(sizes[k], sizes[k + 1]) for k in range(len(indices))]
    resampled_groups = np.repeat(np.arange(len(indices)), [len(i) for i in indices])
    draws = []
    for _ in range(reps):
        rows = np.concatenate([rng.choice(i, size=len(i), replace=True) for i in indices])
        draws.append(statistic(rows, resampled_groups, positions))
    return np.vstack(draws)


def month_block_bootstrap(groups: np.ndarray, statistic: Statistic, reps: int, seed: int) -> np.ndarray:
    """Resample whole months. Wider and more honest about month-to-month change; there are only a few months."""
    rng = np.random.default_rng(seed)
    indices = group_indices(groups)
    draws = []
    for _ in range(reps):
        picked = [indices[k] for k in rng.integers(0, len(indices), size=len(indices))]
        sizes = np.cumsum([0] + [len(i) for i in picked])
        positions = [np.arange(sizes[k], sizes[k + 1]) for k in range(len(picked))]
        labels = np.repeat(np.arange(len(picked)), [len(i) for i in picked])
        draws.append(statistic(np.concatenate(picked), labels, positions))
    return np.vstack(draws)


def interval(draws: np.ndarray, level: float = 0.95) -> tuple[np.ndarray, np.ndarray]:
    tail = (1 - level) / 2 * 100
    return np.nanpercentile(draws, tail, axis=0), np.nanpercentile(draws, 100 - tail, axis=0)
