from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from fitscore import baselines, verdict
from fitscore.backtest import best_logistic, run_backtest, select_model, walk_forward_raw
from fitscore.bootstrap import interval, month_block_bootstrap, month_stratified_bootstrap
from fitscore.metrics import auc, band_weights, brier, lift_at, log_loss, reliability, within_group_auc
from fitscore.models import ModelSpec, calibrate, fit_calibrator, fit_model
from fitscore.segments import history_segment, segment_table
from fitscore.verdict import RULES, equal_month_summary, verdict_table

LOGIT = ModelSpec("logistic_C0.3", "logistic", 0.3)


def test_auc_by_hand_with_ties() -> None:
    # pairs: (0.9 v 0.5)=1, (0.9 v 0.1)=1, (0.5 v 0.5)=0.5, (0.5 v 0.1)=1 -> 3.5 / 4
    assert auc(np.array([1, 1, 0, 0]), np.array([0.9, 0.5, 0.5, 0.1])) == pytest.approx(0.875)
    assert np.isnan(auc(np.array([1, 1]), np.array([1.0, 2.0])))


def test_within_group_auc_ignores_between_month_differences() -> None:
    y = np.array([1, 0, 1, 0])
    scores = np.array([2.0, 1.0, 20.0, 30.0])
    assert within_group_auc(y, scores, np.array(["a", "a", "b", "b"])) == 0.5


def test_tied_rows_share_the_cut_equally() -> None:
    weights = band_weights(np.array([5.0, 1.0, 1.0, 1.0]), 0.0, 0.5)
    assert weights.tolist() == pytest.approx([1.0, 1 / 3, 1 / 3, 1 / 3])
    assert band_weights(np.zeros(10), 0.0, 0.3).tolist() == pytest.approx([0.3] * 10)


def test_bands_cover_every_row_once() -> None:
    scores = np.array([3.0, 3.0, 2.0, 1.0, 1.0, 1.0, 0.0])
    total = sum(band_weights(scores, a, b) for a, b in ((0, 0.1), (0.1, 0.3), (0.3, 1.0)))
    assert total.tolist() == pytest.approx([1.0] * 7)


def test_no_ranking_has_lift_one() -> None:
    y = np.array([1, 0, 0, 1, 0, 0])
    assert lift_at(y, np.zeros(6), np.array(["a"] * 6), 0.3) == pytest.approx(1.0)


def test_probability_scores() -> None:
    y, p = np.array([1, 0]), np.array([0.8, 0.2])
    assert brier(y, p) == pytest.approx(0.04)
    assert log_loss(y, p) == pytest.approx(-np.log(0.8))
    assert reliability(y, p, bins=2)["observed_rate"].tolist() == [0.0, 1.0]


def test_bootstraps_are_seeded_and_bracket_the_mean() -> None:
    groups = np.array(["a"] * 50 + ["b"] * 50)
    values = np.arange(100.0)
    for sampler in (month_stratified_bootstrap, month_block_bootstrap):
        first = sampler(groups, lambda rows, g, i: np.array([values[rows].mean()]), 200, 1)
        again = sampler(groups, lambda rows, g, i: np.array([values[rows].mean()]), 200, 1)
        assert np.array_equal(first, again)
        low, high = interval(first)
        assert low[0] <= 49.5 <= high[0]


def test_calibrator_never_reverses_ranking() -> None:
    raw = np.linspace(0.05, 0.95, 40)
    assert fit_calibrator(raw, (raw < 0.5).astype(int)) == (1.0, 0.0)
    fitted = fit_calibrator(raw, (raw > 0.5).astype(int))
    assert np.all(np.diff(calibrate(raw, fitted)) >= 0)


def test_future_rows_cannot_change_an_earlier_score(frame, cfg) -> None:
    months = ["2008-07", "2008-08"]
    original = walk_forward_raw(frame, months, LOGIT, cfg)
    poisoned = frame.copy()
    later = poisoned["period"] > "2008-08"
    poisoned.loc[later, "won"] = 1 - poisoned.loc[later, "won"]
    poisoned.loc[later, "job"] = "retired"
    pd.testing.assert_series_equal(original, walk_forward_raw(poisoned, months, LOGIT, cfg))


def test_a_months_own_outcomes_cannot_change_its_scores(frame, cfg) -> None:
    flipped = frame.assign(won=np.where(frame["period"] == "2008-08", 1 - frame["won"], frame["won"]))
    pd.testing.assert_series_equal(
        walk_forward_raw(frame, ["2008-08"], LOGIT, cfg), walk_forward_raw(flipped, ["2008-08"], LOGIT, cfg)
    )


def test_model_choice_never_sees_the_later_period(frame, cfg) -> None:
    candidates = (LOGIT, ModelSpec("boosted_depth2", "boosted", 2))
    _, table = select_model(frame, cfg, "2008-07", "2008-09", candidates)
    flipped = frame.assign(won=np.where(frame["period"] >= "2008-09", 1 - frame["won"], frame["won"]))
    _, again = select_model(flipped, cfg, "2008-07", "2008-09", candidates)
    pd.testing.assert_frame_equal(table, again)


