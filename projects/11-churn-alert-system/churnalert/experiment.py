"""How big a randomised holdout is needed to show that outreach reduces churn? The model cannot show that."""
from __future__ import annotations

from math import ceil, sqrt
from statistics import NormalDist


def per_arm(control_rate: float, reduction: float, alpha: float = 0.05, power: float = 0.8) -> int:
    """Two-sided two-proportion test, normal approximation. Each account counts once."""
    treated = control_rate - reduction
    if not 0 < treated < control_rate < 1:
        raise ValueError("need 0 < control_rate - reduction < control_rate < 1")
    z_alpha, z_power = NormalDist().inv_cdf(1 - alpha / 2), NormalDist().inv_cdf(power)
    pooled = (control_rate + treated) / 2
    top = z_alpha * sqrt(2 * pooled * (1 - pooled)) + z_power * sqrt(control_rate * (1 - control_rate) + treated * (1 - treated))
    return ceil((top / reduction) ** 2)
