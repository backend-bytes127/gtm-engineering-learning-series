"""Hand-made, deterministic fixtures. No downloaded data is needed. These rows are invented."""
from __future__ import annotations

import pandas as pd
import pytest

from fitscore.config import load_config
from fitscore.data import prepare

JOBS = ("admin.", "blue-collar", "retired", "student")
MONTHS = ("may", "jun", "jul", "aug", "sep", "oct")


def make_rows(per_month: int = 60) -> pd.DataFrame:
    rows = []
    for m, month in enumerate(MONTHS):
        for i in range(per_month):
            poutcome = "success" if i % 10 == 0 else ("failure" if i % 10 in (1, 2) else "nonexistent")
            won = (poutcome == "success" and i % 30 != 0) or (poutcome != "success" and (i * 7 + m) % 11 == 0)
            rows.append({
                "age": 20 + (i * 3) % 50, "job": JOBS[i % 4], "marital": ("single", "married")[i % 2],
                "education": ("high.school", "university.degree", "unknown")[i % 3],
                "default": ("no", "unknown")[int(i % 5 == 0)], "housing": ("yes", "no")[i % 2], "loan": ("no", "yes")[int(i % 6 == 0)],
                "contact": ("cellular", "telephone")[int(i % 4 == 0)], "month": month, "day_of_week": ("mon", "tue")[i % 2],
                "duration": 600 if won else 60, "campaign": 1 + i % 3,
                "pdays": 3 + i % 9 if poutcome == "success" else 999, "previous": 0 if poutcome == "nonexistent" else 1,
                "poutcome": poutcome, "emp.var.rate": 1.0 - m / 10, "cons.price.idx": 93.0 + m / 10, "cons.conf.idx": -40.0,
                "euribor3m": 4.0 - m / 10, "nr.employed": 5100.0 - m, "y": "yes" if won else "no",
            })
    return pd.DataFrame(rows)


@pytest.fixture(scope="session")
def raw_rows() -> pd.DataFrame:
    return make_rows()


@pytest.fixture(scope="session")
def frame(raw_rows: pd.DataFrame) -> pd.DataFrame:
    return prepare(raw_rows)


@pytest.fixture(scope="session")
def cfg():
    return load_config()
