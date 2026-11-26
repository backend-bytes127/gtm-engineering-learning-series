"""Point-in-time journey construction.

A journey is one row in `journeys` (journey_id, converted, end_ts) plus its rows in `touches`
(journey_id, ts, channel). `end_ts` is the conversion time for a converting journey and the end
of observation for the others. Timestamps are in seconds.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

DAY = 86_400.0
TOUCH_COLUMNS = ("journey_id", "ts", "channel")
JOURNEY_COLUMNS = ("journey_id", "converted", "end_ts")


@dataclass(frozen=True)
class Prepared:
    touches: pd.DataFrame  # eligible touches, ordered, with `converted` and `end_ts`
    n_conversions: int  # conversions with at least one eligible touch
    n_untracked_conversions: int  # conversions with none; no method may credit these
    dropped: dict[str, int]


def _require(frame: pd.DataFrame, columns: tuple[str, ...], name: str) -> None:
    missing = [c for c in columns if c not in frame.columns]
    if missing:
        raise ValueError(f"{name} is missing columns: {missing}")
    if frame[list(columns)].isna().any().any():
        raise ValueError(f"{name} has missing values in {list(columns)}")


def prepare(touches: pd.DataFrame, journeys: pd.DataFrame, lookback_days: float = 30.0) -> Prepared:
    """Keep only touches that happened strictly before the journey end and inside the lookback window."""
    _require(touches, TOUCH_COLUMNS, "touches")
    _require(journeys, JOURNEY_COLUMNS, "journeys")
    if lookback_days <= 0:
        raise ValueError("lookback_days must be positive")
    if journeys["journey_id"].duplicated().any():
        raise ValueError("journey_id must be unique in journeys")
    merged = touches[list(TOUCH_COLUMNS)].merge(journeys[list(JOURNEY_COLUMNS)], on="journey_id", how="left")
    if merged["end_ts"].isna().any():
        raise ValueError("some touches point to a journey that does not exist")
    after = merged["ts"] >= merged["end_ts"]
    too_old = ~after & (merged["ts"] < merged["end_ts"] - lookback_days * DAY)
    kept = merged[~after & ~too_old]
    unique = kept.drop_duplicates(subset=list(TOUCH_COLUMNS))
    ordered = unique.sort_values(["journey_id", "ts", "channel"], kind="mergesort").reset_index(drop=True)
    ordered = ordered.astype({"converted": bool})
    tracked = int(ordered.loc[ordered["converted"], "journey_id"].nunique())
    total = int(journeys["converted"].astype(bool).sum())
    dropped = {"at_or_after_end": int(after.sum()), "outside_lookback": int(too_old.sum()), "duplicate": len(kept) - len(unique)}
    return Prepared(ordered, tracked, total - tracked, dropped)


def channel_names(prepared: Prepared) -> list[str]:
    return sorted(prepared.touches["channel"].unique().tolist())


def path_table(prepared: Prepared) -> pd.DataFrame:
    """Unique ordered paths with the number of converting and non-converting journeys on each."""
    t = prepared.touches
    if t.empty:
        return pd.DataFrame(columns=["path", "conversions", "nulls"])
    ids = t["journey_id"].to_numpy()
    channels = t["channel"].to_numpy().tolist()
    starts = np.flatnonzero(np.r_[True, ids[1:] != ids[:-1]])
    ends = np.r_[starts[1:], len(ids)]
    paths = [tuple(channels[a:b]) for a, b in zip(starts, ends)]
    frame = pd.DataFrame({"path": pd.Series(paths, dtype=object), "converted": t["converted"].to_numpy()[starts]})
    counts: dict[tuple[str, ...], list[int]] = {}
    for path, converted in zip(frame["path"], frame["converted"]):
        counts.setdefault(path, [0, 0])[0 if converted else 1] += 1
    keys = sorted(counts)
    return pd.DataFrame(
        {"path": pd.Series(keys, dtype=object), "conversions": [counts[k][0] for k in keys], "nulls": [counts[k][1] for k in keys]}
    )
