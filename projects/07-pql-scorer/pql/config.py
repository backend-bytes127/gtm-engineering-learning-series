"""Every choice that affects a result lives here, fixed before the test set is opened."""

from __future__ import annotations

from dataclasses import dataclass

MINUTE_MS = 60_000
DAY_MS = 86_400_000


@dataclass(frozen=True)
class CohortConfig:
    """Who is scored, when, and what counts as success."""

    cutoff_minutes: int = 30  # prediction time = first event + this
    horizon_days: int = 7  # label = a purchase after the cut-off and within this many days of it
    burn_in_days: int = 14  # visitors first seen this early may be returning visitors, so they are dropped
    session_gap_minutes: int = 30
    max_window_events: int = 100  # more events than this before the cut-off is treated as automation

    @property
    def cutoff_ms(self) -> int:
        return self.cutoff_minutes * MINUTE_MS

    @property
    def horizon_ms(self) -> int:
        return self.horizon_days * DAY_MS


@dataclass(frozen=True)
class SplitConfig:
    """Calendar split on the day a visitor is first seen (UTC)."""

    validation_start: str = "2015-07-20"
    test_start: str = "2015-08-15"


@dataclass(frozen=True)
class Tier:
    name: str
    daily_capacity: int
    action: str


# Capacities are ASSUMPTIONS about a team, not facts about the shop in the data.
TIERS: tuple[Tier, ...] = (
    Tier("A_assist", 50, "high-touch: proactive chat or a human-assisted offer"),
    Tier("B_nudge", 500, "automated: triggered on-site message or retargeting audience"),
)
DEFAULT_TIER = Tier("C_none", 0, "no extra action; normal lifecycle only")

SENSITIVITY_CUTOFFS_MINUTES: tuple[int, ...] = (5, 30, 1440)
CAPACITY_FRACTIONS: tuple[float, ...] = (0.005, 0.01, 0.05, 0.10)
BOOTSTRAP_REPS = 300
SEED = 7
