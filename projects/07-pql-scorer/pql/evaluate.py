"""Ranking, calibration and capacity metrics with tie handling and bootstrap intervals."""

from __future__ import annotations

import numpy as np
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score


def top_k_hits(labels: np.ndarray, scores: np.ndarray, k: int) -> float:
    """Expected buyers in the top k when visitors with equal scores are picked at random.

    Rules produce huge ties; without this, the result would depend on row order.
    """
    if k <= 0:
        return 0.0
    if k >= labels.size:
        return float(labels.sum())
    threshold = np.partition(scores, labels.size - k)[labels.size - k]
    above = scores > threshold
    tied = scores == threshold
    return float(labels[above].sum() + (k - above.sum()) * labels[tied].mean())


def at_capacity(labels: np.ndarray, scores: np.ndarray, fraction: float) -> dict[str, float]:
    k = max(1, int(round(labels.size * fraction)))
    hits = top_k_hits(labels, scores, k)
    precision = hits / k
    base = float(labels.mean())
    return {
        "fraction": fraction,
        "contacted": k,
        "precision": precision,
        "recall": hits / labels.sum() if labels.sum() else 0.0,
        "lift": precision / base if base else 0.0,
    }


def ranking_metrics(labels: np.ndarray, scores: np.ndarray) -> dict[str, float]:
    return {"average_precision": float(average_precision_score(labels, scores)), "roc_auc": float(roc_auc_score(labels, scores))}


def probability_metrics(labels: np.ndarray, p: np.ndarray) -> dict[str, float]:
    return {
        "brier": float(brier_score_loss(labels, p)),
        "log_loss": float(log_loss(labels, p, labels=[0, 1])),
        "mean_predicted": float(p.mean()),
        "observed_rate": float(labels.mean()),
    }


def wilson_interval(successes: float, total: int, z: float = 1.96) -> tuple[float, float]:
    if total == 0:
        return (0.0, 1.0)
    p = successes / total
    denom = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    half = z * np.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return (float(max(0.0, centre - half)), float(min(1.0, centre + half)))


def calibration_table(labels: np.ndarray, p: np.ndarray, edges: tuple[float, ...]) -> list[dict[str, float]]:
    """Bins by predicted-probability quantile (`edges` are quantiles in (0, 1)), finer at the top."""
    cuts = np.unique(np.quantile(p, edges))
    bins = np.searchsorted(cuts, p, side="right")
    rows = []
    for b in np.unique(bins):
        mask = bins == b
        count, hits = int(mask.sum()), int(labels[mask].sum())
        low, high = wilson_interval(hits, count)
        rows.append({"n": count, "predicted": float(p[mask].mean()), "observed": hits / count, "low": low, "high": high})
    return rows


def bootstrap(
    labels: np.ndarray, scores: dict[str, np.ndarray], reference: str, fraction: float, reps: int, seed: int
) -> dict[str, dict[str, tuple[float, float]]]:
    """95% percentile intervals. Rows are distinct visitors, so visitors are resampled.

    The same resample is used for every scorer, so the difference from `reference` is paired.
    It does not capture day-to-day or season-to-season variation.
    """
    rng = np.random.default_rng(seed)
    metrics = ("average_precision", "precision_at_capacity")
    draws = {name: {m: np.empty(reps) for m in metrics} for name in scores}
    for r in range(reps):
        idx = rng.integers(0, labels.size, labels.size)
        y = labels[idx]
        for name, s in scores.items():
            picked = s[idx]
            draws[name]["average_precision"][r] = average_precision_score(y, picked)
            draws[name]["precision_at_capacity"][r] = at_capacity(y, picked, fraction)["precision"]
    out: dict[str, dict[str, tuple[float, float]]] = {}
    for name in scores:
        out[name] = {m: _interval(draws[name][m]) for m in metrics}
        out[name].update({f"{m}_minus_{reference}": _interval(draws[name][m] - draws[reference][m]) for m in metrics})
    return out


def _interval(values: np.ndarray) -> tuple[float, float]:
    low, high = np.quantile(values, [0.025, 0.975])
    return (float(low), float(high))
