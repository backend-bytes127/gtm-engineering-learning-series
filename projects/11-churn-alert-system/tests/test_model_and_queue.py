from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest
from conftest import make_lines

from churnalert import backtest, experiment, features, metrics, models, queue, uncertainty
from churnalert.config import PLAN

AS_OF = date(2011, 6, 1)
EVENTS = [
    (1, "2011-04-01", 1000), (1, "2011-04-11", 2000), (1, "2011-05-02", 3000), (1, "2011-05-03", -500),
    (1, "2010-11-01", 99999),  # older than the 180-day lookback
    (2, "2011-05-20", 5000),  # one purchase day: not eligible
    (3, "2011-01-10", 4000), (3, "2011-02-10", 4000),  # silent more than 90 days: already lapsed
    (4, "2010-12-20", 800), (4, "2011-03-20", 900),
]
FUTURE = [(1, "2011-06-15", 100), (4, "2011-08-30", 100), (9, "2011-11-30", 100)]


def history(events):
    return features.prepare(make_lines(events))


def test_features_match_hand_calculation():
    frame = features.snapshot_features(history(EVENTS), AS_OF).set_index("customer_id")
    assert list(frame.index) == [1, 4]
    row = frame.loc[1]
    assert (row.recency_days, row.purchase_days_180, row.purchase_days_90, row.purchase_days_prev90) == (30, 3, 3, 0)
    assert row.median_gap_days == 15.5
    assert row.net_180 == pytest.approx(55.0)
    assert row.return_share_180 == pytest.approx(500 / 6000)
    assert row.products_90 == 1


def test_gap_evidence_uses_only_earlier_gaps():
    result = features.gap_evidence(history(EVENTS), date(2011, 4, 2), horizon=60)
    assert result == {"gaps": 3, "within_horizon": pytest.approx(1 / 3)}


def test_rows_on_or_after_the_snapshot_cannot_change_features():
    before = features.snapshot_features(history(EVENTS), AS_OF)
    poisoned = [*EVENTS, (1, "2011-06-01 00:00:00", 10**7), (1, "2011-07-01", -10**6), (4, "2011-06-02", 5)]
    pd.testing.assert_frame_equal(before, features.snapshot_features(history(poisoned), AS_OF))


def test_label_window_includes_day_zero_and_excludes_day_ninety():
    end = AS_OF + timedelta(days=90)
    hist = history([*EVENTS, (1, str(AS_OF), 1), (4, str(end), 1)])
    assert features.labels(hist, pd.Series([1, 4]), AS_OF).tolist() == [0, 1]


def test_a_return_alone_is_not_a_purchase():
    hist = history([*EVENTS, *FUTURE, (4, "2011-06-10", -100)])
    assert features.labels(hist, pd.Series([4]), AS_OF).tolist() == [1]


def test_unobserved_label_window_is_refused():
    with pytest.raises(ValueError, match="after the data ends"):
        features.labels(history(EVENTS), pd.Series([1]), AS_OF)
    assert len(features.labelled_snapshot(history([*EVENTS, *FUTURE]), AS_OF)) == 2


def test_training_labels_are_closed_at_every_origin():
    for origin in (PLAN.dev_start, PLAN.test_start, date(2011, 12, 10)):
        dates = backtest.training_dates(PLAN, origin)
        assert dates and all(d + timedelta(days=90) <= origin for d in dates)
    assert backtest.training_dates(PLAN, date(2010, 7, 1)) == []


def test_model_choice_cannot_see_the_test_period():
    assert PLAN.dev_end + timedelta(days=90) <= PLAN.test_start
    assert PLAN.test_end + timedelta(days=90) <= date(2011, 12, 10)


def test_no_training_data_is_an_error():
    with pytest.raises(ValueError, match="no training snapshot"):
        backtest.Snapshots(history(EVENTS), {}).training(PLAN, date(2010, 7, 1))


