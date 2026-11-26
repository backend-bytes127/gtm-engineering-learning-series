"""Small markdown helpers (no extra dependency)."""
from __future__ import annotations

import pandas as pd


def cell(value: object) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def table(frame: pd.DataFrame) -> str:
    header = "| " + " | ".join(map(str, frame.columns)) + " |"
    rule = "|" + "---|" * len(frame.columns)
    body = ["| " + " | ".join(cell(v) for v in row) + " |" for row in frame.astype(object).itertuples(index=False)]
    return "\n".join([header, rule, *body])


def with_interval(frame: pd.DataFrame, column: str, digits: int = 3) -> pd.Series:
    return frame.apply(
        lambda r: f"{r[column]:.{digits}f} ({r[column + '_low']:.{digits}f} to {r[column + '_high']:.{digits}f})", axis=1
    )
