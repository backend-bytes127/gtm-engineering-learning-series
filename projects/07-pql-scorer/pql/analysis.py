"""Test-set evaluation, weekly stability, cut-off sensitivity and the experiment numbers."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from pql import experiment, models, routing
from pql.config import CAPACITY_FRACTIONS, SEED, TIERS, CohortConfig
from pql.evaluate import at_capacity, bootstrap, calibration_table, probability_metrics, ranking_metrics
from pql.milestones import reached

if TYPE_CHECKING:
    from pql.pipeline import Prepared, RunConfig

CALIBRATION_QUANTILES = (0.25, 0.5, 0.75, 0.9, 0.95, 0.99, 0.998)
LIFTS = (0.10, 0.20, 0.30, 0.50)
ALLOCATIONS = (0.5, 0.9)
# ASSUMPTIONS for the break-even illustration only. The data has no prices, costs or margins.
ASSUMED_MARGIN_PER_ORDER = 20.0
ASSUMED_COST_PER_ACTION = {"A_assist": 1.50, "B_nudge": 0.05}


def sensitivity(events: pd.DataFrame, cutoffs: list[CohortConfig], config: RunConfig) -> list[dict]:
    """How the choice of cut-off changes what is left to predict. Logistic only, validation only."""
    from pql.pipeline import prepare

    rows = []
    for cohort_config in cutoffs:
        data = prepare(events, cohort_config, config.split)
        train, val = data.split["train"], data.split["validation"]
        model = models.fit_logistic(data.features.loc[train], data.labels.loc[train])
        scores = models.probabilities(model, data.features.loc[val])
        labels = data.labels.loc[val].to_numpy()
        top = at_capacity(labels, scores, config.selection_fraction)
        counts = data.cohort.counts
        remaining = counts["eligible"] + counts["excluded_bought_before_cutoff"] + counts["excluded_automation_like"]
        rows.append(
            {
                "cutoff_minutes": cohort_config.cutoff_minutes,
                "bought_before_cutoff": counts["excluded_bought_before_cutoff"],
                "later_buyers": counts["eligible_later_buyers"],
                "share_excluded_as_already_bought": counts["excluded_bought_before_cutoff"] / remaining,
                "validation_rate": float(labels.mean()),
                **ranking_metrics(labels, scores),
                "lift_at_1pct": top["lift"],
                "recall_at_1pct": top["recall"],
            }
        )
    return rows


def evaluate_test(
    data: Prepared, fitted: dict, chosen: str, calibrator: models.PlattCalibrator, policy: routing.Policy, config: RunConfig
) -> dict:
    index = data.split["test"]
    features, labels = data.features.loc[index], data.labels.loc[index].to_numpy()
    raw = {name: models.probabilities(m, features) for name, m in fitted.items()}
    calibrated = calibrator.apply(raw[chosen])
    scores = {"model": calibrated, "cart_rule": models.cart_rule(features), "points_rule": models.points_rule(features)}
    other = next(n for n in raw if n != chosen)
    scores[f"{other}_not_chosen"] = raw[other]
    intervals = bootstrap(labels, scores, "points_rule", config.selection_fraction, config.bootstrap_reps, SEED)
    table = [{"scorer": n, **ranking_metrics(labels, s), "intervals": intervals[n]} for n, s in scores.items()]
    capacity = [
        {"scorer": n, **at_capacity(labels, s, fraction)}
        for fraction in CAPACITY_FRACTIONS
        for n, s in scores.items()
    ]
    train_rate = float(data.labels.loc[data.split["train"]].mean())
    probability = {
        "constant_train_rate": probability_metrics(labels, np.full(labels.size, train_rate)),
        "model_before_calibration": probability_metrics(labels, raw[chosen]),
        "model_calibrated_on_validation": probability_metrics(labels, calibrated),
    }
    decided = data.cohort.visitors.loc[index, "cutoff_ts"].to_numpy()
    routed = {}
    for name, s, route_policy in _policies(data, calibrated, scores, policy, config):
        decisions = routing.route(s, decided, route_policy)
        routed[name] = {
            "tiers": routing.tier_summary(decisions, labels, decided, route_policy),
            "visitors_hitting_a_full_tier": int(decisions["hit_capacity"].sum()),
        }
    return {
        "ranking": table,
        "capacity": capacity,
        "probability": probability,
        "calibration": calibration_table(labels, calibrated, CALIBRATION_QUANTILES),
        "routing": routed,
        "segments": _segments(features, labels, calibrated, policy),
        "days": int((decided // 86_400_000).max() - (decided // 86_400_000).min() + 1),
    }


def _policies(data: Prepared, calibrated: np.ndarray, scores: dict, policy: routing.Policy, config: RunConfig) -> list:
    """The model policy, plus the points rule given the same capacity and thresholds set the same way."""
    val = data.split["validation"]
    rule_val = models.points_rule(data.features.loc[val])
    per_day = routing.visitors_per_day(data.cohort.visitors.loc[val, "first_ts"])
    rule_policy = routing.fit_thresholds(rule_val, per_day, TIERS, "points-rule-v1")
    floor = tuple(max(t, 1.0) for t in rule_policy.thresholds)  # zero points never earns an action
    rule_policy = routing.Policy(rule_policy.tiers, floor, rule_policy.score_version)
    return [("model", calibrated, policy), ("points_rule", scores["points_rule"], rule_policy)]


def _segments(features: pd.DataFrame, labels: np.ndarray, scores: np.ndarray, policy: routing.Policy) -> list[dict]:
    """Where the model loses: how many later buyers in each behaviour segment get any action."""
    flags = reached(features)
    acted = scores >= policy.thresholds[-1]
    masks = {
        "one event only before cut-off": ((features["views"] + features["cart_adds"]) == 1).to_numpy(),
        "2+ events, no cart": (((features["views"] + features["cart_adds"]) > 1) & ~flags["M4_added_to_cart"]).to_numpy(),
        "added to cart": flags["M4_added_to_cart"].to_numpy(),
    }
    rows = []
    for name, mask in masks.items():
        buyers = int(labels[mask].sum())
        rows.append(
            {
                "segment": name,
                "share_of_visitors": float(mask.mean()),
                "later_buyers": buyers,
                "share_of_buyers": buyers / labels.sum() if labels.sum() else 0.0,
                "buy_rate": float(labels[mask].mean()) if mask.any() else 0.0,
                "buyers_above_lowest_threshold": float((acted & mask & (labels == 1)).sum() / buyers) if buyers else 0.0,
            }
        )
    return rows


def weekly_table(data: Prepared, model: object, calibrator: models.PlattCalibrator) -> list[dict]:
    """Test-period drift, week by week."""
    index = data.split["test"]
    labels = data.labels.loc[index]
    p = pd.Series(calibrator.apply(models.probabilities(model, data.features.loc[index])), index=index)
    week = pd.to_datetime(data.cohort.visitors.loc[index, "first_ts"], unit="ms").dt.to_period("W").dt.start_time
    rows = []
    for start, members in labels.groupby(week):
        ids = members.index
        both = members.nunique() == 2
        rows.append(
            {
                "week": start.strftime("%Y-%m-%d"),
                "visitors": len(ids),
                "buyers": int(members.sum()),
                "observed_rate": float(members.mean()),
                "mean_predicted": float(p.loc[ids].mean()),
                "average_precision": ranking_metrics(members.to_numpy(), p.loc[ids].to_numpy())["average_precision"] if both else 0.0,
            }
        )
    return rows


def experiment_section(test: dict, config: RunConfig) -> dict:
    """Size the test from the observed rate and volume of each routed tier."""
    tiers = {row["tier"]: row for row in test["routing"]["model"]["tiers"]}
    both = [tiers[t.name] for t in TIERS]
    visitors = sum(r["visitors"] for r in both)
    pooled = {
        "tier": "A_and_B_pooled",
        "buy_rate": sum(r["buyers"] for r in both) / visitors if visitors else 0.0,
        "per_day": sum(r["per_day"] for r in both),
    }
    designs = []
    for row in [*both, pooled]:
        if not 0 < row["buy_rate"] < 1 or row["per_day"] <= 0:
            continue
        table = experiment.design_table(row["buy_rate"], row["per_day"], LIFTS, ALLOCATIONS, config.cohort.horizon_days)
        entry = {"tier": row["tier"], "baseline": row["buy_rate"], "per_day": row["per_day"], "rows": table}
        if row["tier"] in ASSUMED_COST_PER_ACTION:
            entry["break_even_lift"] = experiment.break_even_lift(
                ASSUMED_COST_PER_ACTION[row["tier"]], ASSUMED_MARGIN_PER_ORDER, row["buy_rate"]
            )
        designs.append(entry)
    check = None
    if designs:
        base, first = designs[-1]["baseline"], designs[-1]["rows"][1]
        check = {
            "tier": designs[-1]["tier"],
            "relative_lift": first["relative_lift"],
            "power": experiment.simulated_power(base, first["treated_rate"], first["n_treated"], first["n_control"], 20_000, SEED),
        }
    assumptions = {"margin_per_order": ASSUMED_MARGIN_PER_ORDER, "cost_per_action": ASSUMED_COST_PER_ACTION}
    return {"designs": designs, "simulation_check": check, "assumptions": assumptions}
