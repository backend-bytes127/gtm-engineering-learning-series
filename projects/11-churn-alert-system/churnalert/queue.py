"""This week's customer-success queue: ranked accounts with plain reasons. Written to local files; nothing is sent."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from .config import CAPACITY, COOLDOWN_DAYS, QUEUE_POLICIES, QUEUE_POLICY
from .models import Model

PLAYBOOK = {
    "OVERDUE": "Call this week: ask whether the usual reorder moved, stalled, or went to another supplier.",
    "FEWER_ORDERS": "Account review: compare the last two quarters of orders and agree the next reorder date.",
    "SPEND_DOWN": "Check basket mix: which lines stopped, and was it stock, price or demand?",
    "RETURNS_UP": "Open a service review first: resolve returns or credits before any sales ask.",
    "THIN_HISTORY": "Early-life follow-up: confirm the second order landed well and set a reorder reminder.",
    "SCORE_ONLY": "Light check-in; no single behaviour stands out, so do not claim a reason to the customer.",
}
HISTORY_COLUMNS = ["as_of", "customer_id"]


def reasons(row: pd.Series) -> list[tuple[str, str]]:
    """Observable facts about the account, in priority order. They describe behaviour; they do not prove a cause."""
    found = []
    if row["return_share_180"] >= 0.2:
        found.append(("RETURNS_UP", f"returns equal {row['return_share_180']:.0%} of 180-day gross sales"))
    if row["overdue_ratio"] >= 2 and row["recency_days"] >= 21:
        found.append(("OVERDUE", f"silent {row['recency_days']:.0f} days; usual gap {row['median_gap_days']:.0f} day(s)"))
    if row["purchase_days_prev90"] >= 2 and row["purchase_days_90"] <= row["purchase_days_prev90"] / 2:
        found.append(("FEWER_ORDERS",
                      f"order days fell from {row['purchase_days_prev90']:.0f} to {row['purchase_days_90']:.0f} (90 days)"))
    if row["net_prev90"] > 0 and row["net_90"] < row["net_prev90"] / 2:
        found.append(("SPEND_DOWN", f"net spend fell {1 - row['net_90'] / row['net_prev90']:.0%} against the previous 90 days"))
    if row["purchase_days_180"] == 2:
        found.append(("THIN_HISTORY", "only 2 order days in 180 days"))
    return found or [("SCORE_ONLY", "no single rule fired; ranked on the model score and the queue policy")]


def read_history(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=HISTORY_COLUMNS)
    frame = pd.read_csv(path)
    if list(frame.columns) != HISTORY_COLUMNS:
        raise ValueError(f"{path.name} must have columns {HISTORY_COLUMNS}")
    return frame.assign(as_of=pd.to_datetime(frame["as_of"], format="%Y-%m-%d"))


def resting_accounts(history: pd.DataFrame, as_of: date, cooldown: int = COOLDOWN_DAYS) -> set[int]:
    """Accounts alerted on an EARLIER day inside the cooldown. Same-day entries are ignored, so a rerun is stable."""
    if history.empty:
        return set()
    age = (pd.Timestamp(as_of) - pd.to_datetime(history["as_of"])).dt.days
    return set(history.loc[(age > 0) & (age < cooldown), "customer_id"].astype(int))


def build_queue(frame: pd.DataFrame, model: Model, resting: set[int], capacity: int = CAPACITY,
                policy: str = QUEUE_POLICY) -> pd.DataFrame:
    """Rank by churn score ("risk", the default) or by score x trailing 180-day net revenue ("value").

    The product is a priority number, not a forecast of money lost.
    """
    if policy not in QUEUE_POLICIES:
        raise ValueError(f"unknown ranking policy {policy!r}; use one of {QUEUE_POLICIES}")
    rank_by = {"risk": "p_churn", "value": "value_at_risk_gbp"}[policy]
    scored = frame.assign(p_churn=model.predict(frame))
    scored = scored.assign(value_at_risk_gbp=scored["p_churn"] * scored["net_180"])
    open_accounts = scored[~scored["customer_id"].isin(resting)]
    top = open_accounts.sort_values([rank_by, "customer_id"], ascending=[False, True]).head(capacity)
    found = [reasons(row) for _, row in top.iterrows()]
    return pd.DataFrame({
        "rank": range(1, len(top) + 1),
        "customer_id": top["customer_id"].to_numpy().astype(int),
        "churn_score": top["p_churn"].to_numpy().round(3),
        "net_180d_gbp": top["net_180"].to_numpy().round(2),
        "value_at_risk_gbp": top["value_at_risk_gbp"].to_numpy().round(2),
        "primary_reason": [f[0][0] for f in found],
        "all_reasons": ["; ".join(text for _, text in f) for f in found],
        "suggested_action": [PLAYBOOK[f[0][0]] for f in found],
        "delivery_status": "not sent (local file only)",
    })


def write_queue(queue: pd.DataFrame, as_of: date, directory: Path) -> Path:
    """Write the queue and record the alerts. Rerunning the same day replaces that day's records."""
    directory.mkdir(parents=True, exist_ok=True)
    history_path = directory / "alert_history.csv"
    old = read_history(history_path)
    kept = old[pd.to_datetime(old["as_of"]) != pd.Timestamp(as_of)] if len(old) else old
    new = pd.DataFrame({"as_of": pd.Timestamp(as_of), "customer_id": queue["customer_id"]})
    combined = pd.concat([kept, new], ignore_index=True) if len(kept) else new
    combined.assign(as_of=pd.to_datetime(combined["as_of"]).dt.strftime("%Y-%m-%d")).to_csv(history_path, index=False)
    target = directory / f"alert_queue_{as_of.isoformat()}.csv"
    queue.to_csv(target, index=False)
    return target


def aggregate_queue(queue: pd.DataFrame) -> pd.DataFrame:
    """Aggregates only, safe to commit: no account identifiers."""
    table = queue.groupby("primary_reason").agg(accounts=("rank", "size"), mean_score=("churn_score", "mean"),
                                                 net_180d_gbp=("net_180d_gbp", "sum"),
                                                 value_at_risk_gbp=("value_at_risk_gbp", "sum")).reset_index()
    table = table.sort_values(["accounts", "primary_reason"], ascending=[False, True])
    return table.assign(suggested_action=table["primary_reason"].map(PLAYBOOK))
