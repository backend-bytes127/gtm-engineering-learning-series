"""Simple rules a sales team could run without a model. Higher score means work first."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import ScoringConfig
from .features import history_numbers

SEGMENT_FIELDS = ("job",)
SEGMENT_PRIOR_WEIGHT = 50  # rows of the overall rate mixed into each segment rate


def no_ranking(frame: pd.DataFrame) -> np.ndarray:
    return np.zeros(len(frame))


def previous_success_first(frame: pd.DataFrame) -> np.ndarray:
    return (frame["poutcome"] == "success").to_numpy(dtype=float)


def most_recent_first(frame: pd.DataFrame, cfg: ScoringConfig) -> np.ndarray:
    return np.nan_to_num(history_numbers(frame, cfg)["recency_weight"].to_numpy())


def points_rules(frame: pd.DataFrame, cfg: ScoringConfig) -> np.ndarray:
    weights = cfg.points_rules
    score = (
        weights["previous_success"] * (frame["poutcome"] == "success")
        + weights["previous_failure"] * (frame["poutcome"] == "failure")
        + weights["recency_max"] * most_recent_first(frame, cfg)
        + frame["job"].map(weights["job"]).fillna(0)
        + frame["education"].map(weights["education"]).fillna(0)
        + weights["no_credit_default_on_file"] * (frame["default"] == "no")
    )
    return score.to_numpy(dtype=float)


def segment_rate(train: pd.DataFrame, frame: pd.DataFrame) -> np.ndarray:
    """'Which segment converted best so far?': smoothed past win rate by job."""
    overall = train["won"].mean()
    field = SEGMENT_FIELDS[0]
    stats = train.groupby(field)["won"].agg(["sum", "count"])
    rates = (stats["sum"] + SEGMENT_PRIOR_WEIGHT * overall) / (stats["count"] + SEGMENT_PRIOR_WEIGHT)
    return frame[field].map(rates).fillna(overall).to_numpy(dtype=float)


def all_baselines(train: pd.DataFrame, frame: pd.DataFrame, cfg: ScoringConfig) -> dict[str, np.ndarray]:
    return {
        "no_ranking": no_ranking(frame),
        "previous_success_first": previous_success_first(frame),
        "most_recent_first": most_recent_first(frame, cfg),
        "points_rules": points_rules(frame, cfg),
        "best_job_first": segment_rate(train, frame),
    }
