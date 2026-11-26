"""Writes output/criteo_report.md (local, git-ignored): aggregates only. All statements about the file are computed."""
from __future__ import annotations

from pathlib import Path

from .charts import criteo_chart
from .criteo_run import PRIMARY_LOOKBACK_DAYS, CriteoResult
from .markdown import pct, table, whole
from .methods import LABELS, METHODS, total_variation

NOTICE = (
    "> **Real data, non-commercial licence.** Criteo Attribution Modeling for Bidding Dataset, Criteo AI Lab, "
    "CC BY-NC-SA 4.0 (https://ailab.criteo.com/criteo-attribution-modeling-bidding-dataset/). Cite: Diemert, Meynet, "
    "Galland, Lefortier, AdKDD & TargetAd 2017. This file and `criteo_shares.png` are aggregates adapted from it and are "
    "shared under the same CC BY-NC-SA 4.0 licence. No rows or user ids are included."
)


SAME_CREDIT = 1e-5  # integer-unit rounding noise


def consequences(audit: dict[str, float]) -> str:
    """What the audit of this particular file implies. Every sentence follows from a computed value."""
    unclicked = audit["converted_rows_without_a_click"]
    multi = audit["conversion_paths_with_more_than_one_campaign"]
    late = audit["conversions_after_the_last_observed_impression"]
    labels = ("Every row marked converted is a clicked row. Check how that label was built before using impression paths."
              if unclicked == 0 else f"{unclicked:,} rows marked converted have no click.")
    paths = ("No conversion path contains two campaigns, so there is nothing to split between campaigns on these paths."
             if multi == 0 else f"{multi:,} conversions have more than one campaign on their converted rows.")
    return "\n".join([
        "Consequences:",
        f"- {labels} This comparison uses click paths only.",
        f"- {paths}",
        f"- Conversions after the last observed impression: {late:,}. Conversions outside the observed window, or without a "
        "full lookback window, are excluded.",
    ])


def conclusions(positional_gap: float) -> str:
    rules = ("On these paths the choice among the five positional rules makes no difference."
             if positional_gap < SAME_CREDIT
             else f"The five positional rules differ by up to {pct(positional_gap)} of credit.")
    return "\n".join([
        f"- {rules}",
        "- Compare the other methods and lookback windows in the tables above.",
        "- Nothing here says any campaign caused a sale. The vendor's own `attribution` flag is not used: it is a credit "
        "rule, not a causal label.",
    ])


def build(r: CriteoResult, out: Path, n_boot: int) -> str:
    shares = r.attribution.shares()[METHODS]
    criteo_chart(shares, out / "criteo_shares.png")
    audit = "\n".join(
        f"| {key.replace('_', ' ')} | {value:,.1f} |" if key == "observed_days" else f"| {key.replace('_', ' ')} | {value:,} |"
        for key, value in r.audit.items()
    )
    distance = shares.apply(lambda column: total_variation(column, shares["last_touch"]))
    moved = distance.rename("credit moved vs last touch").to_frame().rename(index=LABELS)
    intervals = r.intervals.set_index(["method", "channel"])
    ci = intervals.loc["shapley_rate"].assign(share=shares["shapley_rate"])[["share", "low", "high"]]
    lookback = r.lookbacks[r.lookbacks["method"].isin(["last_touch", "shapley_rate"])].copy()
    lookback.index = [f"{LABELS[m]}, {d}d" for m, d in zip(lookback["method"], lookback["lookback_days"])]
    lookback = lookback.drop(columns=["method", "lookback_days"]).sort_index(kind="mergesort")
    lookback_formats = {c: pct for c in lookback.columns} | {"conversions": whole}
    lengths = r.path_lengths
    parts = [
        "# Criteo click paths: audit and method comparison (local output)",
        NOTICE,
        "This is one display vendor's sub-sampled traffic. A campaign id is not a marketing channel, there is no "
        "randomised control, and nothing here measures incrementality.",
        "## 1. Audit",
        "| check | value |\n|---|---|\n" + audit,
        consequences(r.audit),
        f"## 2. Methods ({PRIMARY_LOOKBACK_DAYS}-day lookback)",
        f"{r.prepared.n_conversions:,} conversions with a click path; {lengths.mean():.2f} clicks per path on average, "
        f"{pct((lengths == 1).mean())} with one click. Top 9 campaigns by converting clicks are labelled A to I; the rest are "
        "pooled as `other` (exact Shapley needs few players, and pooling hides differences inside `other`).",
        table(shares, pct, "campaign"),
        "![Criteo shares](criteo_shares.png)",
        "With every campaign kept separate, the largest gap between any two of the five positional rules is "
        f"{pct(r.all_campaign_distance.to_numpy().max())} of credit.",
        table(moved, pct, "method"),
        f"The rate game gave a negative raw value to: {', '.join(r.attribution.negative_rate_channels) or 'none'}. "
        "These are set to zero before rescaling. It compares conversion **rates** and ignores volume, so a small campaign "
        "with a high rate takes credit from large ones. That is a choice of value function, not a discovery about the data.",
        f"### Rate-game Shapley, 95% bootstrap intervals ({n_boot} replicates)",
        table(ci, pct, "campaign"),
        "## 3. Analyst choice: lookback window",
        "Each window also changes which conversions have a full lookback, so the rows mix a rule change with a period change.",
        table(lookback, lookback_formats, "method, lookback"),
        "## 4. What can be concluded",
        conclusions(float(r.all_campaign_distance.to_numpy().max())),
    ]
    return "\n\n".join(parts) + "\n"
