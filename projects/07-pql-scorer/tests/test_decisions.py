import numpy as np
import pandas as pd
import pytest

from pql import evaluate, experiment, models, routing
from pql.config import DAY_MS, Tier
from pql.features import FEATURES


def _features(**columns):
    n = len(next(iter(columns.values())))
    base = {name: np.zeros(n) for name in FEATURES}
    base.update({k: np.asarray(v, dtype=float) for k, v in columns.items()})
    return pd.DataFrame(base)


def test_rules():
    features = _features(cart_adds=[0, 1, 2], cart_items=[0, 1, 2], distinct_items=[1, 2, 6], repeat_views=[0, 0, 1])
    assert list(models.cart_rule(features)) == [0, 1, 1]
    assert list(models.points_rule(features)) == [0, 16, 34]


def test_platt_corrects_inflated_probabilities_without_reordering():
    rng = np.random.default_rng(0)
    true_p = rng.uniform(0.01, 0.3, 20_000)
    labels = (rng.random(true_p.size) < true_p).astype(int)
    inflated = np.clip(true_p * 2.5, 0, 0.99)
    calibrated = models.fit_platt(inflated, labels).apply(inflated)
    assert abs(calibrated.mean() - labels.mean()) < 0.005
    assert np.array_equal(np.argsort(calibrated), np.argsort(inflated))


def test_top_k_handles_ties_without_depending_on_row_order():
    labels = np.array([1, 0, 0, 0, 1])
    scores = np.array([1.0, 1.0, 1.0, 1.0, 2.0])
    assert evaluate.top_k_hits(labels, scores, 3) == pytest.approx(1 + 2 * 0.25)
    assert evaluate.top_k_hits(labels[::-1], scores[::-1], 3) == pytest.approx(1.5)
    assert evaluate.top_k_hits(labels, scores, 0) == 0 and evaluate.top_k_hits(labels, scores, 9) == 2


def test_capacity_lift_and_calibration_bins():
    labels = np.array([1] * 10 + [0] * 90)
    scores = np.linspace(1, 0, 100)
    top = evaluate.at_capacity(labels, scores, 0.1)
    assert top["precision"] == 1.0 and top["recall"] == 1.0 and top["lift"] == pytest.approx(10)
    bins = evaluate.calibration_table(labels, scores, (0.5, 0.9))
    assert sum(b["n"] for b in bins) == 100
    assert all(b["low"] <= b["observed"] <= b["high"] + 1e-12 for b in bins)
    assert evaluate.wilson_interval(0, 0) == (0.0, 1.0)


def test_bootstrap_is_reproducible_and_paired():
    rng = np.random.default_rng(1)
    labels = (rng.random(800) < 0.1).astype(int)
    good = labels + rng.normal(0, 0.5, 800)
    scores = {"good": good, "copy": good.copy()}
    first = evaluate.bootstrap(labels, scores, "copy", 0.05, 30, seed=2)
    assert first == evaluate.bootstrap(labels, scores, "copy", 0.05, 30, seed=2)
    assert first["good"]["average_precision_minus_copy"] == (0.0, 0.0)


TIERS = (Tier("A", 1, "call"), Tier("B", 2, "nudge"))


def test_thresholds_match_capacity():
    policy = routing.fit_thresholds(np.arange(1000) / 1000, 100, (Tier("A", 10, ""), Tier("B", 20, "")), "v1")
    assert policy.thresholds == pytest.approx((0.8991, 0.6993))
    with pytest.raises(ValueError):
        routing.fit_thresholds(np.array([]), 100, TIERS, "v1")


def test_routing_decides_in_time_order_and_never_exceeds_a_daily_cap():
    policy = routing.Policy(TIERS, (0.8, 0.5), "v1")
    scores = np.array([0.95, 0.85, 0.9, 0.9, 0.99, 0.1])
    times = np.array([2, 1, 3, 4, DAY_MS + 1, 5])
    out = routing.route(scores, times, policy)
    # the 0.85 visitor arrived first and takes the only A slot, although better ones came later
    assert list(out["tier"]) == ["B", "A", "B", "C_none", "A", "C_none"]
    assert out["hit_capacity"].sum() == 3
    summary = routing.tier_summary(out, np.array([1, 0, 0, 1, 1, 0]), times, policy)
    assert sum(r["visitors"] for r in summary) == 6
    assert sum(r["share_of_buyers"] for r in summary) == pytest.approx(1)


def test_routing_rejects_a_missing_score():
    with pytest.raises(ValueError):
        routing.route(np.array([np.nan]), np.array([1]), routing.Policy(TIERS, (0.8, 0.5), "v1"))


def test_replaying_a_batch_creates_no_second_task():
    policy = routing.Policy(TIERS, (0.8, 0.5), "v1")
    decisions = pd.DataFrame({"tier": ["A", "C_none", "B"]})
    ledger = routing.TaskLedger()
    first = ledger.tasks_for(["a", "b", "c"], decisions, policy)
    assert [t["idempotency_key"] for t in first] == ["a:v1", "c:v1"]
    assert ledger.tasks_for(["a", "b", "c"], decisions, policy) == []


def test_sample_size_matches_a_textbook_value_and_simulation():
    treated, control = experiment.sample_size(0.10, 0.12)
    assert treated == control and 3830 <= control <= 3850
    power = experiment.simulated_power(0.10, 0.12, treated, control, 20_000, seed=1)
    assert power == pytest.approx(0.8, abs=0.015)


def test_unequal_allocation_needs_more_people_in_total():
    even = sum(experiment.sample_size(0.05, 0.06))
    skewed = experiment.sample_size(0.05, 0.06, treated_share=0.9)
    assert sum(skewed) > 2 * even and skewed[0] > 8 * skewed[1]


def test_design_table_adds_the_outcome_window():
    rows = experiment.design_table(0.05, 100, (0.2,), (0.5,), 7)
    assert rows[0]["days_to_readout"] == rows[0]["enrol_days"] + 7


@pytest.mark.parametrize("call", [
    lambda: experiment.sample_size(0.1, 0.1),
    lambda: experiment.sample_size(0.1, 0.2, treated_share=1),
    lambda: experiment.design_table(0.1, 0, (0.1,), (0.5,), 7),
    lambda: experiment.sample_ratio_p_value(0, 0, 0.5),
    lambda: experiment.break_even_lift(1, 0, 0.1),
])
def test_experiment_inputs_are_validated(call):
    with pytest.raises(ValueError):
        call()


def test_sample_ratio_mismatch_and_break_even():
    assert experiment.sample_ratio_p_value(5000, 5000, 0.5) == pytest.approx(1)
    assert experiment.sample_ratio_p_value(5400, 4600, 0.5) < 1e-6
    assert experiment.break_even_lift(0.05, 20, 0.025) == pytest.approx(0.1)
