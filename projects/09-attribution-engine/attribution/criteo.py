"""The Criteo attribution dataset: local-only, CC BY-NC-SA 4.0, never committed.

It is real traffic from one display-advertising vendor. Its `campaign` is not a marketing
channel, and `attribution` is the vendor's own credit flag, not a causal label.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .journeys import DAY

COLUMNS = ["timestamp", "uid", "campaign", "conversion", "conversion_timestamp", "conversion_id", "click"]
TOP_CAMPAIGNS = 9


def load(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"{path} not found; run fetch_data.py first")
    frame = pd.read_csv(path, sep="\t", usecols=COLUMNS, dtype="int64", compression="infer")
    validate(frame)
    return frame


def validate(frame: pd.DataFrame) -> None:
    missing = [c for c in COLUMNS if c not in frame.columns]
    if missing:
        raise ValueError(f"missing columns: {missing}")
    for flag in ("conversion", "click"):
        if not frame[flag].isin([0, 1]).all():
            raise ValueError(f"{flag} must be 0 or 1")
    bad = (frame["conversion"] == 1) & ((frame["conversion_timestamp"] < 0) | (frame["conversion_id"] < 0))
    if bad.any():
        raise ValueError("converted rows need a conversion time and id")


def audit(frame: pd.DataFrame) -> dict[str, float]:
    """Facts that decide what this dataset can be used for. Computed on every impression row."""
    converted = frame[frame["conversion"] == 1]
    keys = ["uid", "conversion_id"]
    per_conversion = converted.groupby(keys).agg(campaigns=("campaign", "nunique"), at=("conversion_timestamp", "first"))
    observed_end = int(frame["timestamp"].max())
    pair = ["uid", "campaign"]
    buyers = converted[[*pair, "conversion_timestamp"]].drop_duplicates().sort_values("conversion_timestamp")
    unclicked = frame[(frame["click"] == 0) & frame["uid"].isin(buyers["uid"])][[*pair, "timestamp"]].sort_values("timestamp")
    following = pd.merge_asof(
        unclicked, buyers, left_on="timestamp", right_on="conversion_timestamp", by=pair, direction="forward", allow_exact_matches=False
    )
    within = (following["conversion_timestamp"] - following["timestamp"]) <= 30 * DAY
    return {
        "impression_rows": len(frame),
        "users": int(frame["uid"].nunique()),
        "campaigns": int(frame["campaign"].nunique()),
        "click_rows": int(frame["click"].sum()),
        "rows_marked_converted": len(converted),
        "converted_rows_without_a_click": int((converted["click"] == 0).sum()),
        "same_user_campaign_unclicked_rows_within_30d_before_conversion_marked_0": int(within.sum()),
        "rows_after_their_conversion": int((converted["timestamp"] > converted["conversion_timestamp"]).sum()),
        "conversions": len(per_conversion),
        "conversion_paths_with_more_than_one_campaign": int((per_conversion["campaigns"] > 1).sum()),
        "observed_days": observed_end / DAY,
        "conversions_after_the_last_observed_impression": int((per_conversion["at"] > observed_end).sum()),
    }


def click_journeys(frame: pd.DataFrame, lookback_days: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Click paths. Conversions are kept only when their whole lookback window was observed.

    Converting journey: the clicks sharing a (uid, conversion_id). Non-converting journey: a
    user's other clicks in the final `lookback_days` of the data. The channel is the campaign id.
    """
    if lookback_days <= 0:
        raise ValueError("lookback_days must be positive")
    observed_end = int(frame["timestamp"].max()) + 1
    first_full = lookback_days * DAY
    if first_full >= observed_end:
        raise ValueError("lookback is longer than the observed window")
    clicks = frame[frame["click"] == 1]
    yes = clicks[clicks["conversion"] == 1]
    yes = yes[(yes["conversion_timestamp"] >= first_full) & (yes["conversion_timestamp"] <= observed_end)]
    yes_id = yes.groupby(["uid", "conversion_id"], sort=False).ngroup().to_numpy()
    yes_journeys = pd.DataFrame({"journey_id": yes_id, "converted": True, "end_ts": yes["conversion_timestamp"].to_numpy()})
    yes_journeys = yes_journeys.drop_duplicates("journey_id")
    no = clicks[(clicks["conversion"] == 0) & (clicks["timestamp"] >= observed_end - first_full)]
    offset = int(yes_id.max()) + 1 if len(yes_id) else 0
    no_id = pd.factorize(no["uid"])[0] + offset
    no_journeys = pd.DataFrame({"journey_id": np.unique(no_id), "converted": False, "end_ts": observed_end})
    touches = pd.DataFrame(
        {
            "journey_id": np.concatenate([yes_id, no_id]),
            "ts": np.concatenate([yes["timestamp"].to_numpy(), no["timestamp"].to_numpy()]),
            "channel": np.concatenate([yes["campaign"].to_numpy(), no["campaign"].to_numpy()]).astype(str),
        }
    )
    return touches, pd.concat([yes_journeys, no_journeys], ignore_index=True)


def group_campaigns(touches: pd.DataFrame, journeys: pd.DataFrame, top: int = TOP_CAMPAIGNS) -> pd.DataFrame:
    """Keep the `top` campaigns by converting clicks as A, B, C...; pool the rest as 'other'."""
    if not 1 <= top <= 13:
        raise ValueError("top must be between 1 and 13 so that exact Shapley stays possible")
    winners = journeys.loc[journeys["converted"], "journey_id"]
    counts = touches.loc[touches["journey_id"].isin(winners), "channel"].value_counts()
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:top]
    names = {campaign: f"campaign_{chr(ord('A') + i)}" for i, (campaign, _) in enumerate(ranked)}
    return touches.assign(channel=touches["channel"].map(names).fillna("other"))
