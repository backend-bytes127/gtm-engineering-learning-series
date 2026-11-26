"""Run every stage and collect the results the report prints."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from . import backtest, features, retention, sqldb
from .config import BOOTSTRAP_REPS, CAPACITY, GAP_EVIDENCE_END, PLAN, QUEUE_AS_OF, BacktestPlan
from .metrics import calibration_table, expected_calibration_error
from .models import BASELINE
from .queue import build_queue, read_history, resting_accounts, write_queue
from .uncertainty import bootstrap_models, segment_table


@dataclass(frozen=True)
class RetentionResults:
    buckets: pd.DataFrame
    checks: pd.DataFrame
    waterfall: pd.DataFrame
    cohorts: pd.DataFrame
    intervals: dict[str, tuple[float, float]]
    sensitivity: pd.DataFrame
    trap: pd.DataFrame
    triangle: pd.DataFrame


@dataclass(frozen=True)
class RiskResults:
    chosen: str
    dev: pd.DataFrame
    test: pd.DataFrame
    dev_scored: pd.DataFrame
    test_scored: pd.DataFrame
    weeks: pd.DataFrame
    bootstrap: pd.DataFrame
    bootstrap_overdue: pd.DataFrame
    bootstrap_revenue: pd.DataFrame  # against base_rate: random order by risk, revenue-only order by value
    segments: pd.DataFrame
    calibration: dict[str, pd.DataFrame]
    ece: dict[str, float]
    cooldown: pd.DataFrame
    gaps: dict[str, float]


@dataclass(frozen=True)
class QueueResults:
    as_of: date
    queue: pd.DataFrame
    path: Path
    coverage: dict[str, float]
    training_rows: int


def run_retention(raw: pd.DataFrame, con: sqlite3.Connection, reps: int = BOOTSTRAP_REPS, **build_args: object) -> RetentionResults:
    checks = sqldb.run_checks(con)
    buckets = sqldb.query(con, "SELECT bucket, COUNT(*) AS rows, SUM(pence) AS pence FROM lines GROUP BY bucket ORDER BY rows DESC")
    return RetentionResults(
        buckets, checks, retention.waterfall(con), retention.cohorts(con),
        retention.bootstrap_rates(retention.base_movements(con, "annual"), reps),
        retention.sensitivity(raw, con, **build_args), retention.monthly_trap(con),
        sqldb.query(con, "SELECT * FROM cohort_month ORDER BY cohort_month, month_index"))


def _cooldown_replay(scored: pd.DataFrame, names: list[str]) -> pd.DataFrame:
    """Precision and revenue captured of the weekly queue when alerted accounts rest, as in operation."""
    rows = []
    for name in names:
        part = scored[scored["model"] == name].reset_index(drop=True)
        for policy, priority in (("risk", part["score"]), ("risk x value", part["p"] * part["net_180"])):
            picked = backtest.top_with_cooldown(part, priority.to_numpy())
            first = picked.drop_duplicates("customer_id")
            rows.append({"model": name, "policy": policy, "alerts": len(picked), "unique_accounts": len(first),
                         "alert_precision": picked["churned"].mean(), "unique_precision": first["churned"].mean(),
                         "churned_value_flagged_gbp": float((first["net_180"] * first["churned"]).sum())})
    return pd.DataFrame(rows)


def run_risk(snapshots: backtest.Snapshots, plan: BacktestPlan = PLAN, reps: int = BOOTSTRAP_REPS) -> RiskResults:
    def score(start: date, end: date) -> pd.DataFrame:
        return backtest.score_period(snapshots, plan, backtest.date_range(start, end, plan.eval_step_days))

    dev_scored = score(plan.dev_start, plan.dev_end)
    chosen = backtest.choose_model(dev_scored)  # decided before any test row is scored
    test_scored = score(plan.test_start, plan.test_end)
    tables = {}
    for title, frame in (("Development weeks", dev_scored), ("Test weeks", test_scored)):
        part = frame[frame["model"] == chosen]
        tables[title] = calibration_table(part["churned"].to_numpy(), part["p"].to_numpy())
    return RiskResults(
        chosen, backtest.summarise(dev_scored), backtest.summarise(test_scored), dev_scored, test_scored,
        backtest.weekly(test_scored), bootstrap_models(test_scored, chosen, BASELINE, reps=reps),
        bootstrap_models(test_scored, chosen, "overdue_rule", reps=reps),
        bootstrap_models(test_scored, chosen, "base_rate", reps=reps),
        segment_table(test_scored, chosen, BASELINE), tables,
        {k: expected_calibration_error(v) for k, v in tables.items()},
        _cooldown_replay(test_scored, [chosen, BASELINE, "overdue_rule"]),
        features.gap_evidence(snapshots.history, GAP_EVIDENCE_END))


def coverage_of(history: features.History, frame: pd.DataFrame, as_of: date) -> dict[str, float]:
    """Who is NOT scored matters as much as who is."""
    cut = pd.Timestamp(as_of)
    days = history.days[(history.days["day"] < cut) & (history.days["day"] >= cut - pd.Timedelta(days=180))]
    value = days.groupby("customer_id")["net"].sum().clip(lower=0)
    return {"buyers_180": int(days.loc[days["bought"] == 1, "customer_id"].nunique()), "eligible": len(frame),
            "eligible_value_share": float(value.reindex(frame["customer_id"], fill_value=0).sum() / value.sum())}


def run_queue(snapshots: backtest.Snapshots, chosen: str, out: Path, plan: BacktestPlan = PLAN,
              as_of: date = QUEUE_AS_OF, capacity: int = CAPACITY) -> QueueResults:
    train = snapshots.training(plan, as_of)
    frame = features.snapshot_features(snapshots.history, as_of)
    resting = resting_accounts(read_history(out / "alert_history.csv"), as_of)
    queue = build_queue(frame, backtest.fit(chosen, train), resting, capacity)
    path = write_queue(queue, as_of, out)
    return QueueResults(as_of, queue, path, coverage_of(snapshots.history, frame, as_of), len(train))
