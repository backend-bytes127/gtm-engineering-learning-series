"""The same point-in-time rules and positional methods in SQL, run on an in-memory SQLite database."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from .heuristics import HALF_LIFE_DAYS
from .journeys import DAY, JOURNEY_COLUMNS, TOUCH_COLUMNS

SQL_DIR = Path(__file__).with_name("sql")


def _read(name: str) -> str:
    return (SQL_DIR / name).read_text(encoding="utf-8")


def connect(touches: pd.DataFrame, journeys: pd.DataFrame, lookback_days: float) -> sqlite3.Connection:
    if lookback_days <= 0:
        raise ValueError("lookback_days must be positive")
    con = sqlite3.connect(":memory:")
    # SQLite only has pow() when built with the math extension, so supply the decay weight ourselves.
    con.create_function("decay_weight", 2, lambda age, half_life: 0.5 ** (age / half_life), deterministic=True)
    touches[list(TOUCH_COLUMNS)].to_sql("raw_touches", con, index=False)
    journeys[list(JOURNEY_COLUMNS)].astype({"converted": int}).to_sql("journeys", con, index=False)
    con.execute("CREATE UNIQUE INDEX ix_journey ON journeys(journey_id)")
    con.execute("CREATE TABLE settings (lookback_seconds REAL, half_life_seconds REAL)")
    con.execute("INSERT INTO settings VALUES (?, ?)", (lookback_days * DAY, HALF_LIFE_DAYS * DAY))
    con.executescript(_read("01_eligible_touches.sql"))
    return con


def heuristic_credit(con: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(_read("02_heuristic_attribution.sql"), con).set_index("channel")


def transition_counts(con: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(_read("03_markov_transitions.sql"), con)
