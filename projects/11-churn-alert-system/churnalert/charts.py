"""PNG charts. Aggregates only."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

BLUE, GREEN, RED, GREY, ORANGE = "#1d4ed8", "#047857", "#b91c1c", "#6b7280", "#c2410c"
STYLE = {"logistic": (BLUE, "-"), "boosted_trees": (GREEN, "-"), "recency_rule": (ORANGE, "--"),
         "overdue_rule": (RED, ":"), "base_rate": (GREY, ":")}


def _save(figure: plt.Figure, path: Path) -> None:
    figure.tight_layout()
    figure.savefig(path, dpi=130)
    plt.close(figure)


def waterfall_chart(row: pd.Series, path: Path) -> None:
    steps = [("Start\n(base year)", row.start_pence, "total"), ("New", row.new_pence, "up"),
             ("Reactivated", row.reactivation_pence, "up"), ("Expansion", row.expansion_pence, "up"),
             ("Contraction", -row.contraction_pence, "down"), ("Churn", -row.churn_pence, "down"),
             ("End\n(next year)", row.end_pence, "total")]
    figure, axis = plt.subplots(figsize=(10, 5))
    level = 0.0
    for i, (_, pence, kind) in enumerate(steps):
        value = pence / 1e8
        bottom, height = (0, value) if kind == "total" else (level + min(value, 0), abs(value))
        axis.bar(i, height, bottom=bottom, color={"total": BLUE, "up": GREEN, "down": RED}[kind])
        axis.text(i, bottom + height + 0.08, f"{value:+.2f}" if kind != "total" else f"{value:.2f}", ha="center", fontsize=9)
        level = value if kind == "total" else level + value
    axis.set_xticks(range(len(steps)), [s[0] for s in steps])
    axis.set_ylabel("net revenue, GBP million")
    axis.set_title("Year-on-year revenue movement: Dec 2010-Nov 2011 against Dec 2009-Nov 2010")
    _save(figure, path)


def cohort_heatmap(triangle: pd.DataFrame, path: Path) -> None:
    share = triangle.assign(share=triangle["buyers"] / triangle["cohort_size"])
    grid = share.pivot(index="cohort_month", columns="month_index", values="share")
    figure, axis = plt.subplots(figsize=(12, 7))
    image = axis.imshow(grid.to_numpy(float), aspect="auto", cmap="Blues", vmin=0, vmax=0.6)
    sizes = triangle.drop_duplicates("cohort_month").set_index("cohort_month")["cohort_size"]
    axis.set_yticks(range(len(grid)), [f"{m} (n={sizes[m]})" for m in grid.index], fontsize=8)
    axis.set_xticks(range(len(grid.columns)), grid.columns, fontsize=8)
    for (i, j), value in np.ndenumerate(grid.to_numpy(float)):
        if np.isfinite(value) and grid.columns[j] > 0:
            axis.text(j, i, f"{100 * value:.0f}", ha="center", va="center", fontsize=6,
                      color="white" if value > 0.35 else "black")
    axis.set_xlabel("months after first purchase month")
    axis.set_title("Share of each cohort that bought in month k (%). 2009-12 includes older customers")
    figure.colorbar(image, ax=axis, shrink=0.7)
    _save(figure, path)


def retention_chart(water: pd.DataFrame, trap: pd.DataFrame, path: Path) -> None:
    figure, (left, right) = plt.subplots(1, 2, figsize=(12, 4.5))
    x = np.arange(len(water))
    left.bar(x - 0.2, 100 * water["grr"], 0.4, label="GRR", color=BLUE)
    left.bar(x + 0.2, 100 * water["nrr"], 0.4, label="NRR", color=GREEN)
    left.set_xticks(x, water["cmp"])
    left.set_ylim(0, 100)
    left.set_title("Same months one year apart (%)")
    left.legend()
    right.plot(trap["month"], 100 * trap["naive_grr"], color=RED, marker="o")
    right.set_ylim(0, 100)
    right.tick_params(axis="x", rotation=90, labelsize=7)
    right.set_title("Do NOT report: month-on-month 'GRR' (%)")
    _save(figure, path)


def calibration_chart(tables: dict[str, pd.DataFrame], path: Path) -> None:
    figure, axes = plt.subplots(1, len(tables), figsize=(5.5 * len(tables), 5), squeeze=False)
    for axis, (title, table) in zip(axes[0], tables.items()):
        axis.plot([0, 1], [0, 1], color=GREY, linestyle=":", label="perfect")
        axis.plot(table["predicted"], table["observed"], color=BLUE, marker="o", label="model")
        for row in table.itertuples():
            axis.annotate(str(row.rows), (row.predicted, row.observed), fontsize=7, xytext=(3, -9), textcoords="offset points")
        axis.set_xlim(0, 1)
        axis.set_ylim(0, 1)
        axis.set_xlabel("predicted churn probability")
        axis.set_ylabel("observed churn rate")
        axis.set_title(title)
        axis.legend()
    _save(figure, path)


def precision_chart(weeks: pd.DataFrame, capacity: int, path: Path) -> None:
    figure, axis = plt.subplots(figsize=(11, 4.5))
    for name, (colour, line) in STYLE.items():
        part = weeks[weeks["model"] == name]
        axis.plot(part["as_of"], 100 * part["precision"], color=colour, linestyle=line, label=name, marker=".")
    axis.set_ylim(0, 100)
    axis.set_ylabel(f"precision in top {capacity} (%)")
    axis.set_title("Test weeks: how many of the flagged accounts did not buy again in 90 days")
    axis.legend(ncol=5, fontsize=8)
    figure.autofmt_xdate()
    _save(figure, path)
