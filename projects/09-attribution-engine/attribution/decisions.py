"""Business layer: what can a budget owner do with a spread of attribution answers?

Spend figures are ASSUMPTIONS invented for the synthetic world. They are not benchmarks.
"""
from __future__ import annotations

import pandas as pd

ASSUMED_SPEND_EUR = {
    "paid_social": 60_000,
    "display": 40_000,
    "nonbrand_search": 80_000,
    "webinar": 25_000,
    "retargeting": 30_000,
    "email": 8_000,
    "brand_search": 35_000,
}
STABLE_RATIO = 1.25  # highest credit within 25% of the lowest counts as "the methods agree"
# The rate game is left out of the range because it ignores how many journeys a channel is in.
CORE_METHODS = ["first_touch", "last_touch", "linear", "time_decay", "u_shaped", "markov", "shapley_count"]


def decision_table(credit: pd.DataFrame, spend: dict[str, float] = ASSUMED_SPEND_EUR) -> pd.DataFrame:
    """One row per paid channel, ordered by the spend whose measured value depends most on the method."""
    paid = [c for c in spend if c in credit.index]
    if not paid:
        raise ValueError("no channel in the credit table has a spend figure")
    if any(spend[c] <= 0 for c in paid):
        raise ValueError("spend must be positive")
    values = credit.loc[paid, CORE_METHODS]
    low, high = values.min(axis=1), values.max(axis=1)
    cost = pd.Series({c: float(spend[c]) for c in paid})
    ranks = values.div(cost, axis=0).rank(ascending=False, method="min")
    table = pd.DataFrame(
        {
            "assumed_spend_eur": cost,
            "credit_low": low,
            "credit_high": high,
            "cpa_low_eur": cost / high.where(high > 0),
            "cpa_high_eur": cost / low.where(low > 0),
            "best_efficiency_rank": ranks.min(axis=1).astype(int),
            "worst_efficiency_rank": ranks.max(axis=1).astype(int),
            "spend_in_dispute_eur": cost * (1 - low / high.where(high > 0)).fillna(0.0),
        }
    )
    agree = (high <= STABLE_RATIO * low) & (low > 0)
    table["verdict"] = agree.map({True: "methods agree (still not proof of effect)", False: "depends on the method: test first"})
    return table.sort_values("spend_in_dispute_eur", ascending=False)


def causal_cost(truth_leave_one_out: pd.Series, spend: dict[str, float] = ASSUMED_SPEND_EUR) -> pd.Series:
    """Synthetic world only: assumed spend per conversion that would be lost without the channel."""
    lost = truth_leave_one_out.reindex(list(spend)).astype(float)
    return pd.Series(spend, dtype=float) / lost.where(lost > 0)
