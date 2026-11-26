import numpy as np
import pandas as pd
import pytest
from conftest import make

from attribution.allocate import UNITS_PER_CONVERSION
from attribution.journeys import prepare
from attribution.methods import METHODS, CreditError, attribute, check_totals, total_variation
from attribution.uncertainty import bootstrap_shares


def random_prepared(seed):
    rng = np.random.default_rng(seed)
    paths = {}
    for j in range(300):
        rows = [(float(rng.uniform(0, 29)), str(rng.choice(list("abcde")))) for _ in range(rng.integers(1, 8))]
        paths[j] = (bool(rng.random() < 0.3), rows)
    return prepare(*make(paths))


@pytest.mark.parametrize("seed", range(5))
def test_every_method_credits_exactly_the_conversions(seed):
    result = attribute(random_prepared(seed))
    assert list(result.units.columns) == METHODS
    assert set(result.units.sum()) == {result.n_conversions * UNITS_PER_CONVERSION}
    assert (result.units >= 0).all().all()
    assert result.shares().sum().to_numpy() == pytest.approx(np.ones(len(METHODS)))
    assert result.credit().sum().to_numpy() == pytest.approx(np.full(len(METHODS), result.n_conversions))


def test_check_totals_catches_one_lost_unit_and_negatives():
    with pytest.raises(CreditError):
        check_totals(pd.DataFrame({"m": [UNITS_PER_CONVERSION - 1]}), 1)
    with pytest.raises(CreditError):
        check_totals(pd.DataFrame({"m": [UNITS_PER_CONVERSION + 5, -5]}), 1)


def test_nothing_to_attribute_is_an_error():
    with pytest.raises(ValueError):
        attribute(prepare(*make({1: (False, [(1, "a")])})))


def test_total_variation_handles_missing_channels():
    assert total_variation(pd.Series({"a": 1.0}), pd.Series({"b": 1.0})) == 1.0


def test_bootstrap_intervals_bracket_the_estimate_and_are_seeded():
    prepared = random_prepared(2)
    first = bootstrap_shares(prepared, n_boot=60, seed=3)
    pd.testing.assert_frame_equal(first, bootstrap_shares(prepared, n_boot=60, seed=3))
    shares = attribute(prepared).shares()
    inside = [row.low - 0.01 <= shares.loc[row.channel, row.method] <= row.high + 0.01 for row in first.itertuples()]
    assert np.mean(inside) > 0.95
    assert set(first["method"]) == set(METHODS)


def test_bootstrap_needs_two_replicates(hand):
    with pytest.raises(ValueError):
        bootstrap_shares(hand, n_boot=1)
