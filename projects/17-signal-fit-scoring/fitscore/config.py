"""Paths, split boundaries and the field policy. Weights live in config/scoring.json."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
UCI_CSV = RAW / "uci" / "bank-additional-full.csv"
DEFAULT_CONFIG = ROOT / "config" / "scoring.json"
REPORTS = ROOT / "reports"

TARGET = "y"
FIRST_YEAR = 2008  # the UCI notes say the file is ordered by date and starts in May 2008
VALIDATION_START = "2008-10"  # months from here to TEST_START choose the model
TEST_START = "2009-05"  # months from here on are never used to choose anything
SEED = 17

# Field groups known before the first call of a campaign.
CATEGORICAL_GROUPS: dict[str, tuple[str, ...]] = {
    "profile": ("job", "education"),
    "finance": ("default", "housing", "loan"),
    "history": ("poutcome",),
}
GROUPS = tuple(CATEGORICAL_GROUPS)

# Fields kept out of the score, with the reason. The ablation shows what each would have added.
EXCLUDED: dict[str, str] = {
    "duration": "leak: call length exists only after the call",
    "campaign": "leak: total calls in this campaign, including the last one; calling usually stops after the outcome",
    "month": "timing of the last call, which is only known to be the last one afterwards",
    "day_of_week": "same as month",
    "contact": "channel of the last call; not clearly fixed before calling starts",
    "age": "policy: age is a protected characteristic",
    "marital": "policy: marital status is a protected characteristic in many places",
    "emp.var.rate": "market-wide value: same for everyone that day, acts as a clock, publication lag unknown",
    "cons.price.idx": "as above",
    "cons.conf.idx": "as above",
    "euribor3m": "as above",
    "nr.employed": "as above",
}


@dataclass(frozen=True)
class Tier:
    name: str
    top_share: float
    action: str


@dataclass(frozen=True)
class ScoringConfig:
    recency_half_life_days: float
    previous_cap: int
    points_rules: dict
    tiers: tuple[Tier, ...]
    exploration_share: float


def load_config(path: Path = DEFAULT_CONFIG) -> ScoringConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    tiers = tuple(Tier(**t) for t in raw["tiers"])
    shares = [t.top_share for t in tiers]
    if not shares or shares != sorted(set(shares)) or shares[0] <= 0 or shares[-1] != 1.0:
        raise ValueError("tier top_share values must be positive, strictly increasing and end at 1.0")
    if raw["recency_half_life_days"] <= 0 or raw["previous_cap"] < 1:
        raise ValueError("recency_half_life_days must be > 0 and previous_cap >= 1")
    if not 0 <= raw["exploration_share"] < 1:
        raise ValueError("exploration_share must be in [0, 1)")
    return ScoringConfig(
        float(raw["recency_half_life_days"]), int(raw["previous_cap"]), raw["points_rules"], tiers, float(raw["exploration_share"])
    )
