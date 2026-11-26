"""Run the audit, the method comparison and an analyst-choice sensitivity on Criteo click paths."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .criteo import audit, click_journeys, group_campaigns, load
from .heuristics import RULES, channel_units
from .journeys import Prepared, path_table, prepare
from .methods import METHODS, Attribution, attribute, total_variation
from .uncertainty import bootstrap_shares

PRIMARY_LOOKBACK_DAYS = 14
LOOKBACKS = (1, 7, 14, 21)


@dataclass(frozen=True)
class CriteoResult:
    audit: dict[str, float]
    prepared: Prepared
    attribution: Attribution
    intervals: pd.DataFrame
    all_campaign_distance: pd.DataFrame  # method x method, every campaign kept separate
    lookbacks: pd.DataFrame
    path_lengths: pd.Series
    multi_campaign_paths: float


def method_distances(shares: pd.DataFrame, methods: list[str]) -> pd.DataFrame:
    return pd.DataFrame({a: {b: total_variation(shares[a], shares[b]) for b in methods} for a in methods})


def _all_campaigns(prepared: Prepared) -> pd.DataFrame:
    units = channel_units(prepared)
    return method_distances(units / units.sum(), list(RULES))


def _lookback_sensitivity(frame: pd.DataFrame, lookbacks: tuple[int, ...]) -> pd.DataFrame:
    rows = []
    for days in lookbacks:
        touches, journeys = click_journeys(frame, days)
        prepared = prepare(group_campaigns(touches, journeys), journeys, days)
        shares = attribute(prepared).shares()
        for method in METHODS:
            rows.append({"lookback_days": days, "method": method, "conversions": prepared.n_conversions, **shares[method].to_dict()})
    return pd.DataFrame(rows)


def run_frame(
    frame: pd.DataFrame, n_boot: int, lookbacks: tuple[int, ...] = LOOKBACKS, primary: int = PRIMARY_LOOKBACK_DAYS
) -> CriteoResult:
    facts = audit(frame)
    touches, journeys = click_journeys(frame, primary)
    ungrouped = prepare(touches, journeys, primary)
    table = path_table(ungrouped)
    multi = table["path"].map(lambda p: len(set(p)) > 1)
    multi_share = float(table.loc[multi, "conversions"].sum() / table["conversions"].sum())
    prepared = prepare(group_campaigns(touches, journeys), journeys, primary)
    result = attribute(prepared)
    converting = prepared.touches[prepared.touches["converted"]]
    return CriteoResult(
        audit=facts,
        prepared=prepared,
        attribution=result,
        intervals=bootstrap_shares(prepared, n_boot=n_boot),
        all_campaign_distance=_all_campaigns(ungrouped),
        lookbacks=_lookback_sensitivity(frame, lookbacks),
        path_lengths=converting.groupby("journey_id").size(),
        multi_campaign_paths=multi_share,
    )


def run_criteo(path: Path, n_boot: int) -> CriteoResult:
    return run_frame(load(path), n_boot)
