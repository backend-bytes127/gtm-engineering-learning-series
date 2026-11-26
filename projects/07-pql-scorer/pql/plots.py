"""Aggregate charts only."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

BLUE, ORANGE, GREY = "#2563eb", "#ea580c", "#6b7280"


def _save(figure: plt.Figure, path: Path) -> None:
    figure.tight_layout()
    figure.savefig(path, dpi=130)
    plt.close(figure)


def buyer_timing_chart(rows: list[dict], path: Path) -> None:
    figure, axis = plt.subplots(figsize=(7, 3.6))
    labels = [_duration(r["cutoff_minutes"]) for r in rows]
    values = [100 * r["share_already_bought"] for r in rows]
    bars = axis.bar(labels, values, color=ORANGE)
    axis.bar_label(bars, fmt="%.0f%%")
    axis.set_ylim(0, 105)
    axis.set_ylabel("% of buyers")
    axis.set_title("Share of eventual buyers who have already bought by each scoring time")
    _save(figure, path)


def _duration(minutes: float) -> str:
    if minutes < 60:
        return f"{minutes:.0f} min"
    return f"{minutes / 60:.0f} h" if minutes < 1440 else f"{minutes / 1440:.0f} d"


def gains_chart(rows: list[dict], path: Path) -> None:
    figure, axis = plt.subplots(figsize=(7, 4))
    styles = {"model": (BLUE, "o"), "points_rule": (ORANGE, "s"), "cart_rule": (GREY, "^")}
    for name, (color, marker) in styles.items():
        picked = [r for r in rows if r["scorer"] == name]
        axis.plot([100 * r["fraction"] for r in picked], [100 * r["recall"] for r in picked], marker=marker, color=color, label=name)
    axis.set_xlabel("% of test visitors acted on")
    axis.set_ylabel("% of later buyers reached")
    axis.set_title("Test: later buyers reached at each capacity")
    axis.legend()
    _save(figure, path)


def calibration_chart(rows: list[dict], path: Path) -> None:
    figure, axis = plt.subplots(figsize=(6, 5))
    xs = [r["predicted"] for r in rows]
    ys = [r["observed"] for r in rows]
    errors = [[max(0.0, y - r["low"]) for y, r in zip(ys, rows)], [max(0.0, r["high"] - y) for y, r in zip(ys, rows)]]
    axis.errorbar(xs, ys, yerr=errors, fmt="o", color=BLUE, label="test bins (95% Wilson)")
    low, high = min(xs) / 2, max(max(xs), max(ys)) * 1.5
    axis.plot([low, high], [low, high], "--", color=GREY, label="perfect")
    axis.set_xscale("log")
    axis.set_yscale("log")
    axis.set_xlim(low, high)
    axis.set_xlabel("mean predicted probability (log scale)")
    axis.set_ylabel("observed purchase rate (log scale)")
    axis.set_title("Test calibration")
    axis.legend()
    _save(figure, path)


def milestone_chart(rows: list[dict], path: Path) -> None:
    figure, axis = plt.subplots(figsize=(8, 3.8))
    names = [r["milestone"] for r in rows][::-1]
    lifts = [r["lift_over_base"] for r in rows][::-1]
    bars = axis.barh(names, lifts, color=BLUE)
    reach = [f"{r['lift_over_base']:.1f}x, reached by {100 * r['reach']:.1f}%" for r in rows][::-1]
    axis.bar_label(bars, labels=reach, padding=3)
    axis.set_xlim(0, max(lifts) * 1.6 if max(lifts) else 1)
    axis.set_xlabel("later purchase rate / base rate (training period)")
    axis.set_title("Activation milestones reached before the cut-off")
    _save(figure, path)


def weekly_chart(rows: list[dict], path: Path) -> None:
    figure, axis = plt.subplots(figsize=(7, 3.6))
    weeks = [r["week"][5:] for r in rows]
    axis.plot(weeks, [100 * r["observed_rate"] for r in rows], marker="o", color=ORANGE, label="observed")
    axis.plot(weeks, [100 * r["mean_predicted"] for r in rows], marker="s", color=BLUE, label="mean predicted")
    axis.set_ylim(bottom=0)
    axis.set_ylabel("purchase rate %")
    axis.set_xlabel("week starting (month-day, 2015)")
    axis.set_title("Test period: predicted and observed rate by week")
    axis.legend()
    _save(figure, path)


def write_all(results: dict, directory: Path) -> None:
    buyer_timing_chart(results["buyer_timing"], directory / "buyer_timing.png")
    gains_chart(results["test"]["capacity"], directory / "gains.png")
    calibration_chart(results["test"]["calibration"], directory / "calibration.png")
    milestone_chart(results["milestones"], directory / "milestones.png")
    weekly_chart(results["weekly"], directory / "weekly.png")
