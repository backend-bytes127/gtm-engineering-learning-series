"""PNG charts from aggregate tables only."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

BLUE, GREY, ORANGE = "#1f5fa8", "#8a8f98", "#d9731a"


def _save(figure, path: Path) -> None:
    figure.tight_layout()
    figure.savefig(path, dpi=130)
    plt.close(figure)


def tier_chart(tiers: pd.DataFrame, overall: float, path: Path) -> None:
    figure, axis = plt.subplots(figsize=(6.4, 3.8))
    errors = np.clip([tiers["win_rate"] - tiers["win_rate_low"], tiers["win_rate_high"] - tiers["win_rate"]], 0, None)
    axis.bar(tiers["tier"], tiers["win_rate"], color=BLUE, yerr=errors, capsize=5)
    axis.axhline(overall, color=ORANGE, linestyle="--", label=f"whole list {overall:.1%}")
    axis.set_ylabel("win rate")
    axis.set_title("Later months: win rate by tier (rank within month, 95% intervals)", fontsize=10)
    axis.legend()
    _save(figure, path)


def method_chart(methods: pd.DataFrame, path: Path) -> None:
    ordered = methods.sort_values("within_month_auc")
    figure, axis = plt.subplots(figsize=(7.2, 3.8))
    errors = np.clip([ordered["within_month_auc"] - ordered["within_month_auc_low"],
                      ordered["within_month_auc_high"] - ordered["within_month_auc"]], 0, None)
    colors = [BLUE if m.startswith(("model", "logistic")) else GREY for m in ordered["method"]]
    axis.barh(ordered["method"], ordered["within_month_auc"], xerr=errors, color=colors, capsize=3)
    axis.axvline(0.5, color=ORANGE, linestyle="--")
    axis.set_xlim(0.4, max(0.75, float(ordered["within_month_auc_high"].max()) + 0.02))
    axis.set_title("Ordering one month's list (within-month AUC, 0.5 = random)", fontsize=10)
    _save(figure, path)


def monthly_chart(monthly: pd.DataFrame, path: Path) -> None:
    figure, (top, bottom) = plt.subplots(2, 1, figsize=(8, 5.4), sharex=True)
    positions = np.arange(len(monthly))
    top.bar(positions, monthly["win_rate"], color=GREY)
    top.set_ylabel("win rate")
    top.set_title("The later period is not stable: win rate and ranking quality by month", fontsize=10)
    for column, label, color in (("auc_model_monthly", "chosen model, retrained monthly", BLUE),
                                 ("auc_previous_success_first", "rule: previous success first", ORANGE)):
        bottom.plot(positions, monthly[column], marker="o", label=label, color=color)
    bottom.axhline(0.5, color=GREY, linestyle=":")
    bottom.set_ylabel("AUC within month")
    bottom.set_xticks(positions, monthly["month"], rotation=60, fontsize=8)
    bottom.legend(fontsize=8)
    _save(figure, path)


def calibration_chart(curves: dict[str, pd.DataFrame], path: Path) -> None:
    figure, axis = plt.subplots(figsize=(5.4, 4.6))
    axis.plot([0, 0.8], [0, 0.8], color=GREY, linestyle=":", label="perfect")
    for (name, table), color in zip(curves.items(), (BLUE, ORANGE, "#3a8f5c"), strict=False):
        axis.plot(table["mean_predicted"], table["observed_rate"], marker="o", label=name, color=color)
    axis.set_xlabel("mean predicted probability")
    axis.set_ylabel("observed win rate")
    axis.set_title("Calibration on later months (five equal-size bins)", fontsize=10)
    axis.legend(fontsize=8)
    _save(figure, path)
