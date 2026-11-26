"""An aggregate playbook: rank prior-campaign segments on past months, then check them on later months."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .features import NOT_CONTACTED

RECENT_DAYS = 7


def history_segment(frame: pd.DataFrame) -> pd.Series:
    days = pd.to_numeric(frame["pdays"], errors="coerce")
    dated = days.notna() & (days != NOT_CONTACTED)
    success = frame["poutcome"] == "success"
    names = np.select(
        [success & dated & (days <= RECENT_DAYS), success, frame["poutcome"] == "failure"],
        [f"earlier success, dated within {RECENT_DAYS} days", "earlier success, older or undated", "earlier attempt failed"],
        default="no earlier campaign",
    )
    return pd.Series(names, index=frame.index)


def segment_table(frame: pd.DataFrame, test_start: str) -> pd.DataFrame:
    tagged = frame.assign(segment=history_segment(frame), later=frame["period"] >= test_start)
    parts = {}
    for label, part in (("past", tagged[~tagged["later"]]), ("later", tagged[tagged["later"]])):
        stats = part.groupby("segment")["won"].agg(["size", "mean"])
        parts[f"{label}_rows"], parts[f"{label}_win_rate"] = stats["size"], stats["mean"]
    out = pd.DataFrame(parts).fillna({"past_rows": 0, "later_rows": 0}).sort_values("past_win_rate", ascending=False)
    return out.astype({"past_rows": int, "later_rows": int}).reset_index()
