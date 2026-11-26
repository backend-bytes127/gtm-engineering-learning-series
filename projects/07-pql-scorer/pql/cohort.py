"""Define the point in time of every prediction, who is eligible, and the label."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from pql.config import DAY_MS, CohortConfig


@dataclass(frozen=True)
class Cohort:
    visitors: pd.DataFrame  # index visitorid: first_ts, cutoff_ts, label
    window: pd.DataFrame  # events of eligible visitors with timestamp <= their cut-off
    counts: dict[str, int]


def _times(events: pd.DataFrame, config: CohortConfig) -> pd.DataFrame:
    first = events.groupby("visitorid", sort=True)["timestamp"].min()
    return pd.DataFrame({"first_ts": first, "cutoff_ts": first + config.cutoff_ms})


def build_cohort(events: pd.DataFrame, config: CohortConfig, data_end_ms: int | None = None) -> Cohort:
    """One row per new visitor, scored at first event + cut-off.

    Excluded, in this order: seen during the burn-in; label window runs past the end of the data;
    already bought by the cut-off (there is nothing left to predict); automation-like volume.
    """
    start_ms = int(events["timestamp"].min())
    end_ms = int(events["timestamp"].max()) if data_end_ms is None else data_end_ms
    visitors = _times(events, config)
    cutoff = events["visitorid"].map(visitors["cutoff_ts"])
    window = events[events["timestamp"] <= cutoff]

    bought = events[events["event"] == "transaction"]
    bought_cutoff = bought["visitorid"].map(visitors["cutoff_ts"])
    later = bought[(bought["timestamp"] > bought_cutoff) & (bought["timestamp"] <= bought_cutoff + config.horizon_ms)]
    early = bought[bought["timestamp"] <= bought_cutoff]
    visitors = visitors.assign(label=visitors.index.isin(later["visitorid"]).astype(int))

    burn_in = visitors["first_ts"] < start_ms + config.burn_in_days * DAY_MS
    censored = ~burn_in & (visitors["cutoff_ts"] + config.horizon_ms > end_ms)
    remaining = ~burn_in & ~censored
    already = remaining & visitors.index.isin(early["visitorid"])
    sizes = window.groupby("visitorid").size().reindex(visitors.index, fill_value=0)
    automated = remaining & ~already & (sizes > config.max_window_events)
    eligible = remaining & ~already & ~automated

    counts = {
        "visitors_total": len(visitors),
        "excluded_burn_in": int(burn_in.sum()),
        "excluded_label_window_incomplete": int(censored.sum()),
        "excluded_bought_before_cutoff": int(already.sum()),
        "excluded_automation_like": int(automated.sum()),
        "excluded_automation_like_later_buyers": int(visitors.loc[automated, "label"].sum()),
        "eligible": int(eligible.sum()),
        "eligible_later_buyers": int(visitors.loc[eligible, "label"].sum()),
    }
    kept = visitors[eligible]
    return Cohort(visitors=kept, window=window[window["visitorid"].isin(kept.index)], counts=counts)


def buyer_timing(events: pd.DataFrame, cutoffs_minutes: tuple[int, ...], config: CohortConfig) -> list[dict[str, float]]:
    """How many first purchases have already happened by each possible scoring time (burn-in excluded)."""
    first = events.groupby("visitorid")["timestamp"].min()
    first = first[first >= events["timestamp"].min() + config.burn_in_days * DAY_MS]
    purchase = events[events["event"] == "transaction"].groupby("visitorid")["timestamp"].min()
    delay = (purchase - first.reindex(purchase.index)).dropna().to_numpy()
    return [
        {"cutoff_minutes": minutes, "buyers": int(delay.size), "share_already_bought": float(np.mean(delay <= minutes * 60_000))}
        for minutes in cutoffs_minutes
    ]


def time_split(visitors: pd.DataFrame, validation_start: str, test_start: str, config: CohortConfig) -> dict[str, pd.Index]:
    """Split by first-seen date with an embargo: earlier labels must be fully known when the next period starts."""
    val_ms = pd.Timestamp(validation_start).value // 1_000_000
    test_ms = pd.Timestamp(test_start).value // 1_000_000
    if val_ms >= test_ms:
        raise ValueError("validation_start must be before test_start")
    known_at = visitors["cutoff_ts"] + config.horizon_ms
    return {
        "train": visitors.index[known_at <= val_ms],
        "validation": visitors.index[(visitors["first_ts"] >= val_ms) & (known_at <= test_ms)],
        "test": visitors.index[visitors["first_ts"] >= test_ms],
    }


def funnel_population(events: pd.DataFrame, validation_start: str, config: CohortConfig) -> pd.Series:
    """First-seen time of ALL new visitors with a full horizon before validation, including fast buyers."""
    first = events.groupby("visitorid")["timestamp"].min()
    start = events["timestamp"].min() + config.burn_in_days * DAY_MS
    end = pd.Timestamp(validation_start).value // 1_000_000 - config.horizon_ms
    return first[(first >= start) & (first <= end)]
