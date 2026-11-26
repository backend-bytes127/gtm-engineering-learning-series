"""Small hand-made data. Nothing here comes from a real dataset."""

from __future__ import annotations

import numpy as np
import pandas as pd

from pql.config import DAY_MS, MINUTE_MS, CohortConfig

COLUMNS = ["timestamp", "visitorid", "event", "itemid", "transactionid"]
START = pd.Timestamp("2015-05-01").value // 1_000_000
SMALL = CohortConfig(cutoff_minutes=30, horizon_days=7, burn_in_days=1, max_window_events=5)


def row(visitor: int, minutes: float, event: str = "view", item: int = 1, transaction: float = np.nan, day: int = 2) -> tuple:
    return (int(START + day * DAY_MS + minutes * MINUTE_MS), visitor, event, item, transaction)


def frame(rows: list[tuple]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=COLUMNS)


def cohort_events() -> pd.DataFrame:
    """One visitor per eligibility case."""
    rows = [
        row(1, 0, day=0),  # seen during burn-in
        row(2, 0), row(2, 5, "addtocart"), row(2, 45, "transaction", transaction=1),  # buys after the cut-off
        row(3, 0), row(3, 10, "transaction", transaction=2),  # bought before the cut-off
        *[row(4, i) for i in range(6)],  # automation-like volume
        row(5, 0), row(5, 30), row(5, 31, "addtocart"),  # boundary: minute 30 is in, minute 31 is out
        row(6, 0), row(6, 8 * 24 * 60, "transaction", transaction=3),  # buys after the horizon
        row(7, 0, day=40),  # label window runs past the end of the data
        row(8, 0, day=41),
    ]
    return frame(rows)


def synthetic_events(per_day: int = 40, days: int = 120, seed: int = 3) -> pd.DataFrame:
    """A random feed where carting really does raise the chance of a later purchase."""
    rng = np.random.default_rng(seed)
    rows, visitor = [], 100
    for day in range(days):
        for _ in range(per_day):
            visitor += 1
            minute = float(rng.uniform(0, 1200))
            n = int(rng.integers(1, 6))
            for i in range(n):
                rows.append(row(visitor, minute + 2 * i, item=int(rng.integers(1, 5)), day=day))
            carted = rng.random() < 0.15
            if carted:
                rows.append(row(visitor, minute + 11, "addtocart", day=day))
            if rng.random() < (0.35 if carted else 0.02 * n / 3):
                delay = 90 if rng.random() < 0.5 else float(rng.uniform(1500, 4000))  # some buy after a day or more
                rows.append(row(visitor, minute + delay, "transaction", transaction=visitor, day=day))
    return frame(rows)


def uci_frame(n: int = 3000, seed: int = 5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    bought = rng.random(n) < 0.25
    months = rng.choice(["Feb", "Mar", "May", "June", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], n)
    data = {
        name: rng.random(n)
        for name in [
            "Administrative", "Administrative_Duration", "Informational", "Informational_Duration", "ProductRelated",
            "ProductRelated_Duration", "BounceRates", "ExitRates", "SpecialDay",
        ]
    }
    data["PageValues"] = np.where(bought, rng.uniform(5, 50, n), 0) * (rng.random(n) < 0.9)
    for name in ["OperatingSystems", "Browser", "Region", "TrafficType"]:
        data[name] = rng.integers(1, 4, n)
    data.update({"Month": months, "VisitorType": rng.choice(["New_Visitor", "Returning_Visitor"], n)})
    data.update({"Weekend": rng.random(n) < 0.3, "Revenue": bought})
    return pd.DataFrame(data)
