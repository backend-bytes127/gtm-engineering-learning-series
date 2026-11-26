"""Rolling-origin backtest. A model scored at origin t is trained only on snapshots whose label closed by t."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

from .config import CAPACITY, COOLDOWN_DAYS, HORIZON_DAYS, BacktestPlan
from .features import History, labelled_snapshot
from .metrics import at_capacity, probability_metrics
from .models import CANDIDATES, FACTORIES, Model


def date_range(start: date, end: date, step_days: int) -> list[date]:
    return [start + timedelta(days=i) for i in range(0, (end - start).days + 1, step_days)]


def training_dates(plan: BacktestPlan, origin: date, horizon: int = HORIZON_DAYS) -> list[date]:
    """Only snapshots s with s + horizon <= origin: their outcome was fully known on the scoring day."""
    last = origin - timedelta(days=horizon)
    return date_range(plan.first_train, last, plan.train_step_days) if last >= plan.first_train else []


@dataclass
class Snapshots:
    history: History
    cache: dict[date, pd.DataFrame]

    def get(self, day: date) -> pd.DataFrame:
        if day not in self.cache:
            self.cache[day] = labelled_snapshot(self.history, day)
        return self.cache[day]

    def training(self, plan: BacktestPlan, origin: date) -> pd.DataFrame:
        dates = training_dates(plan, origin)
        if not dates:
            raise ValueError(f"no training snapshot has a closed label by {origin}")
        return pd.concat([self.get(d) for d in dates], ignore_index=True)


def fit(name: str, train: pd.DataFrame) -> Model:
    return FACTORIES[name]().fit(train)


def score_period(snapshots: Snapshots, plan: BacktestPlan, origins: list[date]) -> pd.DataFrame:
    """One row per origin, account and model: probability `p`, ranking `score`, outcome and trailing value."""
    parts = []
    for origin in origins:
        train, test = snapshots.training(plan, origin), snapshots.get(origin)
        for name in FACTORIES:
            model = fit(name, train)
            parts.append(test[["customer_id", "as_of", "churned", "net_180", "recency_days", "purchase_days_180"]]
                         .assign(model=name, p=model.predict(test), score=model.score(test)))
    return pd.concat(parts, ignore_index=True)


def weekly(scored: pd.DataFrame, capacity: int = CAPACITY) -> pd.DataFrame:
    """Capacity metrics per origin, for two policies: rank by risk, or by risk x trailing revenue."""
    rows = []
    for (name, origin), part in scored.groupby(["model", "as_of"]):
        y, value = part["churned"].to_numpy(), part["net_180"].to_numpy()
        by_risk = at_capacity(y, part["score"].to_numpy(), value, capacity)
        by_value = at_capacity(y, part["p"].to_numpy() * value, value, capacity)
        rows.append({"model": name, "as_of": origin, "accounts": len(part), "base_rate": float(y.mean()), **by_risk,
                     **{f"ev_{k}": v for k, v in by_value.items()}})
    return pd.DataFrame(rows)


def summarise(scored: pd.DataFrame, capacity: int = CAPACITY) -> pd.DataFrame:
    """Pooled probability metrics plus capacity metrics averaged over weeks."""
    means = weekly(scored, capacity).groupby("model").mean(numeric_only=True)
    rows = []
    for name, part in scored.groupby("model"):
        pooled = probability_metrics(part["churned"].to_numpy(), part["p"].to_numpy(), part["score"].to_numpy())
        rows.append({"model": name, **pooled, **means.loc[name].drop("accounts").to_dict()})
    table = pd.DataFrame(rows).set_index("model")
    return table.loc[[m for m in FACTORIES if m in table.index]].reset_index()


def choose_model(development: pd.DataFrame) -> str:
    """Declared rule: the fitted model with the lowest development log loss."""
    table = summarise(development).set_index("model")
    return str(table.loc[list(CANDIDATES), "log_loss"].idxmin())


def top_with_cooldown(scored: pd.DataFrame, priority: np.ndarray, capacity: int = CAPACITY,
                      cooldown: int = COOLDOWN_DAYS) -> pd.DataFrame:
    """Replay the weekly queue: take the top accounts that were not alerted within the cooldown."""
    frame = scored.assign(priority=priority)
    last_alert: dict[int, pd.Timestamp] = {}
    picked = []
    for origin, part in frame.groupby("as_of"):
        resting = [c for c, day in last_alert.items() if (origin - day).days < cooldown]
        chosen = part[~part["customer_id"].isin(resting)].sort_values(["priority", "customer_id"],
                                                                      ascending=[False, True]).head(capacity)
        last_alert.update({c: origin for c in chosen["customer_id"]})
        picked.append(chosen)
    return pd.concat(picked, ignore_index=True)
