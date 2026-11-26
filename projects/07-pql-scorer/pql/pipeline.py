"""Event table in, aggregate results out. Order matters: every choice is made before the test split is scored."""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from pql import models, routing, tracking_plan
from pql.analysis import evaluate_test, experiment_section, sensitivity, weekly_table
from pql.cohort import Cohort, build_cohort, buyer_timing, funnel_population, time_split
from pql.config import SENSITIVITY_CUTOFFS_MINUTES, TIERS, CohortConfig, SplitConfig
from pql.evaluate import at_capacity, bootstrap, ranking_metrics
from pql.features import build_features
from pql.leakage import whole_history_features, window_leak_test
from pql.milestones import funnel, milestone_table


@dataclass(frozen=True)
class RunConfig:
    cohort: CohortConfig = CohortConfig()
    split: SplitConfig = SplitConfig()
    bootstrap_reps: int = 300
    selection_fraction: float = 0.01


@dataclass(frozen=True)
class Prepared:
    cohort: Cohort
    features: pd.DataFrame
    labels: pd.Series
    split: dict[str, pd.Index]


def prepare(events: pd.DataFrame, cohort_config: CohortConfig, split_config: SplitConfig) -> Prepared:
    cohort = build_cohort(events, cohort_config)
    features = build_features(cohort.window, cohort.visitors, cohort_config)
    labels = cohort.visitors["label"]
    split = time_split(cohort.visitors, split_config.validation_start, split_config.test_start, cohort_config)
    for name, index in split.items():
        if len(index) == 0 or labels.loc[index].nunique() < 2:
            raise ValueError(f"the {name} split needs both buyers and non-buyers; it has {len(index)} visitors")
    return Prepared(cohort, features, labels, split)


def fit_candidates(data: Prepared) -> dict[str, object]:
    train = data.split["train"]
    return {name: fit(data.features.loc[train], data.labels.loc[train]) for name, fit in models.FITTERS.items()}


def select_model(data: Prepared, fitted: dict[str, object], config: RunConfig) -> dict:
    """Prefer logistic regression unless boosting beats it on validation with a paired 95% interval above zero."""
    index = data.split["validation"]
    labels = data.labels.loc[index].to_numpy()
    scores = {name: models.probabilities(m, data.features.loc[index]) for name, m in fitted.items()}
    scores["cart_rule"] = models.cart_rule(data.features.loc[index])
    scores["points_rule"] = models.points_rule(data.features.loc[index])
    intervals = bootstrap(labels, scores, "logistic", config.selection_fraction, config.bootstrap_reps, seed=1)
    low, _ = intervals["boosting"]["average_precision_minus_logistic"]
    table = [
        {"scorer": n, **ranking_metrics(labels, s), "precision_at_capacity": at_capacity(labels, s, config.selection_fraction)["precision"]}
        for n, s in scores.items()
    ]
    return {
        "chosen": "boosting" if low > 0 else "logistic",
        "validation_table": table,
        "boosting_minus_logistic_ap_interval": intervals["boosting"]["average_precision_minus_logistic"],
    }


def run(events: pd.DataFrame, config: RunConfig | None = None) -> dict:
    config = config or RunConfig()
    checked = tracking_plan.validate(events)
    clean = checked.clean
    data = prepare(clean, config.cohort, config.split)
    fitted = fit_candidates(data)
    selection = select_model(data, fitted, config)
    chosen = fitted[selection["chosen"]]

    validation = data.split["validation"]
    raw_val = models.probabilities(chosen, data.features.loc[validation])
    calibrator = models.fit_platt(raw_val, data.labels.loc[validation].to_numpy())
    per_day = routing.visitors_per_day(data.cohort.visitors.loc[validation, "first_ts"])
    version = f"{selection['chosen']}-t{config.cohort.cutoff_minutes}m-v1"
    policy = routing.fit_thresholds(calibrator.apply(raw_val), per_day, TIERS, version)

    leak = window_leak_test(
        data.features, whole_history_features(clean, data.cohort, config.cohort), data.labels, data.split
    )
    cutoffs = [replace(config.cohort, cutoff_minutes=m) for m in SENSITIVITY_CUTOFFS_MINUTES]

    test = evaluate_test(data, fitted, selection["chosen"], calibrator, policy, config)
    train_ids = data.split["train"]
    newcomers = funnel_population(clean, config.split.validation_start, config.cohort)
    return {
        "tracking": {"rows_in": checked.rows_in, "rows_clean": len(clean), "violations": checked.violations},
        "cohort": data.cohort.counts,
        "buyer_timing": buyer_timing(clean, (5, 10, 30, 60, 1440, 10080), config.cohort),
        "splits": {
            n: {"visitors": len(i), "buyers": int(data.labels.loc[i].sum()), "rate": float(data.labels.loc[i].mean())}
            for n, i in data.split.items()
        },
        "sensitivity": sensitivity(clean, cutoffs, config),
        "milestones": milestone_table(data.features.loc[train_ids], data.labels.loc[train_ids]),
        "funnel": funnel(clean, newcomers.index, newcomers, config.cohort.horizon_ms),
        "selection": selection,
        "leak_window": leak,
        "calibrator": {"slope": calibrator.slope, "intercept": calibrator.intercept},
        "policy": {"version": policy.score_version, "thresholds": list(policy.thresholds), "validation_per_day": per_day},
        "test": test,
        "weekly": weekly_table(data, chosen, calibrator),
        "experiment": experiment_section(test, config),
        "importance": _importance(chosen, data),
    }


def _importance(model: object, data: Prepared) -> list[dict]:
    """Permutation importance on validation: drop in average precision when one feature is shuffled."""
    index = data.split["validation"]
    features, labels = data.features.loc[index], data.labels.loc[index].to_numpy()
    base = ranking_metrics(labels, models.probabilities(model, features))["average_precision"]
    rng = np.random.default_rng(11)
    rows = []
    for name in features.columns:
        shuffled = features.assign(**{name: rng.permutation(features[name].to_numpy())})
        drop = base - ranking_metrics(labels, models.probabilities(model, shuffled))["average_precision"]
        rows.append({"feature": name, "ap_drop": float(drop)})
    return sorted(rows, key=lambda r: r["ap_drop"], reverse=True)
