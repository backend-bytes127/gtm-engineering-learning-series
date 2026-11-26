"""A tiny markdown table writer, so reports need no extra dependency."""
from __future__ import annotations

from collections.abc import Callable

import pandas as pd


def table(frame: pd.DataFrame, formats: dict[str, Callable] | Callable | None = None, index_name: str = "") -> str:
    """`formats` is one formatter for every column, or one per column name. Missing values print as n/a."""

    def cell(column: str, value: object) -> str:
        if not isinstance(value, str) and pd.isna(value):
            return "n/a"
        chosen = formats.get(column) if isinstance(formats, dict) else formats
        return chosen(value) if chosen else str(value)

    header = [index_name or frame.index.name or "", *map(str, frame.columns)]
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    for label, row in zip(frame.index, frame.itertuples(index=False, name=None)):
        lines.append("| " + " | ".join([str(label), *(cell(c, v) for c, v in zip(frame.columns, row))]) + " |")
    return "\n".join(lines)


def pct(value: float) -> str:
    return f"{100 * value:.1f}%"


def whole(value: float) -> str:
    return f"{value:,.0f}"


def decimal(value: float) -> str:
    return f"{value:.3f}"
