import pytest
from conftest import make

from attribution.allocate import UNITS_PER_CONVERSION
from attribution.heuristics import channel_units, time_decay, touch_units
from attribution.journeys import prepare

U = UNITS_PER_CONVERSION


def credit(prepared, rule):
    return (channel_units(prepared)[rule] / U).to_dict()


def test_first_and_last(hand):
    assert credit(hand, "first_touch") == {"email": 0, "search": 1, "social": 2}
    assert credit(hand, "last_touch") == {"email": 1, "search": 2, "social": 0}


def test_linear_splits_by_touch_not_by_channel(hand):
    # journey 1: social .25, email .5, search .25; journey 2: search 1; journey 3: social .5, email .5
    assert credit(hand, "linear") == pytest.approx({"email": 1.0, "search": 1.25, "social": 0.75})


def test_u_shaped_for_one_two_and_many_touches():
    for length, expected in [(1, [1.0]), (2, [0.5, 0.5]), (3, [0.4, 0.2, 0.4]), (6, [0.4, 0.05, 0.05, 0.05, 0.05, 0.4])]:
        prepared = prepare(*make({1: (True, [(i + 1, f"c{i}") for i in range(length)])}))
        assert (touch_units(prepared)["u_shaped"] / U).tolist() == pytest.approx(expected, abs=1e-6)


def test_time_decay_halves_every_seven_days():
    prepared = prepare(*make({1: (True, [(16, "old"), (23, "new")])}))
    assert credit(prepared, "time_decay") == pytest.approx({"old": 1 / 3, "new": 2 / 3}, abs=1e-6)


def test_time_decay_does_not_underflow_on_very_old_touches():
    prepared = prepare(*make({1: (True, [(1, "a"), (2, "b")])}, end_day=100_000), lookback_days=100_000)
    assert sum(credit(prepared, "time_decay").values()) == 1


def test_half_life_must_be_positive(hand):
    with pytest.raises(ValueError):
        time_decay(hand.touches, 0)


def test_every_rule_sums_to_the_conversions(hand):
    assert set(channel_units(hand).sum()) == {3 * U}
