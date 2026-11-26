"""Two leak tests: features that see past the cut-off, and a vendor metric built from the outcome."""

from __future__ import annotations

import numpy as np
import pandas as pd

from pql import models
from pql.cohort import Cohort
from pql.config import CohortConfig
from pql.evaluate import ranking_metrics
from pql.features import build_features

UCI_MONTH_ORDER = ["Feb", "Mar", "May", "June", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
UCI_TRAIN_MONTHS = UCI_MONTH_ORDER[:7]
UCI_NUMERIC = [
    "Administrative", "Administrative_Duration", "Informational", "Informational_Duration", "ProductRelated",
    "ProductRelated_Duration", "BounceRates", "ExitRates", "PageValues", "SpecialDay",
]
UCI_CONTEXT = ["SpecialDay", "OperatingSystems", "Browser", "Region", "TrafficType", "VisitorType", "Weekend"]


def whole_history_features(events: pd.DataFrame, cohort: Cohort, config: CohortConfig) -> pd.DataFrame:
    """DELIBERATELY WRONG: view and cart events from the whole label window, as a careless GROUP BY would use.

    Transaction rows are removed, so the leak is the subtle kind: no feature mentions a purchase.
    """
    visitors = cohort.visitors
    scoped = events[events["visitorid"].isin(visitors.index) & (events["event"] != "transaction")]
    end = scoped["visitorid"].map(visitors["cutoff_ts"]) + config.horizon_ms
    late_visitors = visitors.assign(cutoff_ts=visitors["cutoff_ts"] + config.horizon_ms)
    return build_features(scoped[scoped["timestamp"] <= end], late_visitors, config)


def window_leak_test(honest: pd.DataFrame, leaked: pd.DataFrame, labels: pd.Series, split: dict[str, pd.Index]) -> list[dict]:
    rows = []
    for name, frame in (("features up to the cut-off", honest), ("features from the whole label window (LEAK)", leaked)):
        model = models.fit_logistic(frame.loc[split["train"]], labels.loc[split["train"]])
        scores = models.probabilities(model, frame.loc[split["validation"]])
        rows.append({"features": name, **ranking_metrics(labels.loc[split["validation"]].to_numpy(), scores)})
    return rows


def _uci_matrix(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    picked = frame[columns].copy()
    for column in picked.columns:
        if not pd.api.types.is_numeric_dtype(picked[column]) or pd.api.types.is_bool_dtype(picked[column]):
            picked[column] = pd.Categorical(picked[column]).codes
    return picked.astype(np.float64)


def check_uci_schema(frame: pd.DataFrame) -> None:
    needed = set(UCI_NUMERIC + UCI_CONTEXT + ["Month", "Revenue"])
    missing = sorted(needed - set(frame.columns))
    if missing:
        raise ValueError(f"UCI file is missing columns: {', '.join(missing)}")
    unknown = sorted(set(frame["Month"]) - set(UCI_MONTH_ORDER))
    if unknown:
        raise ValueError(f"unexpected Month values: {', '.join(map(str, unknown))}")


def uci_page_value_test(frame: pd.DataFrame) -> dict:
    """Train on Feb-Sep, test on Oct-Dec (the file has no year or date, so calendar order is assumed)."""
    check_uci_schema(frame)
    labels = frame["Revenue"].astype(int)
    train = frame["Month"].isin(UCI_TRAIN_MONTHS)
    positive = frame["PageValues"] > 0
    without = [c for c in UCI_NUMERIC if c != "PageValues"] + [c for c in UCI_CONTEXT if c not in UCI_NUMERIC]
    variants = {
        "all columns, PageValues included": [*without, "PageValues"],
        "PageValues alone": ["PageValues"],
        "without PageValues (still end-of-session totals)": without,
        "context only (plausibly known at session start)": UCI_CONTEXT,
    }
    rows = []
    for name, columns in variants.items():
        matrix = _uci_matrix(frame, columns)
        model = models.fit_boosting(matrix[train], labels[train])
        scores = models.probabilities(model, matrix[~train])
        rows.append({"variant": name, **ranking_metrics(labels[~train].to_numpy(), scores)})
    return {
        "sessions": len(frame),
        "buy_rate": float(labels.mean()),
        "train_sessions": int(train.sum()),
        "test_sessions": int((~train).sum()),
        "test_buy_rate": float(labels[~train].mean()),
        "pv_positive_among_buyers": float(positive[labels == 1].mean()),
        "pv_positive_among_non_buyers": float(positive[labels == 0].mean()),
        "buy_rate_pv_positive": float(labels[positive].mean()),
        "buy_rate_pv_zero": float(labels[~positive].mean()),
        "variants": rows,
    }
