import numpy as np
import pytest

from attribution.allocate import UNITS_PER_CONVERSION, allocate_by_group, allocate_total


def test_thirds_still_sum_to_one_conversion():
    units = allocate_by_group(np.ones(3), np.zeros(3))
    assert units.tolist() == [333_334, 333_333, 333_333]


def test_random_groups_always_sum_exactly():
    rng = np.random.default_rng(0)
    groups = rng.integers(0, 500, 4000)
    units = allocate_by_group(rng.random(4000) + 1e-9, groups)
    totals = np.bincount(groups, weights=units)
    assert set(totals[np.unique(groups)]) == {UNITS_PER_CONVERSION}
    assert units.min() >= 0


def test_zero_weight_rows_get_nothing():
    assert allocate_by_group(np.array([0.0, 1.0, 0.0]), np.zeros(3)).tolist() == [0, UNITS_PER_CONVERSION, 0]


def test_empty_input():
    assert allocate_by_group(np.array([]), np.array([])).size == 0


@pytest.mark.parametrize("weights", [[-1.0, 2.0], [np.nan, 1.0], [0.0, 0.0]])
def test_bad_weights_are_refused(weights):
    with pytest.raises(ValueError):
        allocate_by_group(np.array(weights), np.zeros(2))


def test_length_mismatch_is_refused():
    with pytest.raises(ValueError):
        allocate_by_group(np.ones(2), np.zeros(3))


def test_total_allocation_is_exact():
    units = allocate_total({"a": 1 / 3, "b": 1 / 3, "c": 1 / 3}, 100)
    assert sum(units.values()) == 100 * UNITS_PER_CONVERSION


def test_total_allocation_edges():
    assert allocate_total({"a": 1.0}, 0) == {"a": 0}
    assert allocate_total({}, 0) == {}
    with pytest.raises(ValueError):
        allocate_total({}, 1)
    with pytest.raises(ValueError):
        allocate_total({"a": 1.0}, -1)
