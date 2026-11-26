"""Individual sections of the synthetic report."""
from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from .analysis import Results
from .decisions import STABLE_RATIO
from .holdout_plan import HOLDOUT_FRACTION
from .markdown import decimal, pct, table, whole
from .methods import LABELS, METHODS


def attribution_section(r: Results) -> str:
    base = r.worlds["base"]
    shares = base.attribution.shares()
    intervals = r.intervals.set_index(["method", "channel"])
    with_ci = pd.DataFrame(
        {
            LABELS[m]: [
                f"{100 * shares.loc[c, m]:.1f} ({100 * intervals.loc[(m, c), 'low']:.1f}-{100 * intervals.loc[(m, c), 'high']:.1f})"
                for c in shares.index
            ]
            for m in METHODS
        },
        index=shares.index,
    )
    return "\n\n".join(
        [
            "## 2. Credit by method against planted truth",
            "In conversions. `leave_one_out` is what is lost if only that channel is switched off (what a holdout measures). "
            "`causal_shapley` splits the whole marketing effect fairly across channels, so it adds up to that total. "
            "Direct is not switchable and has no planted effect.",
            table(r.credit.T, whole, "measure"),
            "![Credit vs truth](credit_vs_truth.png)",
            "### Share of credit with 95% bootstrap intervals (%)",
            table(with_ci.T, None, "method"),
            "The intervals cover sampling noise only. They are narrow next to the gaps between methods, and a narrow "
            "interval around a wrong rule is still wrong. Journeys are resampled as independent units.",
        ]
    )


def holdout_section(r: Results) -> str:
    formats = {
        "true_effect_pp": "{:.3f}".format,
        "holdout_mean_pp": "{:.3f}".format,
        "holdout_sd_pp": "{:.3f}".format,
        "interval_coverage": pct,
        "detected": pct,
        "naive_exposed_gap_pp": "{:.2f}".format,
        "users_needed_80pct_power": whole,
    }
    return "\n\n".join(
        [
            "## 5. Holdout test, replayed on the planted world",
            f"{HOLDOUT_FRACTION:.0%} of {r.settings.users:,} users are held out from one channel, re-randomised "
            f"{r.settings.holdout_reps} times. Effects are intention-to-treat differences in conversion rate. `detected` is "
            "the share of runs whose 95% interval excludes zero (power; for a true zero it is the false-positive rate). "
            "`users_needed` is the two-arm total for 80% power at the true effect, which in real life you must guess.",
            table(r.holdout, formats, "channel"),
            "![Holdout](holdout.png)",
            "This replay only shows that the design and arithmetic are right. A simulation has no cross-device leakage, "
            "no spillover and perfect delivery, so a real test will be noisier than this.",
        ]
    )


def decision_section(r: Results) -> str:
    frame = r.decisions.copy()
    frame["true_cost_per_incremental_eur"] = r.true_cost.reindex(frame.index)
    formats: dict[str, Callable] = {c: whole for c in frame.columns if c != "verdict"}
    return "\n\n".join(
        [
            "## 6. Budget view",
            "**Spend is an assumption invented for this example.** The first columns are what a real team could compute. "
            "The last one exists only because the world is synthetic.",
            "`spend_in_dispute` = spend x (1 - lowest credit / highest credit) across the five positional rules, Markov and "
            f"count-game Shapley. 'Methods agree' means the highest credit is at most {STABLE_RATIO:.2f} times the lowest. "
            "It is a ranking aid for what to test, not money at risk.",
            table(frame, formats | {"verdict": None}, "channel"),
        ]
    )


def hygiene_section(r: Results) -> str:
    leak = r.leakage.loc[r.leakage.max(axis=1) > 0.001]
    facts = r.normalisation
    return "\n\n".join(
        [
            "## 7. Pipeline checks",
            "### Point in time (last-touch share)",
            f"{r.worlds['base'].prepared.dropped['at_or_after_end']:,} events at or after the journey end are removed. "
            "Keeping them changes last touch like this:",
            table(leak, pct, "channel"),
            "### Channel normalisation",
            "\n".join(
                [
                    f"- {facts['events']:,} raw events carry {facts['distinct_raw_source_medium_strings']} distinct "
                    f"`utm_source / utm_medium` strings; normalising gives {facts['channels_after_normalising']} channels.",
                    f"- {pct(facts['events_matching_planted_channel'])} match the planted channel. The same author wrote the URL "
                    "variants and the rules, so this is a regression check, not an accuracy estimate.",
                    "- A 'no `utm_source` means direct' shortcut would mislabel "
                    f"{pct(facts['share_of_events_a_no_utm_source_means_direct_rule_would_mislabel'])} of events.",
                ]
            ),
            "### SQL against Python",
            "Largest difference between the SQL layer and the Python methods, in conversions: "
            f"{decimal(r.sql_gap)} (rounding from integer allocation).",
        ]
    )
