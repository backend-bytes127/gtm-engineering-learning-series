"""Two baselines written by hand, two fitted models, and one calibration step."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler

from pql.config import SEED

Scorer = Callable[[pd.DataFrame], np.ndarray]


def cart_rule(features: pd.DataFrame) -> np.ndarray:
    """The rule most teams would start with: did they add to cart?"""
    return (features["cart_adds"] >= 1).to_numpy(dtype=float)


def points_rule(features: pd.DataFrame) -> np.ndarray:
    """A hand-set points score in the style of the original spec. The weights were not fitted or tuned."""
    points = (
        15 * (features["cart_adds"] >= 1)
        + 10 * (features["cart_items"] >= 2)
        + 5 * (features["repeat_views"] >= 1)
        + 3 * (features["distinct_items"] >= 5)
        + 1 * (features["distinct_items"] >= 2)
    )
    return points.to_numpy(dtype=float)


def _signed_log(values: np.ndarray) -> np.ndarray:
    return np.log1p(np.clip(values, 0, None))


def fit_logistic(features: pd.DataFrame, labels: pd.Series) -> Pipeline:
    model = make_pipeline(FunctionTransformer(_signed_log), StandardScaler(), LogisticRegression(C=1.0, max_iter=2000))
    return model.fit(features.to_numpy(), labels.to_numpy())


def fit_boosting(features: pd.DataFrame, labels: pd.Series) -> HistGradientBoostingClassifier:
    model = HistGradientBoostingClassifier(
        max_depth=3, learning_rate=0.05, max_iter=200, min_samples_leaf=500, l2_regularization=1.0,
        early_stopping=False, random_state=SEED,
    )
    return model.fit(features.to_numpy(), labels.to_numpy())


FITTERS = {"logistic": fit_logistic, "boosting": fit_boosting}


def probabilities(model: object, features: pd.DataFrame) -> np.ndarray:
    return model.predict_proba(features.to_numpy())[:, 1]


def _logit(p: np.ndarray) -> np.ndarray:
    clipped = np.clip(p, 1e-7, 1 - 1e-7)
    return np.log(clipped / (1 - clipped)).reshape(-1, 1)


@dataclass(frozen=True)
class PlattCalibrator:
    """Two-parameter recalibration fitted on validation. It cannot change the ranking when the slope is positive."""

    slope: float
    intercept: float

    def apply(self, raw: np.ndarray) -> np.ndarray:
        z = self.slope * _logit(raw).ravel() + self.intercept
        return 1 / (1 + np.exp(-z))


def fit_platt(raw: np.ndarray, labels: np.ndarray) -> PlattCalibrator:
    model = LogisticRegression(C=1e6, max_iter=2000).fit(_logit(raw), labels)
    return PlattCalibrator(slope=float(model.coef_[0, 0]), intercept=float(model.intercept_[0]))
