"""PNG charts. Aggregates only."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from .methods import LABELS, METHODS  # noqa: E402

BLUE, GREY, ORANGE, INK = "#2563eb", "#9ca3af", "#d97706", "#111827"


def _save(figure: plt.Figure, path: Path) -> None:
    figure.savefig(path, dpi=140, bbox_inches="tight", metadata={"Software": None})
    plt.close(figure)


def credit_vs_truth_chart(shares: pd.DataFrame, truth: pd.Series, path: Path) -> None:
    """One panel per channel: each method's share as a dot, the planted causal share as a line."""
    channels = list(truth.index)
    figure, axes = plt.subplots(2, 4, figsize=(13, 7), sharey=True, sharex=True)
    positions = np.arange(len(METHODS))[::-1]
    for axis, channel in zip(axes.flat, channels):
        axis.scatter(100 * shares.loc[channel, METHODS], positions, color=BLUE, s=32, zorder=3)
        axis.axvline(100 * truth[channel], color=ORANGE, linewidth=2.5)
        axis.set_title(f"{channel}  (true {100 * truth[channel]:.0f}%)", fontsize=10, color=INK)
        axis.grid(axis="y", color="#e5e7eb")
        axis.set_xlim(left=-1.5)
    for axis in axes[:, 0]:
        axis.set_yticks(positions, [LABELS[m] for m in METHODS], fontsize=9)
    for axis in axes[1]:
        axis.set_xlabel("share of credit (%)", fontsize=9)
    figure.suptitle("Synthetic base world: credit given (blue dots) vs credit caused (orange line)", fontsize=13)
    figure.tight_layout()
    _save(figure, path)


def error_by_world_chart(scores: dict[str, pd.DataFrame], titles: dict[str, str], path: Path) -> None:
    names = [*METHODS, "equal_split"]
    figure, axes = plt.subplots(1, len(scores), figsize=(13, 4.8), sharey=True)
    positions = np.arange(len(names))[::-1]
    for axis, (world, table) in zip(axes, scores.items()):
        axis.barh(positions, 100 * table.loc[names, "share_error"], color=[BLUE] * len(METHODS) + [GREY])
        axis.axvline(100 * table.loc["equal_split", "share_error"], color=GREY, linestyle="--", linewidth=1)
        axis.set_title(titles[world], fontsize=11)
        axis.set_xlabel("credit on the wrong channel (%)", fontsize=9)
        axis.set_xlim(0, 80)
    axes[0].set_yticks(positions, [LABELS.get(m, "Equal split (no model)") for m in names], fontsize=9)
    figure.suptitle("Which rule is closest to the truth changes with the world (lower is better)", fontsize=13)
    figure.tight_layout()
    _save(figure, path)


def holdout_chart(holdout: pd.DataFrame, path: Path) -> None:
    figure, axis = plt.subplots(figsize=(10, 4.6))
    positions = np.arange(len(holdout))[::-1]
    axis.scatter(holdout["naive_exposed_gap_pp"], positions, color=GREY, label="exposed minus unexposed (not an experiment)", s=50)
    axis.errorbar(
        holdout["holdout_mean_pp"], positions, xerr=1.96 * holdout["holdout_sd_pp"], fmt="o", color=BLUE,
        capsize=3, label="randomised 20% holdout (mean, 95% spread over re-randomisations)",
    )
    axis.scatter(holdout["true_effect_pp"], positions, marker="|", s=420, color=ORANGE, linewidths=3, label="planted truth", zorder=4)
    axis.set_yticks(positions, holdout.index)
    axis.axvline(0, color="#374151", linewidth=0.8)
    axis.set_xlabel("effect on conversion rate (percentage points)")
    axis.set_title("A holdout finds the truth; comparing exposed with unexposed users does not")
    axis.legend(fontsize=8, loc="upper right")
    _save(figure, path)


def criteo_chart(shares: pd.DataFrame, path: Path) -> None:
    shown = ["last_touch", "markov", "shapley_rate"]
    figure, axis = plt.subplots(figsize=(11, 4.6))
    positions = np.arange(len(shares))
    for offset, (method, colour) in enumerate(zip(shown, [GREY, BLUE, ORANGE])):
        axis.bar(positions + (offset - 1) * 0.27, 100 * shares[method], width=0.27, color=colour, label=LABELS[method])
    axis.set_xticks(positions, shares.index, rotation=30, ha="right", fontsize=9)
    axis.set_ylabel("share of conversions credited (%)")
    axis.set_title("Criteo click paths (local output, CC BY-NC-SA 4.0): credit share by method")
    axis.legend(fontsize=9)
    _save(figure, path)
