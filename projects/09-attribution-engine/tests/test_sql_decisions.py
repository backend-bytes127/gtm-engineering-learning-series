import dataclasses

import pandas as pd
import pytest
from conftest import HAND, make

from attribution.checks import leakage_effect, method_spread, normalisation_effect, sql_parity
from attribution.decisions import CORE_METHODS, causal_cost, decision_table
from attribution.heuristics import RULES, channel_units
from attribution.journeys import path_table
from attribution.markov import TransitionModel
from attribution.scenario import run_scenario
from attribution.sqllayer import connect, heuristic_credit, transition_counts
from attribution.world import WorldParams


@pytest.fixture(scope="module")
def scenario():
    return run_scenario(WorldParams(), 8000, 5)


def test_sql_matches_python_on_hand_fixture(hand):
    con = connect(*make(HAND), lookback_days=30)
    sql = heuristic_credit(con)
    python = channel_units(hand)[list(RULES)] / 1_000_000
    pd.testing.assert_frame_equal(sql, python, check_names=False, atol=1e-5, check_dtype=False)


def test_sql_applies_the_same_point_in_time_rules(hand):
    touches, journeys = make({1: (True, [(10, "a"), (10, "a"), (30, "late"), (31, "later"), (1, "old")])})
    con = connect(touches, journeys, lookback_days=25)
    assert heuristic_credit(con).index.tolist() == ["a"]


def test_sql_transitions_match_the_python_model(hand):
    sql = transition_counts(connect(*make(HAND), lookback_days=30))
    table = path_table(hand)
    channels = ["email", "search", "social"]
    counts = TransitionModel(table["path"].tolist(), channels).counts(table["conversions"].to_numpy(), table["nulls"].to_numpy())
    rows, cols = ["(start)", *channels], ["(start)", *channels, "(conversion)", "(null)"]
    for row in sql.itertuples():
        assert counts[rows.index(row.from_state), cols.index(row.to_state)] == row.n
    assert counts.sum() == sql["n"].sum()


def test_sql_lookback_guard():
    with pytest.raises(ValueError):
        connect(*make(HAND), lookback_days=0)


def test_parity_check_passes_and_fails_loudly(scenario):
    assert sql_parity(scenario, 32) < 0.05
    broken = dataclasses.replace(scenario, events=scenario.events.iloc[::2])
    with pytest.raises(RuntimeError):
        sql_parity(broken, 32)


def test_keeping_post_purchase_events_changes_last_touch(scenario):
    effect = leakage_effect(scenario)
    assert effect.loc["email", "post_purchase_events_kept"] > effect.loc["email", "point_in_time"] + 0.05


def test_normalisation_facts(scenario):
    facts = normalisation_effect(scenario.events)
    assert facts["distinct_raw_source_medium_strings"] > facts["channels_after_normalising"]
    assert facts["events_matching_planted_channel"] == 1
    assert facts["share_of_events_a_no_utm_source_means_direct_rule_would_mislabel"] > 0


def test_decision_table_verdicts_and_costs():
    credit = pd.DataFrame({m: {"email": 100.0, "display": 10.0, "brand_search": 0.0} for m in CORE_METHODS}).astype(float)
    credit.loc["display", "first_touch"] = 40.0
    table = decision_table(credit, {"email": 1000, "display": 4000, "brand_search": 500})
    assert table.loc["email", "verdict"].startswith("methods agree")
    assert table.loc["display", "verdict"].startswith("depends")
    assert table.loc["display", "spend_in_dispute_eur"] == 3000
    assert (table.loc["display", "cpa_low_eur"], table.loc["display", "cpa_high_eur"]) == (100, 400)
    assert table.loc["brand_search", "verdict"].startswith("depends")
    assert pd.isna(table.loc["brand_search", "cpa_low_eur"])


def test_decision_guards():
    credit = pd.DataFrame({m: {"email": 1.0} for m in CORE_METHODS})
    with pytest.raises(ValueError):
        decision_table(credit, {"tv": 1})
    with pytest.raises(ValueError):
        decision_table(credit, {"email": 0})


def test_causal_cost_is_undefined_for_zero_effect():
    cost = causal_cost(pd.Series({"email": 10, "brand_search": 0}), {"email": 100, "brand_search": 100})
    assert cost["email"] == 10
    assert pd.isna(cost["brand_search"])


def test_method_spread_is_a_share(scenario):
    assert 0 < method_spread(scenario.attribution.shares(), CORE_METHODS) < 1
