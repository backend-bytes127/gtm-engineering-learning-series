"""Ranking, tier and calibration measures. Ties are averaged, as if broken at random."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import rankdata
from sklearn.metrics import roc_auc_score


def auc(outcomes: np.ndarray, scores: np.ndarray) -> float:
    positives = outcomes.sum()
    negatives = len(outcomes) - positives
    if positives == 0 or negatives == 0:
        return float("nan")
    return float((rankdata(scores)[outcomes == 1].sum() - positives * (positives + 1) / 2) / (positives * negatives))


def pooled_auc(outcomes: np.ndarray, scores: np.ndarray) -> float:
    return float(roc_auc_score(outcomes, scores))


def group_indices(groups: np.ndarray) -> list[np.ndarray]:
    _, codes = np.unique(groups, return_inverse=True)
    return [np.flatnonzero(codes == i) for i in range(codes.max() + 1)]


def within_group_auc(outcomes: np.ndarray, scores: np.ndarray, groups: np.ndarray, indices: list | None = None) -> float:
    """AUC over (won, lost) pairs from the same month only: 'can it order one month's list?'"""
    total, weight = 0.0, 0.0
    for idx in indices or group_indices(groups):
        y = outcomes[idx]
        pairs = y.sum() * (len(y) - y.sum())
        if pairs:
            total += auc(y, scores[idx]) * pairs
            weight += pairs
    return float(total / weight) if weight else float("nan")


def band_weights(scores: np.ndarray, low: float, high: float) -> np.ndarray:
    """Share of each row that falls between positions low*n and high*n when sorted best first."""
    n = len(scores)
    _, inverse, counts = np.unique(-scores, return_inverse=True, return_counts=True)
    start = np.concatenate([[0], np.cumsum(counts)[:-1]])
    overlap = np.clip(np.minimum(start + counts, high * n) - np.maximum(start, low * n), 0, None)
    return (overlap / counts)[inverse]


def grouped_band_weights(scores: np.ndarray, groups: np.ndarray, low: float, high: float, indices: list | None = None) -> np.ndarray:
    out = np.zeros(len(scores))
    for idx in indices or group_indices(groups):
        out[idx] = band_weights(scores[idx], low, high)
    return out


def lift_at(outcomes: np.ndarray, scores: np.ndarray, groups: np.ndarray, share: float, indices: list | None = None) -> float:
    """Win rate in the top `share` of each month's list, divided by the overall win rate."""
    weights = grouped_band_weights(scores, groups, 0.0, share, indices)
    return float((weights @ outcomes / weights.sum()) / outcomes.mean())


def brier(outcomes: np.ndarray, probs: np.ndarray) -> float:
    return float(np.mean((probs - outcomes) ** 2))


def log_loss(outcomes: np.ndarray, probs: np.ndarray) -> float:
    p = np.clip(probs, 1e-6, 1 - 1e-6)
    return float(-np.mean(outcomes * np.log(p) + (1 - outcomes) * np.log(1 - p)))


def reliability(outcomes: np.ndarray, probs: np.ndarray, bins: int = 5) -> pd.DataFrame:
    """Equal-count bins by predicted probability; equal predictions never split by outcome."""
    order = np.argsort(probs, kind="stable")
    chunks = [c for c in np.array_split(order, bins) if len(c)]
    return pd.DataFrame(
        [{"rows": len(c), "mean_predicted": probs[c].mean(), "observed_rate": outcomes[c].mean()} for c in chunks]
    )
