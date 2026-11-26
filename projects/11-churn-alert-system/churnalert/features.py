"""Point-in-time snapshots. At snapshot t, features read only rows before t; the label reads only [t, t+H)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from .config import HORIZON_DAYS, LOOKBACK_DAYS, MAX_RECENCY_DAYS, MIN_PURCHASE_DAYS

FEATURES = ["recency_days", "purchase_days_180", "purchase_days_90", "purchase_days_prev90", "median_gap_days",
            "overdue_ratio", "net_90", "net_prev90", "net_180", "avg_day_value", "products_90", "return_share_180",
            "is_uk"]


@dataclass(frozen=True)
class History:
    """Daily aggregates: one row per customer-day, and one per customer-day-product bought."""
    days: pd.DataFrame
    products: pd.DataFrame
    last_day: pd.Timestamp


def prepare(lines: pd.DataFrame) -> History:
    frame = lines.assign(day=lines["ts"].dt.normalize(),
                         gross=lines["pence"].where(lines["is_sale"] == 1, 0),
                         returned=(-lines["pence"]).clip(lower=0),
                         uk=(lines["country"] == "United Kingdom").astype(int))
    days = frame.groupby(["customer_id", "day"], as_index=False).agg(
        net=("pence", "sum"), gross=("gross", "sum"), returned=("returned", "sum"), bought=("is_sale", "max"), uk=("uk", "max"))
    products = frame.loc[frame["is_sale"] == 1, ["customer_id", "day", "stock_code"]].drop_duplicates()
    return History(days, products.reset_index(drop=True), frame["day"].max())


def gap_evidence(history: History, before: date, horizon: int = HORIZON_DAYS) -> dict[str, float]:
    """Share of observed gaps between purchase days, all before `before`, that were no longer than the horizon."""
    buys = history.days[(history.days["bought"] == 1) & (history.days["day"] < pd.Timestamp(before))]
    gaps = buys.sort_values(["customer_id", "day"]).groupby("customer_id")["day"].diff().dt.days.dropna()
    return {"gaps": len(gaps), "within_horizon": float((gaps <= horizon).mean()) if len(gaps) else float("nan")}


def _between(frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    return frame[(frame["day"] >= start) & (frame["day"] < end)]


def snapshot_features(history: History, as_of: date) -> pd.DataFrame:
    """Eligible accounts at the start of `as_of`: repeat buyers in the lookback who have not yet lapsed."""
    cut = pd.Timestamp(as_of)
    mid = cut - pd.Timedelta(days=90)
    window = _between(history.days, cut - pd.Timedelta(days=LOOKBACK_DAYS), cut)
    buys = window[window["bought"] == 1].sort_values(["customer_id", "day"])
    gaps = buys.assign(gap=buys.groupby("customer_id")["day"].diff().dt.days)
    stats = gaps.groupby("customer_id").agg(last=("day", "max"), purchase_days_180=("day", "size"),
                                            median_gap_days=("gap", "median"))
    stats = stats.assign(recency_days=(cut - stats["last"]).dt.days)
    keep = stats[(stats["purchase_days_180"] >= MIN_PURCHASE_DAYS) & (stats["recency_days"] <= MAX_RECENCY_DAYS)]
    recent, earlier = window[window["day"] >= mid], window[window["day"] < mid]
    totals = window.groupby("customer_id").agg(net=("net", "sum"), gross=("gross", "sum"), returned=("returned", "sum"),
                                               is_uk=("uk", "max"))
    distinct = _between(history.products, mid, cut).groupby("customer_id")["stock_code"].nunique()
    out = keep.drop(columns="last").join(totals)

    def count(part: pd.DataFrame) -> pd.Series:
        return part.groupby("customer_id")["bought"].sum().reindex(out.index, fill_value=0)

    def value(part: pd.DataFrame) -> pd.Series:
        return part.groupby("customer_id")["net"].sum().reindex(out.index, fill_value=0).clip(lower=0) / 100

    net_180 = out["net"].clip(lower=0) / 100
    out = out.assign(
        purchase_days_90=count(recent), purchase_days_prev90=count(earlier), net_90=value(recent), net_prev90=value(earlier),
        net_180=net_180, avg_day_value=net_180 / out["purchase_days_180"],
        overdue_ratio=out["recency_days"] / out["median_gap_days"].clip(lower=1),
        products_90=distinct.reindex(out.index, fill_value=0),
        return_share_180=(out["returned"] / out["gross"].clip(lower=1)).clip(upper=1))
    return out[FEATURES].reset_index().assign(as_of=cut).sort_values("customer_id").reset_index(drop=True)


def labels(history: History, customers: pd.Series, as_of: date, horizon: int = HORIZON_DAYS) -> np.ndarray:
    """1 = churned: no purchase day in [as_of, as_of + horizon). Refuses a window the data cannot fully show."""
    cut = pd.Timestamp(as_of)
    end = cut + pd.Timedelta(days=horizon)
    if end > history.last_day + pd.Timedelta(days=1):
        raise ValueError(f"label window for {as_of} ends {end.date()}, after the data ends {history.last_day.date()}")
    future = _between(history.days, cut, end)
    buyers = set(future.loc[future["bought"] == 1, "customer_id"])
    return np.array([0 if c in buyers else 1 for c in customers], dtype=int)


def labelled_snapshot(history: History, as_of: date, horizon: int = HORIZON_DAYS) -> pd.DataFrame:
    frame = snapshot_features(history, as_of)
    return frame.assign(churned=labels(history, frame["customer_id"], as_of, horizon))
