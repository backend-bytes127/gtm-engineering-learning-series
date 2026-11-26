"""Design the A/B test that would show whether acting on the score CAUSES more purchases.

A good score only says who is likely to buy. Many of them would buy anyway.
"""

from __future__ import annotations

import math
from statistics import NormalDist

import numpy as np

_NORMAL = NormalDist()


def sample_size(baseline: float, treated: float, alpha: float = 0.05, power: float = 0.8, treated_share: float = 0.5) -> tuple[int, int]:
    """(treated n, control n) for a two-sided two-proportion z-test, normal approximation."""
    if not (0 < baseline < 1 and 0 < treated < 1) or baseline == treated:
        raise ValueError("rates must be between 0 and 1 and must differ")
    if not 0 < treated_share < 1:
        raise ValueError("treated_share must be between 0 and 1")
    ratio = treated_share / (1 - treated_share)  # treated per control
    pooled = (baseline + ratio * treated) / (1 + ratio)
    z_alpha, z_power = _NORMAL.inv_cdf(1 - alpha / 2), _NORMAL.inv_cdf(power)
    null_sd = math.sqrt(pooled * (1 - pooled) * (1 + 1 / ratio))
    alt_sd = math.sqrt(baseline * (1 - baseline) + treated * (1 - treated) / ratio)
    control = math.ceil(((z_alpha * null_sd + z_power * alt_sd) / (treated - baseline)) ** 2)
    return math.ceil(control * ratio), control


def simulated_power(baseline: float, treated: float, n_treated: int, n_control: int, reps: int, seed: int, alpha: float = 0.05) -> float:
    """Check the formula: simulate the test many times and count how often it detects the effect."""
    rng = np.random.default_rng(seed)
    hits_t = rng.binomial(n_treated, treated, reps)
    hits_c = rng.binomial(n_control, baseline, reps)
    pooled = (hits_t + hits_c) / (n_treated + n_control)
    se = np.sqrt(pooled * (1 - pooled) * (1 / n_treated + 1 / n_control))
    z = np.divide(hits_t / n_treated - hits_c / n_control, se, out=np.zeros(reps), where=se > 0)
    return float(np.mean(np.abs(z) > _NORMAL.inv_cdf(1 - alpha / 2)))


def design_table(baseline: float, per_day: float, lifts: tuple[float, ...], shares: tuple[float, ...], horizon_days: int) -> list[dict]:
    """Sample size and calendar time for each relative lift and allocation."""
    if per_day <= 0:
        raise ValueError("per_day must be positive")
    rows = []
    for share in shares:
        for lift in lifts:
            treated_n, control_n = sample_size(baseline, baseline * (1 + lift), treated_share=share)
            total = treated_n + control_n
            enrol = math.ceil(total / per_day)
            rows.append(
                {
                    "relative_lift": lift,
                    "treated_share": share,
                    "treated_rate": baseline * (1 + lift),
                    "n_treated": treated_n,
                    "n_control": control_n,
                    "enrol_days": enrol,
                    "days_to_readout": enrol + horizon_days,
                }
            )
    return rows


def sample_ratio_p_value(n_treated: int, n_control: int, treated_share: float) -> float:
    """Sample-ratio mismatch check (chi-square, 1 degree of freedom). A tiny p means assignment is broken."""
    total = n_treated + n_control
    if total == 0:
        raise ValueError("no visitors assigned")
    expected_t, expected_c = total * treated_share, total * (1 - treated_share)
    chi = (n_treated - expected_t) ** 2 / expected_t + (n_control - expected_c) ** 2 / expected_c
    return math.erfc(math.sqrt(chi / 2))


def break_even_lift(cost_per_action: float, margin_per_order: float, baseline: float) -> float:
    """Relative lift needed to pay for the action, if its only effect is extra orders."""
    if margin_per_order <= 0 or baseline <= 0:
        raise ValueError("margin and baseline must be positive")
    return cost_per_action / margin_per_order / baseline
