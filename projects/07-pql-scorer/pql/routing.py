"""Turn probabilities into actions under daily capacity. Thresholds come from validation only."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from pql.config import DAY_MS, DEFAULT_TIER, Tier
from pql.evaluate import wilson_interval


@dataclass(frozen=True)
class Policy:
    tiers: tuple[Tier, ...]
    thresholds: tuple[float, ...]  # minimum score for each tier, highest tier first
    score_version: str


def visitors_per_day(first_ts: pd.Series) -> float:
    days = (first_ts // DAY_MS).nunique()
    return len(first_ts) / days if days else 0.0


def fit_thresholds(scores: np.ndarray, per_day: float, tiers: Sequence[Tier], score_version: str) -> Policy:
    """Pick score cut-offs so each tier's expected daily volume matches its capacity on validation."""
    if per_day <= 0 or scores.size == 0:
        raise ValueError("need validation scores and a positive daily volume to set thresholds")
    cumulative = np.cumsum([t.daily_capacity for t in tiers])
    thresholds = tuple(float(np.quantile(scores, max(0.0, 1 - total / per_day))) for total in cumulative)
    return Policy(tiers=tuple(tiers), thresholds=thresholds, score_version=score_version)


def route(scores: np.ndarray, decided_at_ms: np.ndarray, policy: Policy) -> pd.DataFrame:
    """Decide in time order with a hard daily cap. A full tier sends the visitor to the next one down.

    First come, first served: a later, better visitor cannot displace an earlier one,
    because a live system does not know who will arrive later in the day.
    """
    if not np.all(np.isfinite(scores)):
        raise ValueError("scores must be finite; a missing score must not be routed silently")
    tier_names = np.full(scores.size, DEFAULT_TIER.name, dtype=object)
    overflow = np.zeros(scores.size, dtype=bool)
    used: dict[tuple[int, str], int] = {}
    lowest = policy.thresholds[-1]
    for position in np.argsort(decided_at_ms, kind="stable"):
        score = scores[position]
        if score < lowest:
            continue
        day = int(decided_at_ms[position] // DAY_MS)
        for tier, threshold in zip(policy.tiers, policy.thresholds):
            if score < threshold:
                continue
            if used.get((day, tier.name), 0) < tier.daily_capacity:
                used[(day, tier.name)] = used.get((day, tier.name), 0) + 1
                tier_names[position] = tier.name
                break
            overflow[position] = True
    return pd.DataFrame({"tier": tier_names, "hit_capacity": overflow})


def tier_summary(decisions: pd.DataFrame, labels: np.ndarray, decided_at_ms: np.ndarray, policy: Policy) -> list[dict[str, float | str]]:
    days = decided_at_ms // DAY_MS
    n_days = max(1, np.unique(days).size)
    total_buyers = labels.sum()
    rows: list[dict[str, float | str]] = []
    for name in [t.name for t in policy.tiers] + [DEFAULT_TIER.name]:
        mask = (decisions["tier"] == name).to_numpy()
        count, hits = int(mask.sum()), int(labels[mask].sum())
        low, high = wilson_interval(hits, count)
        rows.append(
            {
                "tier": name,
                "visitors": count,
                "per_day": count / n_days,
                "buyers": hits,
                "buy_rate": hits / count if count else 0.0,
                "buy_rate_low": low,
                "buy_rate_high": high,
                "share_of_buyers": hits / total_buyers if total_buyers else 0.0,
            }
        )
    return rows


class TaskLedger:
    """Remembers which (visitor, score version) already produced a task, so a replay creates none."""

    def __init__(self) -> None:
        self._seen: set[tuple[str, str]] = set()

    def tasks_for(self, visitor_keys: Sequence[str], decisions: pd.DataFrame, policy: Policy) -> list[dict[str, str]]:
        """Dry-run payloads. Nothing is sent anywhere."""
        actions = {t.name: t.action for t in policy.tiers}
        tasks = []
        for key, tier in zip(visitor_keys, decisions["tier"]):
            identity = (key, policy.score_version)
            if tier not in actions or identity in self._seen:
                continue
            self._seen.add(identity)
            tasks.append({"idempotency_key": f"{key}:{policy.score_version}", "tier": tier, "action": actions[tier]})
        return tasks
