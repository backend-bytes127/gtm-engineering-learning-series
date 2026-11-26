"""First-order Markov chain attribution by removal effect."""
from __future__ import annotations

import numpy as np
import pandas as pd


class TransitionModel:
    """Pre-indexes the transitions in each unique path so that bootstrap replicates are cheap."""

    def __init__(self, paths: list[tuple[str, ...]], channels: list[str]):
        self.channels = list(channels)
        index = {c: i + 1 for i, c in enumerate(self.channels)}  # 0 is the start state
        self.n_states = len(self.channels) + 1
        self.conv_col, self.null_col = self.n_states, self.n_states + 1
        rows: list[int] = []
        cells: list[int] = []
        last: list[int] = []
        width = self.n_states + 2
        for row, path in enumerate(paths):
            state = 0
            for channel in path:
                rows.append(row)
                cells.append(state * width + index[channel])
                state = index[channel]
            last.append(state)
        self.width = width
        self.rows = np.array(rows, dtype=np.int64)
        self.cells = np.array(cells, dtype=np.int64)
        self.last = np.array(last, dtype=np.int64)

    def counts(self, conversions: np.ndarray, nulls: np.ndarray) -> np.ndarray:
        size = self.n_states * self.width
        totals = (conversions + nulls).astype(float)
        flat = np.bincount(self.cells, weights=totals[self.rows], minlength=size)
        flat = flat + np.bincount(self.last * self.width + self.conv_col, weights=conversions.astype(float), minlength=size)
        flat = flat + np.bincount(self.last * self.width + self.null_col, weights=nulls.astype(float), minlength=size)
        return flat.reshape(self.n_states, self.width)


def conversion_probability(counts: np.ndarray, removed: int | None = None) -> float:
    """P(reach conversion from start). A removed state sends everything that enters it to 'no conversion'."""
    n = counts.shape[0]
    outgoing = counts.sum(axis=1, keepdims=True)
    matrix = np.divide(counts, outgoing, out=np.zeros_like(counts), where=outgoing > 0)
    q = matrix[:, :n].copy()
    r = matrix[:, n].copy()
    if removed is not None:
        q[removed, :] = 0.0
        r[removed] = 0.0
    return float(np.linalg.solve(np.eye(n) - q, r)[0])


def removal_effects(counts: np.ndarray, channels: list[str]) -> dict[str, float]:
    base = conversion_probability(counts)
    if base <= 0:
        return {c: 0.0 for c in channels}
    return {c: max(0.0, 1 - conversion_probability(counts, i + 1) / base) for i, c in enumerate(channels)}


def markov_shares(table: pd.DataFrame, channels: list[str]) -> dict[str, float]:
    """Removal effects rescaled to sum to one. The rescaling is a convention, not a measurement."""
    model = TransitionModel(table["path"].tolist(), channels)
    counts = model.counts(table["conversions"].to_numpy(), table["nulls"].to_numpy())
    return normalise(removal_effects(counts, channels))


def normalise(values: dict[str, float]) -> dict[str, float]:
    total = sum(values.values())
    if total <= 0:
        return {k: 0.0 for k in values}
    return {k: v / total for k, v in values.items()}
