"""Score each method against the planted causal truth. Only this layer is allowed to see the truth."""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd

from .methods import METHODS, total_variation
from .scenario import Scenario, run_scenario
from .world import CHANNELS, SWITCHABLE, WorldParams

BASELINES = ["equal_split", "touch_volume"]
ZERO_EFFECT = ("brand_search", "direct")
TRUE_ZERO_TOLERANCE = 1e-12


def candidate_shares(scenario: Scenario) -> pd.DataFrame:
    """Method shares plus two baselines that use no attribution logic at all."""
    shares = scenario.attribution.shares().reindex(CHANNELS, fill_value=0.0)
    volume = scenario.prepared.touches["channel"].value_counts(normalize=True)
    return shares.assign(equal_split=1 / len(CHANNELS), touch_volume=volume.reindex(CHANNELS, fill_value=0.0))


def score(scenario: Scenario) -> pd.DataFrame:
    """share_error: part of all credit sitting on the wrong channel versus the causal split (0 is perfect)."""
    shares, truth = candidate_shares(scenario), scenario.truth.share()
    if truth.sum() <= 0:
        raise ValueError("this world has no incremental conversions, so shares of the truth are undefined")
    zero = [c for c in CHANNELS if scenario.truth.table.loc[c, "causal_shapley"] <= TRUE_ZERO_TOLERANCE]
    rows = []
    for method in [*METHODS, *BASELINES]:
        values = shares[method]
        rows.append(
            {
                "method": method,
                "share_error": total_variation(values, truth),
                "rank_correlation": float(values.rank().corr(truth.rank())),
                "credit_to_zero_effect": float(values.reindex(zero).sum()),
                "top_channel": values.idxmax(),
                "top_is_right": bool(values.idxmax() == truth.idxmax()),
            }
        )
    return pd.DataFrame(rows).set_index("method")


def credit_vs_truth(scenario: Scenario) -> pd.DataFrame:
    """Attributed conversions next to the conversions each channel really caused."""
    credit = scenario.attribution.credit().reindex(CHANNELS, fill_value=0.0)
    return pd.concat([scenario.truth.table, credit], axis=1)


def seed_stability(params: WorldParams, n_users: int, seeds: list[int]) -> pd.DataFrame:
    """The same planted world with fresh users each time."""
    runs = pd.concat([score(run_scenario(params, n_users, s)).assign(seed=s) for s in seeds])
    return runs.groupby("method")["share_error"].agg(["mean", "min", "max"]).reindex([*METHODS, *BASELINES])


def random_params(rng: np.random.Generator) -> WorldParams:
    """A different business each time: other lifts (brand search may now work a little) and other targeting."""
    base = WorldParams()
    lift = {c: float(rng.uniform(0, 0.9)) for c in SWITCHABLE if c != "brand_search"}
    lift |= {"brand_search": float(rng.uniform(0, 0.3)), "direct": 0.0}
    awareness = {c: float(rng.uniform(0, 0.8)) for c in base.awareness}
    return replace(base, lift=lift, awareness=awareness, targeting=float(rng.uniform(0, 1.5)), cascade=float(rng.uniform(0.2, 1.5)))


def world_sweep(n_worlds: int, n_users: int, seed: int) -> pd.DataFrame:
    """One row per (world, method). Guards against conclusions that only hold in the hand-picked world."""
    rng = np.random.default_rng(seed)
    frames = []
    for world in range(n_worlds):
        scenario = run_scenario(random_params(rng), n_users, seed + 100 + world)
        frames.append(score(scenario).assign(world=world))
    return pd.concat(frames).reset_index()


def summarise_sweep(sweep: pd.DataFrame) -> pd.DataFrame:
    errors = sweep.pivot(index="world", columns="method", values="share_error")
    grouped = sweep.groupby("method")
    table = pd.DataFrame(
        {
            "median_error": grouped["share_error"].median(),
            "worst_error": grouped["share_error"].max(),
            "beats_equal_split": errors.lt(errors["equal_split"], axis=0).mean(),
            "lowest_error_worlds": errors.idxmin(axis=1).value_counts().reindex(errors.columns, fill_value=0),
            "names_right_top_channel": grouped["top_is_right"].mean(),
        }
    )
    return table.reindex([*METHODS, *BASELINES])
