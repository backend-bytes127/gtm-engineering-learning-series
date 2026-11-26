"""Randomised holdout design: assignment, sample size, analysis and a check on the planted world.

The estimate is intention-to-treat: everyone assigned to a group is counted, whether or not the
channel ever reached them. Comparing exposed with unexposed people is not an experiment.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from statistics import NormalDist

import numpy as np

NORMAL = NormalDist()


def assign(unit_id: str, salt: str, holdout_fraction: float) -> str:
    """Stable assignment: the same unit and salt always give the same arm. Use a new salt per test."""
    if not unit_id or not salt:
        raise ValueError("unit_id and salt must not be empty")
    _check_fraction(holdout_fraction)
    digest = hashlib.sha256(f"{salt}:{unit_id}".encode()).digest()
    return "holdout" if int.from_bytes(digest[:8], "big") / 2**64 < holdout_fraction else "treatment"


def _check_fraction(fraction: float) -> None:
    if not 0 < fraction < 1:
        raise ValueError("holdout_fraction must be between 0 and 1")


def required_total(
    rate_with: float, rate_without: float, holdout_fraction: float, alpha: float = 0.05, power: float = 0.8
) -> int:
    """Total units (both arms) for a two-sided two-proportion z-test."""
    _check_fraction(holdout_fraction)
    for value in (rate_with, rate_without, alpha, power):
        if not 0 < value < 1:
            raise ValueError("rates, alpha and power must be between 0 and 1")
    delta = rate_with - rate_without
    if delta == 0:
        raise ValueError("no finite sample can detect a zero difference")
    treat, hold = 1 - holdout_fraction, holdout_fraction
    pooled = treat * rate_with + hold * rate_without
    null_sd = (pooled * (1 - pooled) * (1 / treat + 1 / hold)) ** 0.5
    alt_sd = (rate_with * (1 - rate_with) / treat + rate_without * (1 - rate_without) / hold) ** 0.5
    return int(np.ceil(((NORMAL.inv_cdf(1 - alpha / 2) * null_sd + NORMAL.inv_cdf(power) * alt_sd) / delta) ** 2))


@dataclass(frozen=True)
class Estimate:
    difference: float  # treatment rate minus holdout rate
    low: float
    high: float


def analyse(conv_treat: int, n_treat: int, conv_hold: int, n_hold: int, alpha: float = 0.05) -> Estimate:
    """Difference in conversion rates with a Wald interval. Needs a few dozen conversions per arm."""
    if min(n_treat, n_hold) <= 0 or not 0 <= conv_treat <= n_treat or not 0 <= conv_hold <= n_hold:
        raise ValueError("conversions must lie between zero and the arm size, and arms must not be empty")
    p_t, p_h = conv_treat / n_treat, conv_hold / n_hold
    se = (p_t * (1 - p_t) / n_treat + p_h * (1 - p_h) / n_hold) ** 0.5
    z = NORMAL.inv_cdf(1 - alpha / 2)
    return Estimate(p_t - p_h, p_t - p_h - z * se, p_t - p_h + z * se)


def sample_ratio_p(n_treat: int, n_hold: int, holdout_fraction: float) -> float:
    """P-value for 'the split is what we asked for'. A tiny value means the assignment is broken."""
    _check_fraction(holdout_fraction)
    n = n_treat + n_hold
    if n <= 0:
        raise ValueError("arms must not both be empty")
    z = (n_hold - n * holdout_fraction) / (n * holdout_fraction * (1 - holdout_fraction)) ** 0.5
    return 2 * (1 - NORMAL.cdf(abs(z)))


@dataclass(frozen=True)
class Replay:
    true_difference: float
    mean_estimate: float
    sd_estimate: float
    coverage: float  # share of intervals that contain the truth
    detected: float  # share of intervals that exclude zero


def replay_holdouts(with_channel: np.ndarray, without_channel: np.ndarray, fraction: float, reps: int, seed: int) -> Replay:
    """Re-randomise many times using both potential outcomes, which only a simulation has."""
    _check_fraction(fraction)
    if len(with_channel) != len(without_channel) or reps <= 0:
        raise ValueError("need equal-length outcomes and a positive number of repetitions")
    rng = np.random.default_rng(seed)
    truth = float(with_channel.mean() - without_channel.mean())
    estimates, covered, detected = [], 0, 0
    for _ in range(reps):
        held = rng.random(len(with_channel)) < fraction
        result = analyse(int(with_channel[~held].sum()), int((~held).sum()), int(without_channel[held].sum()), int(held.sum()))
        estimates.append(result.difference)
        covered += result.low <= truth <= result.high
        detected += result.low > 0 or result.high < 0
    return Replay(truth, float(np.mean(estimates)), float(np.std(estimates)), covered / reps, detected / reps)


def naive_exposed_gap(exposed: np.ndarray, converted: np.ndarray) -> float:
    """Conversion rate of exposed minus unexposed people. Shown only to expose its bias."""
    if exposed.all() or not exposed.any():
        raise ValueError("need both exposed and unexposed units")
    return float(converted[exposed].mean() - converted[~exposed].mean())
