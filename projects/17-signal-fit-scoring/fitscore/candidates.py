"""Checks on the other candidate datasets. Each runs only if its files were downloaded.

maven: fictional B2B pipeline. Is there any signal at all?
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import OneHotEncoder

from . import config
from .bootstrap import interval, month_stratified_bootstrap
from .metrics import auc, lift_at


def _logistic_scores(train: pd.DataFrame, test: pd.DataFrame, fields: list[str], outcome: str, strength: float = 0.3) -> np.ndarray:
    encoder = OneHotEncoder(handle_unknown="infrequent_if_exist", min_frequency=20)
    x_train = encoder.fit_transform(train[fields].astype(str))
    model = LogisticRegression(C=strength, max_iter=3000).fit(x_train, train[outcome])
    return model.predict_proba(encoder.transform(test[fields].astype(str)))[:, 1]


def _score_with_interval(y: np.ndarray, scores: np.ndarray, reps: int) -> dict:
    groups = np.zeros(len(y))

    def statistic(rows: np.ndarray, labels: np.ndarray, indices: list) -> np.ndarray:
        return np.array([auc(y[rows], scores[rows]), lift_at(y[rows], scores[rows], labels, 0.3, indices)])

    low, high = interval(month_stratified_bootstrap(groups, statistic, reps, config.SEED))
    point = statistic(np.arange(len(y)), groups, [np.arange(len(y))])
    return {"auc": point[0], "auc_low": low[0], "auc_high": high[0], "lift_top30": point[1], "lift_low": low[1], "lift_high": high[1]}


def maven_check(folder: Path, reps: int, cutoff: str = "2017-07-01") -> dict:
    pipeline = pd.read_csv(folder / "sales_pipeline.csv")
    teams = pd.read_csv(folder / "sales_teams.csv")
    accounts = pd.read_csv(folder / "accounts.csv")
    closed = pipeline[pipeline["deal_stage"].isin(["Won", "Lost"])]
    closed = closed.merge(accounts, on="account", how="left").merge(teams, on="sales_agent", how="left")
    closed = closed.assign(
        won=(closed["deal_stage"] == "Won").astype(int),
        revenue_band=pd.qcut(closed["revenue"], 5, labels=False, duplicates="drop"),
    )
    train = closed[(closed["engage_date"] < cutoff) & (closed["close_date"] < cutoff)]
    test = closed[closed["engage_date"] >= cutoff]
    fields = ["sales_agent", "manager", "regional_office", "product", "sector", "office_location", "revenue_band"]
    scores = _logistic_scores(train, test, fields, "won")
    return {
        "pipeline_rows": len(pipeline), "open_rows": int((~pipeline["deal_stage"].isin(["Won", "Lost"])).sum()),
        "train_rows": len(train), "test_rows": len(test), "test_win_rate": float(test["won"].mean()),
        **_score_with_interval(test["won"].to_numpy(), scores, reps),
    }


def run_candidates(raw: Path, reps: int) -> dict:
    results: dict = {}
    if (raw / "maven" / "sales_pipeline.csv").exists():
        results["maven"] = maven_check(raw / "maven", reps)
    return results
