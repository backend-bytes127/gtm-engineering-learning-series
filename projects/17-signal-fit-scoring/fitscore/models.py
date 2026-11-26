"""Candidate models and the probability calibrator."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression

from . import config
from .config import ScoringConfig
from .features import Encoder, feature_spec, fit_encoder, transform


@dataclass(frozen=True)
class ModelSpec:
    name: str
    kind: str  # "logistic" or "boosted"
    strength: float  # logistic: C. boosted: max depth.


CANDIDATES = (
    ModelSpec("logistic_C0.03", "logistic", 0.03),
    ModelSpec("logistic_C0.3", "logistic", 0.3),
    ModelSpec("logistic_C3", "logistic", 3.0),
    ModelSpec("boosted_depth2", "boosted", 2),
    ModelSpec("boosted_depth3", "boosted", 3),
)
BOOSTED_MARGIN = 0.01  # boosted trees must beat the best logistic model by this much: they give no simple reason codes


@dataclass(frozen=True)
class Fitted:
    encoder: Encoder
    estimator: object

    def predict(self, frame: pd.DataFrame, cfg: ScoringConfig) -> np.ndarray:
        return self.estimator.predict_proba(transform(frame, self.encoder, cfg))[:, 1]


def fit_model(
    train: pd.DataFrame,
    spec: ModelSpec,
    cfg: ScoringConfig,
    groups: tuple[str, ...] = config.GROUPS,
    extra_categorical: tuple[str, ...] = (),
    extra_numeric: tuple[str, ...] = (),
) -> Fitted:
    fields, numeric = feature_spec(groups, extra_categorical, extra_numeric)
    encoder = fit_encoder(train, fields, numeric, cfg)
    matrix = transform(train, encoder, cfg)
    if spec.kind == "logistic":
        estimator = LogisticRegression(C=spec.strength, max_iter=3000)
    else:
        estimator = HistGradientBoostingClassifier(
            max_depth=int(spec.strength), learning_rate=0.05, max_iter=150, min_samples_leaf=100,
            early_stopping=False, random_state=config.SEED,
        )
    return Fitted(encoder, estimator.fit(matrix, train["won"].to_numpy()))


def logit(p: np.ndarray) -> np.ndarray:
    clipped = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(clipped / (1 - clipped))


def fit_calibrator(raw: np.ndarray, outcomes: np.ndarray) -> tuple[float, float]:
    """Platt scaling on out-of-time predictions. Falls back to 'no change' if the slope would flip the ranking."""
    model = LogisticRegression(C=1e6, max_iter=3000).fit(logit(raw)[:, None], outcomes)
    slope, intercept = float(model.coef_[0, 0]), float(model.intercept_[0])
    return (slope, intercept) if slope > 0 else (1.0, 0.0)


def calibrate(raw: np.ndarray, calibrator: tuple[float, float]) -> np.ndarray:
    slope, intercept = calibrator
    return 1 / (1 + np.exp(-(slope * logit(raw) + intercept)))
