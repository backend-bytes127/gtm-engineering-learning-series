"""Metrics at the weekly capacity, calibration, and a customer-cluster bootstrap."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score


def top_k_weights(score: np.ndarray, k: int) -> np.ndarray:
    """Chance each row is in the top k when ties are broken at random. Weights sum to min(k, n)."""
    score = np.asarray(score, float)
    if k >= len(score):
        return np.ones(len(score))
    threshold = np.partition(score, len(score) - k)[len(score) - k]
    above, tied = score > threshold, score == threshold
    return above.astype(float) + tied * ((k - above.sum()) / tied.sum())


def at_capacity(y: np.ndarray, score: np.ndarray, value: np.ndarray, k: int) -> dict[str, float]:
    """Precision, recall and the share of churners' trailing revenue that sits in the top k."""
    y, value = np.asarray(y, float), np.asarray(value, float)
    chosen = top_k_weights(score, k)
    hits = float((chosen * y).sum())
    lost = float((y * value).sum())
    return {"precision": hits / chosen.sum() if len(y) else float("nan"),
            "recall": hits / y.sum() if y.sum() else float("nan"),
            "value_captured": float((chosen * y * value).sum()) / lost if lost else float("nan")}


def probability_metrics(y: np.ndarray, p: np.ndarray, score: np.ndarray) -> dict[str, float]:
    clipped = np.clip(p, 1e-6, 1 - 1e-6)
    both = len(np.unique(y)) == 2
    return {"auc": float(roc_auc_score(y, score)) if both else float("nan"),
            "brier": float(brier_score_loss(y, clipped)), "log_loss": float(log_loss(y, clipped, labels=[0, 1])),
            "mean_predicted": float(np.mean(p)), "observed": float(np.mean(y))}


def calibration_table(y: np.ndarray, p: np.ndarray, bins: int = 10) -> pd.DataFrame:
    edges = np.linspace(0, 1, bins + 1)
    which = np.clip(np.digitize(p, edges[1:-1]), 0, bins - 1)
    frame = pd.DataFrame({"bin": which, "p": p, "y": y})
    table = frame.groupby("bin").agg(rows=("y", "size"), predicted=("p", "mean"), observed=("y", "mean")).reset_index()
    return table.assign(low=edges[table["bin"]], high=edges[table["bin"] + 1])


def expected_calibration_error(table: pd.DataFrame) -> float:
    return float((table["rows"] * (table["predicted"] - table["observed"]).abs()).sum() / table["rows"].sum())


def cluster_samples(customers: np.ndarray, reps: int, seed: int) -> list[np.ndarray]:
    """Row indices for each replicate, resampling whole customers (their weekly rows are not independent)."""
    order = np.argsort(customers, kind="stable")
    _, starts = np.unique(customers[order], return_index=True)
    groups = np.split(order, starts[1:])
    rng = np.random.default_rng(seed)
    return [np.concatenate([groups[i] for i in rng.integers(0, len(groups), len(groups))]) for _ in range(reps)]
