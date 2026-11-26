"""Turn the events seen before the cut-off into one row of features per visitor."""

from __future__ import annotations

import numpy as np
import pandas as pd

from pql.config import MINUTE_MS, CohortConfig

FEATURES: tuple[str, ...] = (
    "views",
    "cart_adds",
    "distinct_items",
    "repeat_views",
    "max_views_one_item",
    "cart_items",
    "active_minutes",
    "idle_minutes_at_cutoff",
    "visits",
    "minutes_to_first_cart",
    "first_hour_utc",
    "first_weekday",
)


class LeakageError(ValueError):
    """An event after the prediction time reached the feature builder."""


def assert_no_future(window: pd.DataFrame, visitors: pd.DataFrame) -> None:
    cutoff = window["visitorid"].map(visitors["cutoff_ts"])
    late = int((window["timestamp"] > cutoff).sum())
    if late:
        raise LeakageError(f"{late} events are later than their visitor's cut-off")


def _counts(window: pd.DataFrame, index: pd.Index) -> pd.DataFrame:
    views = window[window["event"] == "view"]
    carts = window[window["event"] == "addtocart"]
    per_item = views.groupby(["visitorid", "itemid"]).size()
    columns = {
        "views": views.groupby("visitorid").size(),
        "cart_adds": carts.groupby("visitorid").size(),
        "distinct_items": window.groupby("visitorid")["itemid"].nunique(),
        "viewed_items": views.groupby("visitorid")["itemid"].nunique(),
        "max_views_one_item": per_item.groupby(level="visitorid").max(),
        "cart_items": carts.groupby("visitorid")["itemid"].nunique(),
    }
    frame = pd.DataFrame({name: column.reindex(index) for name, column in columns.items()}, index=index)
    return frame.fillna(0)


def build_features(window: pd.DataFrame, visitors: pd.DataFrame, config: CohortConfig) -> pd.DataFrame:
    """Features use only events at or before the cut-off; the function refuses anything later."""
    assert_no_future(window, visitors)
    index = visitors.index
    frame = _counts(window, index)
    ordered = window.sort_values(["visitorid", "timestamp"], kind="stable")
    gap = ordered.groupby("visitorid")["timestamp"].diff()
    new_visit = gap.isna() | (gap > config.session_gap_minutes * MINUTE_MS)
    last = ordered.groupby("visitorid")["timestamp"].max().reindex(index)
    first_cart = ordered[ordered["event"] == "addtocart"].groupby("visitorid")["timestamp"].min().reindex(index)
    started = pd.to_datetime(visitors["first_ts"], unit="ms")
    to_cart = (first_cart - visitors["first_ts"]) / MINUTE_MS
    result = frame.assign(
        repeat_views=frame["views"] - frame["viewed_items"],
        active_minutes=(last - visitors["first_ts"]) / MINUTE_MS,
        idle_minutes_at_cutoff=(visitors["cutoff_ts"] - last) / MINUTE_MS,
        visits=new_visit.astype(int).groupby(ordered["visitorid"]).sum().reindex(index),
        minutes_to_first_cart=to_cart.fillna(config.cutoff_minutes),  # "not yet" is coded as the cut-off
        first_hour_utc=started.dt.hour,
        first_weekday=started.dt.day_of_week,
    )
    return result[list(FEATURES)].astype(np.float64)
