"""Small hand-made fixtures. No downloaded data and no network."""
from __future__ import annotations

import pandas as pd
import pytest

from attribution.journeys import DAY, prepare


def make(paths: dict[int, tuple[bool, list[tuple[float, str]]]], end_day: float = 30.0):
    """{journey_id: (converted, [(day, channel), ...])} -> (touches, journeys)."""
    touches = [(j, day * DAY, channel) for j, (_, rows) in paths.items() for day, channel in rows]
    journeys = [(j, converted, end_day * DAY) for j, (converted, _) in paths.items()]
    return (
        pd.DataFrame(touches, columns=["journey_id", "ts", "channel"]),
        pd.DataFrame(journeys, columns=["journey_id", "converted", "end_ts"]),
    )


HAND = {
    1: (True, [(2, "social"), (9, "email"), (16, "email"), (23, "search")]),
    2: (True, [(23, "search")]),
    3: (True, [(9, "social"), (23, "email")]),
    4: (False, [(5, "social")]),
    5: (False, [(5, "email"), (6, "search")]),
}


@pytest.fixture
def hand():
    return prepare(*make(HAND), lookback_days=30)
