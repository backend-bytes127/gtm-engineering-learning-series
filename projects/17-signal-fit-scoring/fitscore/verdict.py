"""The short answer, written from the computed intervals so it cannot drift from the tables."""
from __future__ import annotations

import pandas as pd

from .metrics import auc

RULES = ("points_rules", "previous_success_first", "most_recent_first")
LABELS = {"within_month_auc": "ordering the whole list (within-month AUC)", "lift_top10": "lift in the top 10%",
          "lift_top30": "lift in the top 30%"}


def _state(row: pd.Series) -> str:
    if row["low"] > 0:
        return "model ahead"
    if row["high"] < 0:
        return "rule ahead"
    return "no clear difference"


def verdict_table(rows_resampled: pd.DataFrame, months_resampled: pd.DataFrame) -> pd.DataFrame:
    out = []
    for rule in RULES:
        for measure, label in LABELS.items():
            pick = lambda t: t[(t["compared_with"] == rule) & (t["measure"] == measure)].iloc[0]  # noqa: E731
            out.append({"rule": rule, "question": label, "difference": pick(rows_resampled)["difference"],
                        "rows resampled": _state(pick(rows_resampled)), "whole months resampled": _state(pick(months_resampled))})
    return pd.DataFrame(out)


def equal_month_summary(rows: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    """Each month counts once. Also returns the largest month's weight inside the pooled within-month AUC."""
    per_month: dict[str, dict] = {}
    pairs = {}
    for month, part in rows.groupby("period"):
        y = part["won"].to_numpy()
        pairs[month] = y.sum() * (len(y) - y.sum())
        per_month[month] = {m: auc(y, part[f"score_{m}"].to_numpy()) for m in ("model_monthly", "logistic_monthly", *RULES)}
    table = pd.DataFrame(per_month).T.dropna()
    summary = pd.DataFrame(
        [{"method": m, "mean_of_monthly_auc": table[m].mean(),
          # comparing the chosen model with itself is not a result
          "months_chosen_model_ahead": "n/a" if m == "model_monthly" else int((table["model_monthly"] > table[m]).sum()),
          "months": len(table)} for m in table.columns]
    )
    return summary, float(max(pairs.values()) / sum(pairs.values()))
