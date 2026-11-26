"""Reason codes: which supplied field pushed this row up or down, and what was unknown."""
from __future__ import annotations

import pandas as pd

from .features import NOT_CONTACTED, NUMERIC_HISTORY

# numeric model column -> the source column a rep can check
SOURCE_OF = {"previous_capped": "previous", "recency_weight": "pdays", "days_since_unknown": "pdays"}
MIN_EFFECT = 0.05  # log-odds; smaller effects are noise to a rep


def field_effects(column_effects, columns: list[tuple[str, str]]) -> dict[str, float]:
    totals: dict[str, float] = {}
    for effect, (name, _) in zip(column_effects, columns, strict=True):
        source = SOURCE_OF.get(name, name) if name in NUMERIC_HISTORY else name
        totals[source] = totals.get(source, 0.0) + float(effect)
    return totals


def shown_value(row: pd.Series, field: str) -> str:
    value = row.get(field, "")
    if pd.isna(value) or str(value).strip() == "":
        return "not supplied"
    if field == "pdays" and float(value) == NOT_CONTACTED:
        return "no dated prior contact"
    return str(value)


def unknown_fields(row: pd.Series, categories: dict[str, tuple[str, ...]]) -> list[str]:
    """Missing, never-seen and literal 'unknown' values. Unknown is reported; it is not read as 'no'."""
    notes = []
    for field, levels in categories.items():
        value = shown_value(row, field)
        if value == "not supplied":
            notes.append(f"{field}: not supplied (neutral)")
        elif value == "unknown":
            notes.append(f"{field}: unknown in source")
        elif value not in levels:
            notes.append(f"{field}: value never seen in training (neutral)")
    notes += [f"{f}: not supplied (neutral)" for f in ("previous", "pdays") if shown_value(row, f) == "not supplied"]
    previous = shown_value(row, "previous")
    if previous not in ("not supplied", "0") and shown_value(row, "pdays") == "no dated prior contact":
        notes.append("pdays: contacted before but no date recorded")
    return notes


def reason_codes(row: pd.Series, effects: dict[str, float], limit: int = 3) -> list[str]:
    strongest = sorted(effects.items(), key=lambda kv: -abs(kv[1]))
    codes = []
    for field, effect in strongest:
        value = shown_value(row, field)
        if abs(effect) < MIN_EFFECT or value == "not supplied":
            continue
        direction = "UP" if effect > 0 else "DOWN"
        codes.append(f"{direction} {field}={value} ({effect:+.2f} log-odds)")
        if len(codes) == limit:
            break
    return codes