def test_top_k_splits_ties_fairly():
    weights = metrics.top_k_weights(np.array([3.0, 1.0, 1.0, 1.0]), 2)
    assert weights.tolist() == pytest.approx([1, 1 / 3, 1 / 3, 1 / 3])
    assert metrics.top_k_weights(np.array([1.0, 2.0]), 5).tolist() == [1, 1]


def test_capacity_metrics():
    result = metrics.at_capacity(np.array([1, 0, 1]), np.array([0.9, 0.8, 0.1]), np.array([10, 20, 30]), 2)
    assert result == pytest.approx({"precision": 0.5, "recall": 0.5, "value_captured": 0.25})


def test_calibration_and_cluster_bootstrap():
    table = metrics.calibration_table(np.array([0, 1, 1]), np.array([0.05, 0.95, 1.0]))
    assert table["rows"].tolist() == [1, 2]
    assert metrics.expected_calibration_error(table) == pytest.approx((0.05 + 2 * 0.025) / 3)
    customers = np.array([1, 2, 1, 2, 3])
    for index in metrics.cluster_samples(customers, 20, 0):
        counts = np.bincount(index, minlength=5)
        assert counts[0] == counts[2] and counts[1] == counts[3]


def training_frame(n: int = 600) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    frame = pd.DataFrame({name: rng.integers(1, 90, n).astype(float) for name in features.FEATURES})
    return frame.assign(churned=(rng.random(n) < frame["recency_days"] / 100).astype(int))


@pytest.mark.parametrize("name", list(models.FACTORIES))
def test_every_model_returns_probabilities(name):
    frame = training_frame()
    fitted = backtest.fit(name, frame)
    p = fitted.predict(frame)
    assert len(p) == len(frame) and ((p >= 0) & (p <= 1)).all()
    assert len(fitted.score(frame)) == len(frame)


def test_recency_rule_is_monotone_on_monotone_data_and_needs_fit():
    rule = models.FACTORIES["recency_rule"]()
    with pytest.raises(RuntimeError):
        rule.predict(training_frame())
    frame = training_frame(5000)
    fitted = rule.fit(frame)
    assert fitted.predict(frame.assign(recency_days=85.0))[0] > fitted.predict(frame.assign(recency_days=2.0))[0]


def scored_rows() -> pd.DataFrame:
    rows = []
    for week in pd.date_range("2011-06-06", periods=6, freq="7D"):
        for customer in range(1, 41):
            for name, p in (("logistic", customer / 50), ("recency_rule", 1 - customer / 50)):
                rows.append({"model": name, "as_of": week, "customer_id": customer, "churned": int(customer > 25),
                             "net_180": float(customer), "recency_days": customer * 2, "purchase_days_180": 2 + customer % 7,
                             "p": p, "score": p})
    return pd.DataFrame(rows)


def test_cooldown_rests_accounts():
    part = scored_rows().query("model == 'logistic'").reset_index(drop=True)
    picked = backtest.top_with_cooldown(part, part["score"].to_numpy(), capacity=5, cooldown=28)
    for _, group in picked.groupby("customer_id"):
        assert (group["as_of"].sort_values().diff().dropna().dt.days >= 28).all()
    assert picked.groupby("as_of").size().tolist() == [5] * 6


def test_summaries_bootstrap_and_segments():
    scored = scored_rows()
    table = backtest.summarise(scored, capacity=5).set_index("model")
    assert table.loc["logistic", "precision"] == 1 and table.loc["recency_rule", "precision"] == 0
    boot = uncertainty.bootstrap_models(scored, "logistic", "recency_rule", capacity=5, reps=20)
    difference = boot[(boot["metric"] == "auc") & (boot["who"] == "difference")].iloc[0]
    assert difference.low > 0
    assert set(uncertainty.segment_table(scored, "logistic", "recency_rule")["segment"])
    with pytest.raises(ValueError, match="same rows"):
        uncertainty.bootstrap_models(scored.iloc[1:], "logistic", "recency_rule", reps=2)


class Fixed:
    def predict(self, frame):
        return frame["p"].to_numpy()