def test_boosted_needs_a_clear_margin(frame, cfg, monkeypatch) -> None:
    from fitscore import backtest

    values = iter([0.600, 0.605])
    monkeypatch.setattr(backtest, "within_group_auc", lambda *a, **k: next(values))
    chosen, _ = backtest.select_model(frame, cfg, "2008-07", "2008-09", (LOGIT, ModelSpec("b", "boosted", 2)))
    assert chosen == LOGIT


def test_backtest_covers_exactly_the_later_months(frame, cfg) -> None:
    rows = run_backtest(frame, LOGIT, cfg, "2008-07", "2008-09")
    assert sorted(rows["period"].unique()) == ["2008-09", "2008-10"]
    assert rows[["prob_monthly", "prob_frozen"]].apply(lambda s: s.between(0, 1)).all().all()
    previous = frame[frame["period"] == "2008-08"]["won"].mean()
    assert rows.loc[rows["period"] == "2008-09", "prob_trailing_rate"].iloc[0] == pytest.approx(previous)


def test_walk_forward_needs_history(frame, cfg) -> None:
    with pytest.raises(ValueError, match="history"):
        walk_forward_raw(frame.assign(won=0), ["2008-07"], LOGIT, cfg)


def test_model_learns_the_planted_pattern(frame, cfg) -> None:
    scores = fit_model(frame, LOGIT, cfg).predict(frame, cfg)
    assert auc(frame["won"].to_numpy(), scores) > 0.6


def test_baselines_order_as_described(frame, cfg) -> None:
    rows = pd.DataFrame({
        "poutcome": ["nonexistent", "success", "success"], "pdays": [999, 12, 2], "previous": [0, 1, 1],
        "job": ["admin.", "admin.", "admin."], "education": ["unknown"] * 3, "default": ["no"] * 3,
    })
    for name, scores in baselines.all_baselines(frame, rows, cfg).items():
        assert len(scores) == 3, name
    recent = baselines.most_recent_first(rows, cfg)
    assert recent[2] > recent[1] > recent[0] == 0
    assert np.argmax(baselines.points_rules(rows, cfg)) == 2
    assert baselines.segment_rate(frame, rows.assign(job="unseen"))[0] == pytest.approx(frame["won"].mean())


def test_segments_by_hand(frame) -> None:
    rows = pd.DataFrame({"poutcome": ["success", "success", "failure", "nonexistent"], "pdays": [7, 999, 999, 999]})
    assert history_segment(rows).tolist() == [
        "earlier success, dated within 7 days", "earlier success, older or undated", "earlier attempt failed", "no earlier campaign"
    ]
    table = segment_table(frame, "2008-09")
    assert table["past_rows"].sum() + table["later_rows"].sum() == len(frame)


def test_verdict_needs_an_interval_that_excludes_zero() -> None:
    def differences(low: float, high: float) -> pd.DataFrame:
        return pd.DataFrame([{"compared_with": r, "measure": m, "difference": 0.01, "low": low, "high": high}
                             for r in RULES for m in ("within_month_auc", "lift_top10", "lift_top30")])

    out = verdict_table(differences(0.001, 0.02), differences(-0.01, 0.02))
    assert set(out["rows resampled"]) == {"model ahead"}
    assert set(out["whole months resampled"]) == {"no clear difference"}
    assert set(verdict_table(differences(-0.2, -0.1), differences(-0.2, -0.1))["rows resampled"]) == {"rule ahead"}


def test_best_logistic_is_the_shipped_model(frame, cfg) -> None:
    candidates = (LOGIT, ModelSpec("boosted_depth2", "boosted", 2))
    table = pd.DataFrame({"model": [c.name for c in candidates], "validation_within_month_auc": [0.5, 0.9]})
    assert best_logistic(table, candidates) == LOGIT
    with pytest.raises(ValueError, match="logistic"):
        best_logistic(table, candidates[1:])


def test_equal_month_summary_by_hand() -> None:
    columns = {f"score_{m}": [1.0, 0.0, 0.0, 1.0] for m in ("model_monthly", "logistic_monthly", *RULES)}
    rows = pd.DataFrame({"period": ["a", "a", "b", "b"], "won": [1, 0, 1, 0], **columns})
    summary, weight = equal_month_summary(rows.assign(score_points_rules=0.0))
    by_method = summary.set_index("method")
    assert by_method.loc["model_monthly", "mean_of_monthly_auc"] == 0.5
    assert by_method.loc["points_rules", "months_chosen_model_ahead"] == 1
    assert weight == 0.5


def test_chosen_model_is_not_counted_against_itself() -> None:
    rows = pd.DataFrame({"period": ["a"] * 4 + ["b"] * 4, "won": [1, 0, 1, 0] * 2})
    for method in ("model_monthly", "logistic_monthly", *verdict.RULES):
        rows[f"score_{method}"] = [4.0, 3.0, 2.0, 1.0] * 2
    summary, _ = verdict.equal_month_summary(rows)
    ahead = summary.set_index("method")["months_chosen_model_ahead"]
    assert ahead["model_monthly"] == "n/a"
    assert ahead["points_rules"] == 0
