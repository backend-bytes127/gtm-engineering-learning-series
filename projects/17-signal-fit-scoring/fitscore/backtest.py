"""Walk forward month by month: train on the past, score the next month, never look ahead.

Assumption: every outcome of a month is known before the next month starts.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config
from .baselines import all_baselines
from .config import ScoringConfig
from .metrics import within_group_auc
from .models import BOOSTED_MARGIN, CANDIDATES, ModelSpec, calibrate, fit_calibrator, fit_model


def months_between(frame: pd.DataFrame, start: str, end: str | None = None) -> list[str]:
    periods = sorted(frame["period"].unique())
    return [p for p in periods if p >= start and (end is None or p < end)]


def walk_forward_raw(frame: pd.DataFrame, months: list[str], spec: ModelSpec, cfg: ScoringConfig, **feature_args) -> pd.Series:
    """Raw model probabilities for each row of `months`, each from a model fitted on earlier months only."""
    parts = []
    for month in months:
        train, current = frame[frame["period"] < month], frame[frame["period"] == month]
        if train["won"].nunique() < 2:
            raise ValueError(f"no usable history before {month}")
        parts.append(pd.Series(fit_model(train, spec, cfg, **feature_args).predict(current, cfg), index=current.index))
    return pd.concat(parts)


def select_model(
    frame: pd.DataFrame, cfg: ScoringConfig, validation_start: str, test_start: str, candidates: tuple[ModelSpec, ...] = CANDIDATES
) -> tuple[ModelSpec, pd.DataFrame]:
    """Choose on validation months only. Rows from `test_start` onwards are removed before anything is fitted."""
    past = frame[frame["period"] < test_start]
    months = months_between(past, validation_start)
    rows = []
    for spec in candidates:
        scores = walk_forward_raw(past, months, spec, cfg)
        held = past.loc[scores.index]
        auc = within_group_auc(held["won"].to_numpy(), scores.to_numpy(), held["period"].to_numpy())
        rows.append({"model": spec.name, "kind": spec.kind, "validation_within_month_auc": auc})
    table = pd.DataFrame(rows)
    best = table.loc[table["validation_within_month_auc"].idxmax()]
    logistic = table[table["kind"] == "logistic"]
    if best["kind"] != "logistic" and len(logistic):
        top = logistic.loc[logistic["validation_within_month_auc"].idxmax()]
        if best["validation_within_month_auc"] - top["validation_within_month_auc"] < BOOSTED_MARGIN:
            best = top
    chosen = next(s for s in candidates if s.name == best["model"])
    return chosen, table.assign(chosen=table["model"] == chosen.name)


def best_logistic(table: pd.DataFrame, candidates: tuple[ModelSpec, ...] = CANDIDATES) -> ModelSpec:
    """The explainable model that gets shipped, chosen on the same validation months."""
    logistic = {s.name: s for s in candidates if s.kind == "logistic"}
    if not logistic:
        raise ValueError("at least one logistic candidate is needed: it is the model that gets exported")
    rows = table[table["model"].isin(logistic)]
    return logistic[rows.loc[rows["validation_within_month_auc"].idxmax(), "model"]]


def explainable_columns(frame: pd.DataFrame, rows: pd.DataFrame, spec: ModelSpec, cfg: ScoringConfig,
                        validation_start: str, test_start: str) -> pd.DataFrame:
    """A new frame: `rows` plus the explainable model's monthly scores and calibrated probabilities."""
    own = run_backtest(frame, spec, cfg, validation_start, test_start).loc[rows.index]
    return rows.assign(score_logistic_monthly=own["score_model_monthly"], prob_logistic_monthly=own["prob_monthly"])


def run_backtest(
    frame: pd.DataFrame, spec: ModelSpec, cfg: ScoringConfig, validation_start: str, test_start: str
) -> pd.DataFrame:
    """One row per test row: outcome, month, scores for every method, calibrated probabilities."""
    validation = months_between(frame, validation_start, test_start)
    test_months = months_between(frame, test_start)
    walk = walk_forward_raw(frame, validation + test_months, spec, cfg)
    frozen_train = frame[frame["period"] < test_start]
    frozen_model = fit_model(frozen_train, spec, cfg)
    frozen_calibrator = fit_calibrator(walk.loc[walk.index.isin(frozen_train.index)].to_numpy(),
                                       frame.loc[walk.index[walk.index.isin(frozen_train.index)], "won"].to_numpy())
    parts = []
    for month in test_months:
        train, current = frame[frame["period"] < month], frame[frame["period"] == month]
        earlier = walk.index[walk.index.isin(train.index)]
        calibrator = fit_calibrator(walk.loc[earlier].to_numpy(), frame.loc[earlier, "won"].to_numpy())
        raw = walk.loc[current.index].to_numpy()
        frozen_raw = frozen_model.predict(current, cfg)
        columns = {f"score_{name}": values for name, values in all_baselines(train, current, cfg).items()}
        columns.update(
            score_model_monthly=raw,
            score_model_frozen=frozen_raw,
            prob_monthly=calibrate(raw, calibrator),
            prob_monthly_uncalibrated=raw,
            prob_frozen=calibrate(frozen_raw, frozen_calibrator),
            prob_trailing_rate=np.full(len(current), train[train["period"] == train["period"].max()]["won"].mean()),
            reference_cut_a=_past_cut(walk.loc[earlier], frame, cfg.tiers[0].top_share),
            reference_cut_b=_past_cut(walk.loc[earlier], frame, cfg.tiers[1].top_share),
        )
        parts.append(pd.DataFrame({"period": month, "won": current["won"], **columns}, index=current.index))
    return pd.concat(parts)


def _past_cut(scores: pd.Series, frame: pd.DataFrame, top_share: float, months: int = 3) -> float:
    """Score threshold that would have selected `top_share` of the last few already-scored months."""
    periods = frame.loc[scores.index, "period"]
    recent = periods >= sorted(periods.unique())[-months:][0]
    return float(np.quantile(scores[recent].to_numpy(), 1 - top_share))


def split_summary(
    frame: pd.DataFrame, validation_start: str = config.VALIDATION_START, test_start: str = config.TEST_START
) -> pd.DataFrame:
    names = np.where(frame["period"] < validation_start, "first training history",
                     np.where(frame["period"] < test_start, "validation (model choice)", "later test"))
    grouped = frame.assign(split=names).groupby("split", sort=False)
    return grouped.agg(
        rows=("won", "size"), first_month=("period", "min"), last_month=("period", "max"), win_rate=("won", "mean"),
        had_previous_campaign=("previous", lambda s: float((pd.to_numeric(s) > 0).mean())),
    ).reset_index()