def account(**changes) -> dict:
    base = {"recency_days": 5, "median_gap_days": 20.0, "overdue_ratio": 0.25, "return_share_180": 0.0,
            "purchase_days_90": 4, "purchase_days_prev90": 4, "net_90": 100.0, "net_prev90": 100.0,
            "purchase_days_180": 8, "net_180": 200.0, "p": 0.5}
    return {**base, **changes}


@pytest.mark.parametrize("changes,code", [
    ({"return_share_180": 0.5}, "RETURNS_UP"),
    ({"recency_days": 60, "overdue_ratio": 3.0}, "OVERDUE"),
    ({"purchase_days_90": 1}, "FEWER_ORDERS"),
    ({"net_90": 10.0}, "SPEND_DOWN"),
    ({"purchase_days_180": 2}, "THIN_HISTORY"),
    ({}, "SCORE_ONLY"),
])
def test_each_reason_has_a_playbook_action(changes, code):
    found = queue.reasons(pd.Series(account(**changes)))
    assert found[0][0] == code and code in queue.PLAYBOOK


def accounts() -> pd.DataFrame:
    return pd.DataFrame([{**account(net_180=100.0 * i), "customer_id": i} for i in range(1, 8)])


def risk_falls_with_value() -> pd.DataFrame:
    """The smallest accounts are the riskiest, so the two ranking policies disagree."""
    return accounts().assign(p=lambda f: 0.9 - 0.05 * f["customer_id"])


def test_default_queue_ranks_by_risk():
    result = queue.build_queue(risk_falls_with_value(), Fixed(), resting={1}, capacity=3)
    assert result["customer_id"].tolist() == [2, 3, 4]


def test_unknown_ranking_policy_is_rejected():
    with pytest.raises(ValueError, match="policy"):
        queue.build_queue(accounts(), Fixed(), set(), capacity=3, policy="revenue")


def test_value_policy_ranks_by_value_at_risk_and_sends_nothing():
    result = queue.build_queue(accounts(), Fixed(), resting={7}, capacity=3, policy="value")
    assert result["customer_id"].tolist() == [6, 5, 4]
    assert set(result["delivery_status"]) == {"not sent (local file only)"}
    assert "customer_id" not in queue.aggregate_queue(result).columns


def test_no_repeat_alert_within_cooldown_and_rerun_is_stable(tmp_path):
    day = date(2011, 12, 10)
    first = queue.build_queue(accounts(), Fixed(), set(), capacity=3, policy="value")
    path = queue.write_queue(first, day, tmp_path)
    original = path.read_text()
    again = queue.resting_accounts(queue.read_history(tmp_path / "alert_history.csv"), day)
    assert again == set()
    queue.write_queue(first, day, tmp_path)
    assert path.read_text() == original and len(pd.read_csv(tmp_path / "alert_history.csv")) == 3
    history_frame = queue.read_history(tmp_path / "alert_history.csv")
    resting = queue.resting_accounts(history_frame, day + timedelta(days=7))
    assert resting == {7, 6, 5}
    second = queue.build_queue(accounts(), Fixed(), resting, capacity=3, policy="value")
    assert not set(second["customer_id"]) & resting
    queue.write_queue(second, day + timedelta(days=7), tmp_path)
    assert len(pd.read_csv(tmp_path / "alert_history.csv")) == 6
    assert queue.resting_accounts(history_frame, day + timedelta(days=28)) == set()


def test_damaged_history_is_not_ignored(tmp_path):
    (tmp_path / "alert_history.csv").write_text("a,b\n1,2\n")
    with pytest.raises(ValueError, match="must have columns"):
        queue.read_history(tmp_path / "alert_history.csv")


def test_holdout_size():
    assert experiment.per_arm(0.256, 0.10) < experiment.per_arm(0.256, 0.05)
    assert experiment.per_arm(0.5, 0.1) == 388  # textbook two-proportion result for 50% vs 40%
    with pytest.raises(ValueError):
        experiment.per_arm(0.05, 0.10)
