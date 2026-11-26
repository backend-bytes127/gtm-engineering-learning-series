import pytest

from attribution.channels import normalise_pairs
from attribution.evaluate import credit_vs_truth, random_params, score, seed_stability, summarise_sweep, world_sweep
from attribution.methods import METHODS
from attribution.scenario import run_scenario
from attribution.truth import causal_truth
from attribution.world import CHANNELS, WorldParams, closer_params, draw, null_params, simulate, untargeted_params
from attribution.world_events import emit

N, SEED = 40_000, 7


@pytest.fixture(scope="module")
def base():
    return run_scenario(WorldParams(), N, SEED)


def test_zero_lift_channels_have_zero_causal_effect(base):
    assert base.truth.table.loc[["brand_search", "direct"]].abs().to_numpy().max() == 0


def test_causal_shapley_adds_up_to_the_whole_marketing_effect(base):
    assert base.truth.table["causal_shapley"].sum() == pytest.approx(base.truth.incremental_total)
    assert 0 < base.truth.incremental_total < base.truth.conversions_all_on


def test_switching_a_channel_off_never_adds_a_buyer():
    draws = draw(5000, 1)
    full = simulate(WorldParams(), draws).converted
    for channel in CHANNELS:
        assert not (simulate(WorldParams(), draws, frozenset({channel})).converted & ~full).any()


def test_same_seed_same_world():
    a, b = run_scenario(WorldParams(), 3000, 3), run_scenario(WorldParams(), 3000, 3)
    assert a.events.equals(b.events)
    assert a.attribution.units.equals(b.attribution.units)


def test_normaliser_recovers_planted_channels_through_the_messy_urls(base):
    assert (base.events["channel"] == base.events["planted_channel"]).all()
    sample = base.events.head(200)
    assert normalise_pairs(sample["landing_url"].tolist(), sample["referrer"].tolist()) == sample["channel"].tolist()


def test_emitted_post_purchase_events_never_reach_attribution(base):
    assert base.prepared.dropped["at_or_after_end"] > 0
    assert (base.prepared.touches["ts"] < base.prepared.touches["end_ts"]).all()


def test_buyers_without_touches_are_kept_as_untracked():
    outcome = simulate(WorldParams(), draw(20_000, 2))
    _, journeys = emit(outcome, 3)
    assert journeys["converted"].sum() == outcome.converted.sum()


def test_last_touch_over_credits_the_zero_effect_channels(base):
    shares = base.attribution.shares()
    assert shares.loc[["brand_search", "direct"], "last_touch"].sum() > 0.4


def test_null_world_still_hands_out_every_conversion():
    null = run_scenario(null_params(WorldParams()), 20_000, SEED)
    assert null.truth.incremental_total == 0
    assert null.attribution.credit().sum().to_numpy() == pytest.approx([null.attribution.n_conversions] * len(METHODS))
    with pytest.raises(ValueError):
        score(null)


def test_the_ranking_of_methods_flips_between_worlds(base):
    closer = score(run_scenario(closer_params(WorldParams()), N, SEED))["share_error"]
    first_vs_decay = score(base)["share_error"]
    assert first_vs_decay["first_touch"] < first_vs_decay["time_decay"]
    assert closer["first_touch"] > closer["time_decay"]


def test_scores_are_bounded_and_include_baselines(base):
    table = score(base)
    assert table["share_error"].between(0, 1).all()
    assert {"equal_split", "touch_volume"} <= set(table.index)
    assert list(credit_vs_truth(base).index) == list(CHANNELS)


def test_untargeted_world_removes_confounding():
    outcome = simulate(untargeted_params(WorldParams()), draw(40_000, 4))
    intent = draw(40_000, 4).intent
    assert abs(intent[outcome.exposed["brand_search"]].mean() - intent.mean()) < 0.05


def test_sweep_and_stability_shapes():
    sweep = world_sweep(2, 4000, 1)
    summary = summarise_sweep(sweep)
    assert summary["lowest_error_worlds"].sum() == 2
    assert list(seed_stability(WorldParams(), 4000, [1, 2]).columns) == ["mean", "min", "max"]


def test_random_params_keep_direct_at_zero():
    import numpy as np

    assert random_params(np.random.default_rng(0)).lift["direct"] == 0


def test_world_input_guards():
    with pytest.raises(ValueError):
        draw(0, 1)
    with pytest.raises(ValueError):
        simulate(WorldParams(), draw(10, 1), frozenset({"tv"}))


def test_truth_for_a_subset_of_players():
    truth = causal_truth(WorldParams(), draw(5000, 1), players=("email", "webinar"))
    assert truth.table["causal_shapley"].sum() == pytest.approx(truth.incremental_total)
