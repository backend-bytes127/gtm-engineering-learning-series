import pandas as pd
import pytest
from conftest import make

from attribution.journeys import DAY, path_table, prepare


def test_touches_at_or_after_the_conversion_are_removed():
    prepared = prepare(*make({1: (True, [(10, "a"), (30, "email"), (31, "direct")])}))
    assert prepared.touches["channel"].tolist() == ["a"]
    assert prepared.dropped["at_or_after_end"] == 2


def test_lookback_boundary_is_inclusive_at_the_old_end():
    prepared = prepare(*make({1: (True, [(22.9, "old"), (23, "edge")])}), lookback_days=7)
    assert prepared.touches["channel"].tolist() == ["edge"]
    assert prepared.dropped["outside_lookback"] == 1


def test_exact_duplicate_events_count_once():
    prepared = prepare(*make({1: (True, [(10, "a"), (10, "a"), (10, "b")])}))
    assert prepared.touches["channel"].tolist() == ["a", "b"]
    assert prepared.dropped["duplicate"] == 1


def test_conversion_without_a_touch_is_counted_separately():
    prepared = prepare(*make({1: (True, []), 2: (True, [(1, "a")])}))
    assert (prepared.n_conversions, prepared.n_untracked_conversions) == (1, 1)


def test_order_of_input_rows_does_not_matter():
    touches, journeys = make({1: (True, [(3, "c"), (1, "a"), (2, "b")])})
    shuffled = touches.iloc[[2, 0, 1]]
    pd.testing.assert_frame_equal(prepare(touches, journeys).touches, prepare(shuffled, journeys).touches)


def test_path_table_counts(hand):
    table = path_table(hand).set_index("path")
    assert table.loc[[("social", "email", "email", "search")], "conversions"].iloc[0] == 1
    assert table["conversions"].sum() == 3
    assert table["nulls"].sum() == 2


def test_empty_path_table():
    assert path_table(prepare(*make({1: (True, [])}))).empty


@pytest.mark.parametrize(
    "change",
    [
        lambda t, j: (t.drop(columns="ts"), j),
        lambda t, j: (t.assign(channel=None), j),
        lambda t, j: (t, pd.concat([j, j])),
        lambda t, j: (t.assign(journey_id=99), j),
    ],
)
def test_bad_input_is_refused(change):
    touches, journeys = make({1: (True, [(1, "a")])})
    with pytest.raises(ValueError):
        prepare(*change(touches, journeys))


def test_lookback_must_be_positive():
    with pytest.raises(ValueError):
        prepare(*make({1: (True, [(1, "a")])}), lookback_days=0)


def test_day_constant():
    assert DAY == 86400
