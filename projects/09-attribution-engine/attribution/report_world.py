"""Writes reports/report.md for the synthetic world."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .analysis import Results
from .charts import credit_vs_truth_chart, error_by_world_chart, holdout_chart
from .checks import method_spread
from .decisions import CORE_METHODS
from .markdown import pct, table, whole
from .methods import METHODS
from .report_sections import attribution_section, decision_section, holdout_section, hygiene_section

TITLES = {"base": "Base: early channels work", "untargeted": "Untargeted: no confounding", "closer": "Closer: late channels work"}


def _worlds_section(r: Results) -> str:
    errors = pd.DataFrame({TITLES[w]: s["share_error"] for w, s in r.scores.items()})
    errors["Base, 10 fresh seeds: mean (min to max)"] = pd.Series(
        {m: f"{pct(row['mean'])} ({pct(row['min'])} to {pct(row['max'])})" for m, row in r.stability.iterrows()}
    )
    formats = {title: pct for title in TITLES.values()}
    sweep_formats = {"median_error": pct, "worst_error": pct, "beats_equal_split": pct, "names_right_top_channel": pct}
    return "\n\n".join(
        [
            "## 3. Which method is closest to the truth? It depends on the world",
            "**Share error** is the part of all credit that would have to move to match the causal split (0% is perfect). "
            "`equal_split` (1/8 each) and `touch_volume` use no attribution logic; a method that cannot beat them adds nothing.",
            table(errors, formats, "method"),
            "![Error by world](error_by_world.png)",
            f"### {r.settings.sweep_worlds} random worlds",
            "Lifts, targeting strength and cross-channel effects are redrawn for each world "
            f"({r.settings.sweep_users:,} users each; brand search may have a small real effect).",
            table(r.sweep, sweep_formats | {"lowest_error_worlds": whole}, "method"),
            "These are shares of the worlds this generator can produce, not of real businesses. In every one of them "
            "prospecting channels come first and intent capture comes last.",
        ]
    )


def _null_section(r: Results) -> str:
    credit = r.null.attribution.credit()[METHODS]
    return "\n\n".join(
        [
            "## 4. The null world: no channel does anything",
            f"Every lift is zero. Switching all marketing off changes conversions by {r.null.truth.incremental_total}. "
            f"Every method still hands out all {r.null.attribution.n_conversions:,} tracked conversions:",
            table(credit, whole, "channel"),
            "No attribution method can output 'nothing worked'. That is a property of the arithmetic, not of this data.",
        ]
    )


def _headline(r: Results) -> str:
    base, truth = r.worlds["base"], r.worlds["base"].truth
    scores = r.scores["base"]
    no_better = int((scores.loc[METHODS, "share_error"] >= scores.loc["equal_split", "share_error"]).sum())
    bullets = [
        f"- {base.attribution.n_conversions:,} tracked conversions are credited by every method, to the exact integer unit. Only "
        f"{truth.incremental_total:,} of all {truth.conversions_all_on:,} conversions would be lost with all switchable channels "
        f"off ({pct(truth.incremental_total / truth.conversions_all_on)}). The other {truth.conversions_all_off:,} happen anyway.",
        f"- {base.prepared.n_untracked_conversions:,} conversions had no touch. No method can credit them.",
        f"- Between the two most different core methods, {pct(method_spread(base.attribution.shares(), CORE_METHODS))} of all "
        "credit changes channel.",
        f"- In the base world, {no_better} of {len(METHODS)} methods are no closer to the truth than an equal split.",
        "- Methods with a negative raw rate-game value, set to zero: "
        f"{', '.join(base.attribution.negative_rate_channels) or 'none'}.",
    ]
    return "\n\n".join(
        [
            "# Attribution report: synthetic world with planted incrementality",
            "> **Everything in this file is synthetic.** Users, channels, effects and spend are invented. It shows how the "
            "methods behave when the truth is known. It says nothing about any real channel.",
            f"Settings: {r.settings.users:,} users, seed {r.settings.seed}, {r.settings.boot} bootstrap replicates. "
            "Rebuild with `python -m attribution`.",
            "## 1. Headline",
            "\n".join(bullets),
        ]
    )


def build(r: Results, out: Path) -> str:
    base = r.worlds["base"]
    truth = base.truth.share()
    credit_vs_truth_chart(base.attribution.shares().reindex(truth.index, fill_value=0.0), truth, out / "credit_vs_truth.png")
    error_by_world_chart(r.scores, TITLES, out / "error_by_world.png")
    holdout_chart(r.holdout, out / "holdout.png")
    sections = [_headline(r), attribution_section(r), _worlds_section(r), _null_section(r), holdout_section(r), decision_section(r),
                hygiene_section(r)]
    return "\n\n".join(sections) + "\n"
