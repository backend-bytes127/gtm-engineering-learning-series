"""Activation milestones (as of the cut-off) and the view -> cart -> purchase funnel."""

from __future__ import annotations

import numpy as np
import pandas as pd

from pql.config import MINUTE_MS

# Written before looking at test results. Each is a plain statement a sales or lifecycle owner can act on.
MILESTONES: dict[str, tuple[str, float]] = {
    "M1_compared_2_items": ("distinct_items", 2),
    "M2_returned_to_an_item": ("repeat_views", 1),
    "M3_explored_5_items": ("distinct_items", 5),
    "M4_added_to_cart": ("cart_adds", 1),
    "M5_carted_2_items": ("cart_items", 2),
}


def reached(features: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({name: features[column] >= minimum for name, (column, minimum) in MILESTONES.items()}, index=features.index)


def milestone_table(features: pd.DataFrame, labels: pd.Series) -> list[dict[str, float | str]]:
    """Reach, later purchase rate with and without, and share of later buyers each milestone catches."""
    flags = reached(features)
    outcome = labels.to_numpy()
    base = float(outcome.mean()) if outcome.size else 0.0
    rows: list[dict[str, float | str]] = []
    for name in MILESTONES:
        hit = flags[name].to_numpy()
        with_rate = float(outcome[hit].mean()) if hit.any() else 0.0
        without_rate = float(outcome[~hit].mean()) if (~hit).any() else 0.0
        rows.append(
            {
                "milestone": name,
                "reach": float(np.mean(hit)) if hit.size else 0.0,
                "buy_rate_reached": with_rate,
                "buy_rate_not_reached": without_rate,
                "lift_over_base": with_rate / base if base else 0.0,
                "share_of_later_buyers": float(outcome[hit].sum() / outcome.sum()) if outcome.sum() else 0.0,
            }
        )
    return rows


def funnel(events: pd.DataFrame, visitor_ids: pd.Index, first_ts: pd.Series, horizon_ms: int) -> list[dict[str, float | str]]:
    """Ordered funnel over each visitor's first `horizon_ms`: cart must follow a view, purchase must follow a cart."""
    scoped = events[events["visitorid"].isin(visitor_ids)]
    scoped = scoped[scoped["timestamp"] <= scoped["visitorid"].map(first_ts) + horizon_ms]

    def first_after(event: str, after: pd.Series) -> pd.Series:
        rows = scoped[(scoped["event"] == event) & scoped["visitorid"].isin(after.index)]
        rows = rows[rows["timestamp"] >= rows["visitorid"].map(after)]
        return rows.groupby("visitorid")["timestamp"].min()

    viewed = scoped[scoped["event"] == "view"].groupby("visitorid")["timestamp"].min()
    carted = first_after("addtocart", viewed)
    bought = first_after("transaction", carted)
    anybuy = scoped.loc[scoped["event"] == "transaction", "visitorid"].nunique()

    def step(name: str, now: pd.Series, before: pd.Series | None) -> dict[str, float | str]:
        previous = len(visitor_ids) if before is None else len(before)
        minutes = float(((now - before.reindex(now.index)) / MINUTE_MS).median()) if before is not None and len(now) else 0.0
        return {"step": name, "visitors": len(now), "from_previous": len(now) / previous if previous else 0.0, "median_minutes": minutes}

    rows = [step("viewed", viewed, None), step("added_to_cart", carted, viewed), step("purchased", bought, carted)]
    rows.append({"step": "purchased_without_that_path", "visitors": int(anybuy - len(bought)), "from_previous": 0.0, "median_minutes": 0.0})
    return rows
