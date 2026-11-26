"""Every analysis choice in one place. They were fixed before the test period was scored."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

HORIZON_DAYS = 90  # churn = no purchase day in the next 90 days
LOOKBACK_DAYS = 180  # every feature uses this fixed window, so early and late snapshots are comparable
MIN_PURCHASE_DAYS = 2  # in the lookback: one-time buyers are an onboarding problem, not a retention one
MAX_RECENCY_DAYS = HORIZON_DAYS  # an account silent for longer has already met the churn definition
GAP_EVIDENCE_END = date(2010, 12, 1)  # the horizon was chosen from gaps before this date only
CAPACITY = 25  # ASSUMPTION: accounts a customer success team can work per week
# Default queue order. "risk" ranks by churn score (higher precision). "value" ranks by score x trailing revenue, whose test
# precision was below picking eligible accounts at random.
QUEUE_POLICIES = ("risk", "value")
QUEUE_POLICY = "risk"
COOLDOWN_DAYS = 28  # an alerted account is not alerted again for this long
SEED = 11
BOOTSTRAP_REPS = 500


@dataclass(frozen=True)
class BacktestPlan:
    first_train: date
    train_step_days: int
    dev_start: date
    dev_end: date
    test_start: date
    test_end: date
    eval_step_days: int = 7


# Development origins choose the model. Their last label closes before the first test origin.
# The last test origin is the last Monday whose 90-day label is fully observed (data ends 2011-12-09).
PLAN = BacktestPlan(first_train=date(2010, 6, 1), train_step_days=28,
                    dev_start=date(2010, 12, 6), dev_end=date(2011, 3, 7),
                    test_start=date(2011, 6, 6), test_end=date(2011, 9, 5))
QUEUE_AS_OF = date(2011, 12, 10)  # the day after the last transaction


@dataclass(frozen=True)
class Comparison:
    key: str
    label: str
    base_start: str
    base_end: str  # exclusive
    cur_start: str
    cur_end: str  # exclusive


# Same months one year apart, so the very strong gift-ware season cancels out. December 2011 is partial and unused.
COMPARISONS = (
    Comparison("annual", "Dec10-Nov11 vs Dec09-Nov10", "2009-12-01", "2010-12-01", "2010-12-01", "2011-12-01"),
    Comparison("q1", "Dec10-Feb11 vs Dec09-Feb10", "2009-12-01", "2010-03-01", "2010-12-01", "2011-03-01"),
    Comparison("q2", "Mar-May11 vs Mar-May10", "2010-03-01", "2010-06-01", "2011-03-01", "2011-06-01"),
    Comparison("q3", "Jun-Aug11 vs Jun-Aug10", "2010-06-01", "2010-09-01", "2011-06-01", "2011-09-01"),
    Comparison("q4", "Sep-Nov11 vs Sep-Nov10", "2010-09-01", "2010-12-01", "2011-09-01", "2011-12-01"),
)
LAST_FULL_MONTH = "2011-11"
