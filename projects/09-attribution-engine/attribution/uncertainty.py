"""Bootstrap intervals for channel shares, resampling journeys with replacement."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .heuristics import RULES, touch_units
from .journeys import Prepared, channel_names, path_table
from .markov import TransitionModel, normalise, removal_effects
from .shapley import clipped_shares, coalition_values, exact_shapley, path_masks


def _heuristic_samples(prepared: Prepared, channels: list[str], n_boot: int, rng: np.random.Generator) -> dict[str, np.ndarray]:
    units = touch_units(prepared)
    ids, journey = np.unique(units["journey_id"].to_numpy(), return_inverse=True)
    column = pd.Categorical(units["channel"], categories=channels).codes
    cells = journey * len(channels) + column
    size = len(ids) * len(channels)
    matrices = {m: np.bincount(cells, weights=units[m].to_numpy(), minlength=size).reshape(len(ids), -1) for m in RULES}
    out = {m: np.empty((n_boot, len(channels))) for m in RULES}
    for b in range(n_boot):
        weight = rng.poisson(1.0, len(ids)).astype(float)  # Poisson bootstrap over converting journeys
        for method, matrix in matrices.items():
            total = weight @ matrix
            out[method][b] = total / total.sum()
    return out


def _path_samples(prepared: Prepared, channels: list[str], n_boot: int, rng: np.random.Generator) -> dict[str, np.ndarray]:
    table = path_table(prepared)
    model = TransitionModel(table["path"].tolist(), channels)
    masks = path_masks(table["path"].tolist(), channels)
    cells = np.concatenate([table["conversions"].to_numpy(), table["nulls"].to_numpy()]).astype(float)
    names = ["markov", "shapley_count", "shapley_rate"]
    out = {m: np.empty((n_boot, len(channels))) for m in names}
    half = len(table)
    for b in range(n_boot):
        draw = rng.multinomial(int(cells.sum()), cells / cells.sum())
        conversions, nulls = draw[:half], draw[half:]
        shares = {"markov": normalise(removal_effects(model.counts(conversions, nulls), channels))}
        for game in ("count", "rate"):
            values = coalition_values(masks, conversions, nulls, len(channels), game)
            shares[f"shapley_{game}"] = clipped_shares(dict(zip(channels, exact_shapley(values, len(channels)))))
        for method in names:
            out[method][b] = [shares[method][c] for c in channels]
    return out


def bootstrap_shares(prepared: Prepared, n_boot: int = 200, seed: int = 11, level: float = 0.95) -> pd.DataFrame:
    """Long table: method, channel, low, high. Journeys are treated as independent units."""
    if n_boot < 2:
        raise ValueError("n_boot must be at least 2")
    channels = channel_names(prepared)
    rng = np.random.default_rng(seed)
    samples = {**_heuristic_samples(prepared, channels, n_boot, rng), **_path_samples(prepared, channels, n_boot, rng)}
    tail = (1 - level) / 2
    rows = []
    for method, matrix in samples.items():
        low, high = np.quantile(matrix, [tail, 1 - tail], axis=0)
        rows += [{"method": method, "channel": c, "low": lo, "high": hi} for c, lo, hi in zip(channels, low, high)]
    return pd.DataFrame(rows)
