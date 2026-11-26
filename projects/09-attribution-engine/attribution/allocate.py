"""Exact credit arithmetic.

One conversion is UNITS_PER_CONVERSION integer units. Credit is only ever split with the
largest-remainder rule, so totals add up exactly instead of "to within floating point error".
"""
from __future__ import annotations

import numpy as np

UNITS_PER_CONVERSION = 1_000_000


def allocate_by_group(weights: np.ndarray, groups: np.ndarray, units: int = UNITS_PER_CONVERSION) -> np.ndarray:
    """Split `units` inside each group in proportion to `weights`; every group sums to `units` exactly.

    Ties in the remainder go to the earlier row, so the result depends only on row order.
    """
    weights = np.asarray(weights, dtype=float)
    groups = np.asarray(groups)
    if weights.shape != groups.shape:
        raise ValueError("weights and groups must have the same length")
    if weights.size == 0:
        return np.zeros(0, dtype=np.int64)
    if not np.all(np.isfinite(weights)) or np.any(weights < 0):
        raise ValueError("weights must be finite and not negative")
    _, codes = np.unique(groups, return_inverse=True)
    totals = np.bincount(codes, weights=weights)
    if np.any(totals <= 0):
        raise ValueError("every group needs a positive total weight")
    exact = weights / totals[codes] * units
    base = np.floor(exact).astype(np.int64)
    short = units - np.bincount(codes, weights=base).astype(np.int64)
    order = np.lexsort((np.arange(weights.size), -(exact - base), codes))
    sizes = np.bincount(codes)
    starts = np.repeat(np.cumsum(sizes) - sizes, sizes)
    rank = np.arange(weights.size) - starts
    bonus = np.zeros(weights.size, dtype=np.int64)
    bonus[order] = (rank < short[codes[order]]).astype(np.int64)
    return base + bonus


def allocate_total(shares: dict[str, float], conversions: int) -> dict[str, int]:
    """Split `conversions` whole conversions, as integer units, in proportion to channel shares."""
    if conversions < 0:
        raise ValueError("conversions must not be negative")
    names = sorted(shares)
    if not names:
        if conversions:
            raise ValueError("cannot credit conversions to no channels")
        return {}
    total_units = conversions * UNITS_PER_CONVERSION
    if total_units == 0:
        return {name: 0 for name in names}
    units = allocate_by_group(np.array([shares[n] for n in names]), np.zeros(len(names)), total_units)
    return {name: int(u) for name, u in zip(names, units)}
