"""Pipeline hygiene shown with numbers: what skipping a step would have done to the answer."""
from __future__ import annotations

import pandas as pd

from .channels import parse_params
from .journeys import DAY, prepare
from .methods import attribute, total_variation
from .scenario import Scenario
from .sqllayer import connect, heuristic_credit

SQL_TOLERANCE = 0.05  # conversions; the integer allocation rounds each journey by under one millionth


def leakage_effect(scenario: Scenario) -> pd.DataFrame:
    """Last-touch share with and without the point-in-time filter (events after the purchase kept)."""
    journeys = scenario.journeys.assign(end_ts=scenario.journeys["end_ts"].max() + 10 * DAY)
    leaky = attribute(prepare(scenario.events, journeys, lookback_days=60)).shares()
    clean = scenario.attribution.shares()
    return pd.DataFrame({"point_in_time": clean["last_touch"], "post_purchase_events_kept": leaky["last_touch"]}).fillna(0.0)


def normalisation_effect(events: pd.DataFrame) -> dict[str, float]:
    """Compare against two shortcuts people take: raw source/medium strings, and 'no utm_source means direct'."""
    pairs = events[["landing_url", "referrer"]].value_counts().reset_index()
    parsed = [parse_params(url) for url in pairs["landing_url"]]
    raw = {f"{p.get('utm_source', '(none)')} / {p.get('utm_medium', '(none)')}" for p in parsed}
    no_source = pd.Series([("utm_source" not in p) for p in parsed])
    pairs = pairs.assign(no_source=no_source.to_numpy())
    mapping = events[["landing_url", "referrer", "channel"]].drop_duplicates()
    pairs = pairs.merge(mapping, on=["landing_url", "referrer"], how="left")
    wrong = pairs.loc[pairs["no_source"] & (pairs["channel"] != "direct"), "count"].sum()
    return {
        "events": len(events),
        "distinct_raw_source_medium_strings": len(raw),
        "channels_after_normalising": int(events["channel"].nunique()),
        "events_matching_planted_channel": float((events["channel"] == events["planted_channel"]).mean()),
        "share_of_events_a_no_utm_source_means_direct_rule_would_mislabel": float(wrong / len(events)),
    }


def sql_parity(scenario: Scenario, lookback_days: float) -> float:
    """Largest gap, in conversions, between SQL and Python credit. Raises if they disagree."""
    con = connect(scenario.events, scenario.journeys, lookback_days)
    try:
        sql = heuristic_credit(con)
    finally:
        con.close()
    python = scenario.attribution.credit()[sql.columns]
    gap = float((sql - python.reindex(sql.index)).abs().to_numpy().max())
    if set(sql.index) != set(python.index) or not gap <= SQL_TOLERANCE:
        raise RuntimeError(f"SQL and Python attribution disagree by {gap:.4f} conversions")
    return gap


def method_spread(shares: pd.DataFrame, methods: list[str]) -> float:
    """Largest total-variation distance between any two methods."""
    return max(total_variation(shares[a], shares[b]) for a in methods for b in methods)
