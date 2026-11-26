"""Baselines a CS team could run in a spreadsheet, and two fitted models. All share fit(train) / predict(frame)."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import StandardScaler

from .config import SEED
from .features import FEATURES

SKEWED = ["recency_days", "purchase_days_180", "purchase_days_90", "purchase_days_prev90", "median_gap_days",
          "overdue_ratio", "net_90", "net_prev90", "net_180", "avg_day_value", "products_90"]


class Model(Protocol):
    def fit(self, train: pd.DataFrame) -> Model: ...
    def predict(self, frame: pd.DataFrame) -> np.ndarray: ...
    def score(self, frame: pd.DataFrame) -> np.ndarray: ...


class BaseRate:
    """Everyone gets the training churn rate."""
    rate = 0.0

    def fit(self, train: pd.DataFrame) -> BaseRate:
        self.rate = float(train["churned"].mean())
        return self

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        return np.full(len(frame), self.rate)

    score = predict


@dataclass
class BinnedRule:
    """Rank by one column. The probability is the smoothed training churn rate in that column's bin."""
    column: str
    edges: tuple[float, ...]
    prior_weight: float = 20.0
    rates_: np.ndarray | None = None

    def fit(self, train: pd.DataFrame) -> BinnedRule:
        prior = train["churned"].mean()
        bins = np.digitize(train[self.column], self.edges)
        churned = np.bincount(bins, weights=train["churned"], minlength=len(self.edges) + 1)
        seen = np.bincount(bins, minlength=len(self.edges) + 1)
        self.rates_ = (churned + self.prior_weight * prior) / (seen + self.prior_weight)
        return self

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        if self.rates_ is None:
            raise RuntimeError("fit first")
        return self.rates_[np.digitize(frame[self.column], self.edges)]

    def score(self, frame: pd.DataFrame) -> np.ndarray:
        return frame[self.column].to_numpy(float)


def design(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[FEATURES].astype(float).assign(**{c: np.log1p(frame[c].astype(float).clip(lower=0)) for c in SKEWED})


class Logistic:
    pipe: Pipeline

    def fit(self, train: pd.DataFrame) -> Logistic:
        self.pipe = make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=2000))
        self.pipe.fit(design(train), train["churned"])
        return self

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        return self.pipe.predict_proba(design(frame))[:, 1]

    score = predict


class Boosted:
    estimator: HistGradientBoostingClassifier

    def fit(self, train: pd.DataFrame) -> Boosted:
        self.estimator = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=150, min_samples_leaf=100,
                                                        l2_regularization=1.0, early_stopping=False, random_state=SEED)
        self.estimator.fit(design(train), train["churned"])
        return self

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        return self.estimator.predict_proba(design(frame))[:, 1]

    score = predict


FACTORIES: dict[str, Callable[[], Model]] = {
    "base_rate": BaseRate,
    "recency_rule": lambda: BinnedRule("recency_days", (8, 15, 22, 31, 46, 61, 76)),
    "overdue_rule": lambda: BinnedRule("overdue_ratio", (0.25, 0.5, 1.0, 1.5, 2.0, 3.0)),
    "logistic": Logistic,
    "boosted_trees": Boosted,
}
CANDIDATES = ("logistic", "boosted_trees")
BASELINE = "recency_rule"
