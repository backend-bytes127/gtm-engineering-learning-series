from itertools import permutations

import numpy as np
import pandas as pd
import pytest

from attribution.markov import TransitionModel, conversion_probability, markov_shares, normalise, removal_effects
from attribution.shapley import clipped_shares, exact_shapley, shapley_raw


def table(rows):
    return pd.DataFrame(rows, columns=["path", "conversions", "nulls"])


# Hand worked: start->a 3 of 4, start->b 1 of 4. After a: 1 to b, 1 converts, 1 null. After b: 1 converts (a,b), 1 null (b).
PATHS = table([(("a", "b"), 1, 0), (("a",), 1, 1), (("b",), 0, 1)])


def counts():
    return TransitionModel(PATHS["path"].tolist(), ["a", "b"]).counts(PATHS["conversions"].to_numpy(), PATHS["nulls"].to_numpy())


def test_markov_hand_worked_probability_and_removal():
    # P(b converts) = 1/2. P(a converts) = 1/3 + 1/3 * 1/2 = 1/2. Start: 3/4 * 1/2 + 1/4 * 1/2 = 1/2.
    assert conversion_probability(counts()) == pytest.approx(0.5)
    effects = removal_effects(counts(), ["a", "b"])
    # without a: only start->b: 1/4 * 1/2 = 1/8, effect 0.75. without b: 3/4 * 1/3 = 1/4, effect 0.5.
    assert effects == pytest.approx({"a": 0.75, "b": 0.5})
    assert markov_shares(PATHS, ["a", "b"]) == pytest.approx({"a": 0.6, "b": 0.4})


def test_markov_with_no_conversions_gives_no_shares():
    empty = table([(("a",), 0, 3)])
    assert markov_shares(empty, ["a"]) == {"a": 0.0}
    assert normalise({"a": 0.0}) == {"a": 0.0}


def test_markov_handles_repeated_channel_loops():
    loop = table([(("a", "a", "a"), 1, 1)])
    assert markov_shares(loop, ["a"]) == {"a": 1.0}


def test_exact_shapley_matches_brute_force_over_orderings():
    rng = np.random.default_rng(1)
    values = rng.random(16)
    values[0] = 0
    brute = np.zeros(4)
    orders = list(permutations(range(4)))
    for order in orders:
        mask = 0
        for player in order:
            brute[player] += values[mask | 1 << player] - values[mask]
            mask |= 1 << player
    assert exact_shapley(values, 4) == pytest.approx(brute / len(orders))


def test_count_game_equals_equal_split_over_distinct_channels():
    paths = table([(("a", "a", "b"), 6, 0), (("c",), 2, 9), (("a", "b", "c"), 3, 1)])
    assert shapley_raw(paths, ["a", "b", "c"], "count") == pytest.approx({"a": 4.0, "b": 4.0, "c": 3.0})


def test_rate_game_can_be_negative_and_is_clipped():
    paths = table([(("good",), 8, 2), (("bad",), 1, 9)])
    raw = shapley_raw(paths, ["bad", "good"], "rate")
    # v(bad)=0.1, v(good)=0.8, v(both)=0.45 -> bad = (0.1 + (0.45-0.8))/2
    assert raw == pytest.approx({"bad": -0.125, "good": 0.575})
    assert clipped_shares(raw) == {"bad": 0.0, "good": 1.0}
    assert clipped_shares({"x": -1.0}) == {"x": 0.0}


def test_shapley_guards():
    with pytest.raises(ValueError):
        shapley_raw(PATHS, ["a", "b"], "other")
    with pytest.raises(ValueError):
        exact_shapley(np.zeros(3), 2)
    with pytest.raises(ValueError):
        exact_shapley(np.zeros(2), 15)
    with pytest.raises(ValueError):
        shapley_raw(PATHS, [str(i) for i in range(15)], "count")
