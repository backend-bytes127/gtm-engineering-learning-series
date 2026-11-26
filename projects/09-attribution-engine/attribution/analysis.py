"""Everything the synthetic report needs, computed once."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .checks import leakage_effect, normalisation_effect, sql_parity
from .decisions import causal_cost, decision_table
from .evaluate import credit_vs_truth, score, seed_stability, summarise_sweep, world_sweep
from .holdout_plan import holdout_table
from .scenario import LOOKBACK_DAYS, Scenario, run_scenario
from .uncertainty import bootstrap_shares
from .world import WorldParams, closer_params, null_params, untargeted_params


@dataclass(frozen=True)
class Settings:
    users: int = 200_000
    seed: int = 7
    boot: int = 200
    stability_seeds: int = 10
    sweep_worlds: int = 40
    sweep_users: int = 60_000
    holdout_reps: int = 500


@dataclass(frozen=True)
class Results:
    settings: Settings
    worlds: dict[str, Scenario]  # base, untargeted, closer
    null: Scenario
    scores: dict[str, pd.DataFrame]
    credit: pd.DataFrame
    intervals: pd.DataFrame
    stability: pd.DataFrame
    sweep: pd.DataFrame
    holdout: pd.DataFrame
    decisions: pd.DataFrame
    true_cost: pd.Series
    leakage: pd.DataFrame
    normalisation: dict[str, float]
    sql_gap: float


def analyse_world(settings: Settings) -> Results:
    base = WorldParams()
    variants = {"base": base, "untargeted": untargeted_params(base), "closer": closer_params(base)}
    worlds = {name: run_scenario(p, settings.users, settings.seed) for name, p in variants.items()}
    main = worlds["base"]
    seeds = [settings.seed + 1000 + i for i in range(settings.stability_seeds)]
    return Results(
        settings=settings,
        worlds=worlds,
        null=run_scenario(null_params(base), settings.users, settings.seed),
        scores={name: score(s) for name, s in worlds.items()},
        credit=credit_vs_truth(main),
        intervals=bootstrap_shares(main.prepared, n_boot=settings.boot),
        stability=seed_stability(base, settings.users, seeds),
        sweep=summarise_sweep(world_sweep(settings.sweep_worlds, settings.sweep_users, settings.seed)),
        holdout=holdout_table(base, settings.users, settings.seed, settings.holdout_reps),
        decisions=decision_table(main.attribution.credit()),
        true_cost=causal_cost(main.truth.table["leave_one_out"]),
        leakage=leakage_effect(main),
        normalisation=normalisation_effect(main.events),
        sql_gap=sql_parity(main, LOOKBACK_DAYS),
    )
