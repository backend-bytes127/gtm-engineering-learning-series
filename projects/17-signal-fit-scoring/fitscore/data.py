"""Load the UCI file and rebuild the calendar month from row order."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import config

MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
REQUIRED = ("job", "education", "default", "housing", "loan", "pdays", "previous", "poutcome", "month", config.TARGET)


def add_period(frame: pd.DataFrame, first_year: int = config.FIRST_YEAR) -> pd.DataFrame:
    """Return a copy with `period` (YYYY-MM). The year goes up each time the month number goes down.

    This relies on the publisher's statement that rows are in date order. A gap of more than twelve
    months could not be detected; the test of the final month checks the documented end date.
    """
    numbers = frame["month"].map({name: i + 1 for i, name in enumerate(MONTHS)})
    if numbers.isna().any():
        raise ValueError("unrecognised month value")
    years = first_year + (numbers.diff() < 0).cumsum()
    period = years.astype(int).astype(str) + "-" + numbers.astype(int).astype(str).str.zfill(2)
    return frame.assign(period=period)


def prepare(frame: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in REQUIRED if c not in frame.columns]
    if missing:
        raise ValueError(f"missing columns: {missing}")
    bad = set(frame[config.TARGET].unique()) - {"yes", "no"}
    if bad:
        raise ValueError(f"unexpected target values: {sorted(map(str, bad))}")
    out = add_period(frame.reset_index(drop=True))
    return out.assign(won=(out[config.TARGET] == "yes").astype(int))


def load_bank(path: Path = config.UCI_CSV) -> pd.DataFrame:
    if not Path(path).exists():
        raise FileNotFoundError(f"{path} not found. Run: python fetch_data.py")
    return prepare(pd.read_csv(path, sep=";"))
