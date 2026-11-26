import numpy as np
import pytest

from attribution.holdout import analyse, assign, naive_exposed_gap, replay_holdouts, required_total, sample_ratio_p
from attribution.holdout_plan import holdout_table
from attribution.world import WorldParams


def test_assignment_is_stable_salted_and_close_to_the_requested_split():
    ids = [f"u{i}" for i in range(20_000)]
    arms = [assign(i, "test-1", 0.2) for i in ids]
    assert arms == [assign(i, "test-1", 0.2) for i in ids]
    assert arms != [assign(i, "test-2", 0.2) for i in ids]
    held = arms.count("holdout")
    assert abs(held / len(ids) - 0.2) < 0.01
    assert sample_ratio_p(len(ids) - held, held, 0.2) > 0.001


def test_sample_ratio_mismatch_is_flagged():
    assert sample_ratio_p(8000, 2300, 0.2) < 0.001


def test_required_total_matches_textbook_equal_split():
    # 10% vs 12%, 80% power, two-sided 5%: about 3,841 per arm.
    assert required_total(0.12, 0.10, 0.5) == pytest.approx(7682, abs=5)
    assert required_total(0.12, 0.10, 0.1) > required_total(0.12, 0.10, 0.5)


@pytest.mark.parametrize("args", [(0.1, 0.1, 0.5), (0.0, 0.1, 0.5), (0.2, 0.1, 1.0)])
def test_required_total_guards(args):
    with pytest.raises(ValueError):
        required_total(*args)


def test_analyse_hand_worked():
    result = analyse(120, 1000, 100, 1000)
    assert result.difference == pytest.approx(0.02)
    half = 1.959964 * ((0.12 * 0.88 + 0.1 * 0.9) / 1000) ** 0.5
    assert (result.low, result.high) == pytest.approx((0.02 - half, 0.02 + half))


@pytest.mark.parametrize("args", [(1, 0, 1, 10), (11, 10, 1, 10), (1, 10, -1, 10)])
def test_analyse_guards(args):
    with pytest.raises(ValueError):
        analyse(*args)


def test_other_guards():
    with pytest.raises(ValueError):
        assign("", "s", 0.2)
    with pytest.raises(ValueError):
        sample_ratio_p(0, 0, 0.5)
    with pytest.raises(ValueError):
        replay_holdouts(np.zeros(3), np.zeros(2), 0.2, 10, 1)
    with pytest.raises(ValueError):
        naive_exposed_gap(np.ones(3, dtype=bool), np.ones(3))


def test_replay_of_a_null_effect_has_nominal_coverage():
    outcome = np.random.default_rng(0).random(20_000) < 0.1
    replay = replay_holdouts(outcome, outcome, 0.2, 400, 1)
    assert replay.true_difference == 0
    assert 0.90 < replay.coverage <= 0.99
    assert replay.detected < 0.10


def test_planted_world_naive_gap_is_large_where_truth_is_zero():
    table = holdout_table(WorldParams(), 40_000, 7, reps=100)
    assert table.loc["brand_search", "true_effect_pp"] == 0
    assert table.loc["brand_search", "naive_exposed_gap_pp"] > 3
    assert np.isnan(table["users_needed_80pct_power"].astype(float)["brand_search"])
    assert table["interval_coverage"].min() > 0.85
