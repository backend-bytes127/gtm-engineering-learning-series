"""Paired customer bootstrap of model-minus-baseline differences on the test weeks."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from .config import BOOTSTRAP_REPS, CAPACITY, SEED
from .metrics import at_capacity, cluster_samples

METRICS = ("auc", "brier", "precision", "ev_value_captured")


def _measure(week: np.ndarray, y: np.ndarray, p: np.ndarray, score: np.ndarray, value: np.ndarray,
             capacity: int) -> np.ndarray:
    precision, captured = [], []
    for w in np.unique(week):
        m = week == w
        precision.append(at_capacity(y[m], score[m], value[m], capacity)["precision"])
        captured.append(at_capacity(y[m], p[m] * value[m], value[m], capacity)["value_captured"])
    return np.array([roc_auc_score(y, score), np.mean((p - y) ** 2), np.mean(precision), np.nanmean(captured)])


def bootstrap_models(scored: pd.DataFrame, model: str, baseline: str, capacity: int = CAPACITY,
                     reps: int = BOOTSTRAP_REPS, seed: int = SEED) -> pd.DataFrame:
    """95% intervals for each model and for the paired difference. Whole customers are resampled."""
    keys = ["as_of", "customer_id"]
    a = scored[scored["model"] == model].sort_values(keys).reset_index(drop=True)
    b = scored[scored["model"] == baseline].sort_values(keys).reset_index(drop=True)
    if not a[keys].equals(b[keys]):
        raise ValueError("model and baseline were not scored on the same rows")
    week = a["as_of"].to_numpy()
    y, value = a["churned"].to_numpy(), a["net_180"].to_numpy()
    columns = [(f["p"].to_numpy(), f["score"].to_numpy()) for f in (a, b)]

    def both(index: np.ndarray | slice) -> np.ndarray:
        return np.array([_measure(week[index], y[index], p[index], s[index], value[index], capacity) for p, s in columns])

    point = both(slice(None))
    draws = np.array([both(i) for i in cluster_samples(a["customer_id"].to_numpy(), reps, seed)])
    rows = []
    for j, metric in enumerate(METRICS):
        for label, estimate, sample in ((model, point[0, j], draws[:, 0, j]), (baseline, point[1, j], draws[:, 1, j]),
                                        ("difference", point[0, j] - point[1, j], draws[:, 0, j] - draws[:, 1, j])):
            low, high = np.percentile(sample, [2.5, 97.5])
            rows.append({"metric": metric, "who": label, "estimate": estimate, "low": low, "high": high})
    return pd.DataFrame(rows)


def segment_table(scored: pd.DataFrame, model: str, baseline: str) -> pd.DataFrame:
    """Where does the model help or lose? AUC and calibration gap by account segment on the test rows."""
    keys = ["as_of", "customer_id"]
    a = scored[scored["model"] == model].sort_values(keys).reset_index(drop=True)
    b = scored[scored["model"] == baseline].sort_values(keys).reset_index(drop=True)
    value_cut = a["net_180"].quantile(0.8)
    segments = {
        "bought in last 30 days": a["recency_days"] <= 30,
        "silent 31-90 days": a["recency_days"] > 30,
        "2 purchase days in 180": a["purchase_days_180"] == 2,
        "3-5 purchase days": a["purchase_days_180"].between(3, 5),
        "6+ purchase days": a["purchase_days_180"] >= 6,
        "top 20% trailing revenue": a["net_180"] >= value_cut,
        "other 80%": a["net_180"] < value_cut,
    }
    rows = []
    for name, mask in segments.items():
        y = a.loc[mask, "churned"]
        if y.nunique() < 2:
            continue
        rows.append({"segment": name, "rows": int(mask.sum()), "churn_rate": float(y.mean()),
                     "mean_predicted": float(a.loc[mask, "p"].mean()),
                     "auc_model": float(roc_auc_score(y, a.loc[mask, "score"])),
                     "auc_baseline": float(roc_auc_score(y, b.loc[mask, "score"]))})
    return pd.DataFrame(rows)
