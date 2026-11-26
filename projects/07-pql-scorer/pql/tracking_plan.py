"""Validate raw events against the tracking plan before any feature is built.

Rows that break the contract are quarantined and counted, never silently dropped.
If too many rows break it, the run stops: an upstream tracking change is more likely than noise.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

PLAN_PATH = Path(__file__).with_name("tracking_plan.json")


class SchemaError(RuntimeError):
    """The feed does not match the tracking plan closely enough to be used."""


@dataclass(frozen=True)
class ValidationResult:
    clean: pd.DataFrame
    violations: dict[str, int]
    rows_in: int

    @property
    def rows_quarantined(self) -> int:
        return self.rows_in - len(self.clean)

    @property
    def quarantine_rate(self) -> float:
        return self.rows_quarantined / self.rows_in if self.rows_in else 0.0


def load_plan(path: Path = PLAN_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _to_integer(series: pd.Series) -> pd.Series:
    """Numeric values that are whole numbers; everything else becomes missing."""
    numbers = pd.to_numeric(series, errors="coerce")
    return numbers.where(numbers % 1 == 0)


def _rule_masks(frame: pd.DataFrame, plan: dict) -> dict[str, pd.Series]:
    masks: dict[str, pd.Series] = {}
    for name, spec in plan["columns"].items():
        if not spec["required"]:
            continue
        missing = frame[name].isna()
        masks[f"missing_{name}"] = missing
        if spec["type"] == "integer":
            numbers = _to_integer(frame[name])
            masks[f"bad_type_{name}"] = numbers.isna() & ~missing
            if "min" in spec:
                masks[f"below_min_{name}"] = numbers < spec["min"]
    masks["unknown_event"] = frame["event"].notna() & ~frame["event"].isin(list(plan["events"]))
    for event, spec in plan["events"].items():
        is_event = frame["event"] == event
        for prop in spec["required"]:
            if not plan["columns"][prop]["required"]:
                masks[f"{event}_without_{prop}"] = is_event & frame[prop].isna()
        for prop in spec["forbidden"]:
            masks[f"{event}_with_{prop}"] = is_event & frame[prop].notna()
    start, end = (pd.Timestamp(plan["window"][k]).value // 1_000_000 for k in ("start", "end"))
    stamps = _to_integer(frame["timestamp"])
    masks["timestamp_out_of_window"] = stamps.notna() & ~stamps.between(start, end)
    return masks


def validate(frame: pd.DataFrame, plan: dict | None = None) -> ValidationResult:
    plan = plan or load_plan()
    absent = [c for c in plan["columns"] if c not in frame.columns]
    if absent:
        raise SchemaError(f"columns missing from the feed: {', '.join(absent)}")
    masks = _rule_masks(frame, plan)
    bad = pd.Series(False, index=frame.index)
    violations: dict[str, int] = {}
    for rule, mask in masks.items():
        count = int(mask.sum())
        if count:
            violations[rule] = count
            bad = bad | mask
    duplicate = frame.duplicated() & ~bad
    if duplicate.any():
        violations["exact_duplicate"] = int(duplicate.sum())
    clean = frame.loc[~bad & ~duplicate, list(plan["columns"])]
    clean = clean.astype({"timestamp": "int64", "visitorid": "int64", "itemid": "int64"})
    clean = clean.sort_values(["visitorid", "timestamp"], kind="stable").reset_index(drop=True)
    result = ValidationResult(clean=clean, violations=violations, rows_in=len(frame))
    broken = int(bad.sum()) / len(frame) if len(frame) else 0.0
    if broken > plan["max_quarantine_rate"]:
        raise SchemaError(f"{broken:.2%} of rows break the tracking plan (limit {plan['max_quarantine_rate']:.2%}): {violations}")
    return result
