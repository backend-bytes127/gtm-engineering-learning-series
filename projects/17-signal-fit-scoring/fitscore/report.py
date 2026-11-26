"""Write reports/report.md from computed tables. No row-level data is written."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import config
from .markdown import table, with_interval
from .verdict import verdict_table

BANNER = (
    "**Data: UCI Bank Marketing (Moro, Rita and Cortez), CC BY 4.0. Real phone-campaign records from a Portuguese bank, "
    "2008-2010. It is consumer telemarketing, not B2B pipeline.** The candidate-dataset checks at the end are labelled separately."
)


def _methods(methods: pd.DataFrame) -> str:
    view = pd.DataFrame({
        "method": methods["method"],
        "within-month AUC (95%)": with_interval(methods, "within_month_auc"),
        "lift, top 10% (95%)": with_interval(methods, "lift_top10", 2),
        "lift, top 30% (95%)": with_interval(methods, "lift_top30", 2),
        "pooled AUC": methods["pooled_auc"],
    })
    return table(view)


def _tiers(tiers: pd.DataFrame) -> str:
    view = pd.DataFrame({
        "tier": tiers["tier"], "rows": tiers["rows"].round(0).astype(int),
        "win rate (95%)": with_interval(tiers, "win_rate"), "lift (95%)": with_interval(tiers, "lift", 2),
        "share of all wins": tiers["share_of_wins"], "calls rows per win": tiers["calls_per_win"].map(lambda v: f"{v:.1f}"),
    })
    return table(view).replace("calls rows per win", "rows per win")


def _differences(differences: pd.DataFrame) -> str:
    view = differences.assign(clear=(differences["low"] > 0) | (differences["high"] < 0))
    return table(view.rename(columns={"clear": "interval excludes 0"}))


def _candidates(candidates: dict) -> list[str]:
    lines = ["## Other candidate datasets (checked, not used for the main result)", ""]
    if "maven" in candidates:
        m = candidates["maven"]
        lines += [
            "### Maven Analytics CRM Sales Opportunities (FICTITIOUS company)", "",
            f"{m['pipeline_rows']} pipeline rows, {m['open_rows']} still open. Logistic model on rep, team, product and account "
            f"fields; trained on {m['train_rows']} deals closed before the cutoff, tested on {m['test_rows']} engaged later "
            f"(win rate {m['test_win_rate']:.3f}).",
            f"Later-period AUC **{m['auc']:.3f}** (95% {m['auc_low']:.3f} to {m['auc_high']:.3f}); "
            f"top-30% lift {m['lift_top30']:.2f} ({m['lift_low']:.2f} to {m['lift_high']:.2f}). "
            "Only closed deals are tested, so slow deals are under-represented.", "",
        ]
    if not candidates:
        lines.append("Not run: files not downloaded.")
    return lines


def render(r: dict) -> str:
    lines = [
        "# Fit and history scoring: backtest report", "", BANNER, "",
        "## Question and point in time", "",
        "Which rows on a call list should be worked first? Each score is made **before the first call of the campaign**, "
        "using the person's job, education, credit and loan flags, and results of earlier campaigns. "
        "Call length, call count, call timing, age, marital status and market-wide indicators are excluded.", "",
        "## Short answer", "",
        "Chosen model against each simple rule on later months. A difference counts only if its 95% interval excludes zero. "
        f"{r['largest_month']} alone holds {r['largest_month_share']:.0%} of the later rows.", "",
        table(verdict_table(r["differences"], r["block_differences"])), "",
        f"The pooled within-month AUC is weighted by (won, lost) pairs, so one month carries {r['heaviest_month_weight']:.0%} of it. "
        "Giving every month the same weight instead:", "", table(r["equal_months"]), "",
        "## Splits (by time; month rebuilt from row order)", "", table(r["split"]), "",
        "## Model choice (validation months only)", "", table(r["selection"]), "",
        f"Rule set in advance: boosted trees are chosen only if they beat the best logistic model by 0.01. "
        f"Chosen: **{r['chosen']}**. Boosted trees give no simple reason codes, so the file the scoring command loads is the "
        f"best logistic model, **{r['shipped']}**, shown below as `logistic_monthly`.", "",
        f"## Does the score beat simple rules on later data? ({config.TEST_START} onwards, {r['test_rows']} rows, "
        f"win rate {r['test_rate']:.3f})", "",
        "`model_monthly` is the chosen model refitted before each month on all earlier months (the primary result). "
        "`model_frozen` is fitted once before the later period. `logistic_monthly` is the explainable model, refitted monthly. "
        "Lift is measured inside each month, then pooled.", "",
        _methods(r["methods"]), "", "![Methods](methods.png)", "",
        "### Paired differences: chosen model minus each other method (rows resampled within month)", "",
        _differences(r["differences"]), "",
        "### Same differences when whole months are resampled (wider)", "", _differences(r["block_differences"]), "",
        "### Shipped logistic minus each other method (rows resampled within month)", "", _differences(r["shipped_differences"]), "",
        "### Shipped logistic, whole months resampled", "", _differences(r["shipped_block_differences"]), "",
        "## Month by month", "", table(r["monthly"]), "", "![Months](monthly.png)", "",
        "## Tiers (rank inside each month: A top 10%, B next 20%, C the rest)", "", _tiers(r["tiers"]), "",
        "![Tiers](tiers.png)", "",
        "Same tiers from the shipped logistic model:", "", _tiers(r["shipped_tiers"]), "",
        "Same tiers from the hand-written points rules:", "", _tiers(r["rule_tiers"]), "",
        "### Reusing score thresholds from the previous three months instead", "", table(r["fixed_cuts"]), "",
        "## Calibration on later months", "",
        "`trailing_rate` gives every row the previous month's win rate: a no-model baseline.", "",
        table(r["calibration"]), "", "![Calibration](calibration.png)", "",
        "Reliability of the chosen model's monthly calibrated probability:", "", table(r["reliability"]), "",
        "## Which signals matter (chosen model, monthly walk-forward)", "",
        "`top30_kept_from_full` is the share of the full model's top-30% rows that stay in the top 30%.", "",
        table(r["ablation"]), "",
        "## What the excluded fields would have added", "",
        "Each field is added alone. The first three result columns are the monthly walk-forward. The last two come from a shuffled "
        "5-fold split, which lets the model learn from the future: first scored on the same later rows, then on all rows.", "",
        table(r["ladder"]), "",
        "## Segment playbook (aggregates)", "",
        "Segments are ranked by their win rate in the months before the later period, then checked on the later months.", "",
        table(r["segments"]), "",
        "## Evidence behind a score", "",
        f"- Every reason code names a source column and its value.\n"
        f"- Rows in the later period with any earlier-campaign history: {r['evidence']['with_history']:.1%}.\n"
        f"- Rows with a dated signal (days since earlier contact): {r['evidence']['with_dated_signal']:.1%}. "
        "The file gives no calendar date for any single signal, so time decay applies only to these rows.\n"
        f"- Rows with at least one literal 'unknown' value: {r['evidence']['with_unknown']:.1%}.", "",
        *_candidates(r["candidates"]),
    ]
    return "\n".join(lines).rstrip() + "\n"


def write_report(results: dict, folder: Path) -> Path:
    path = Path(folder) / "report.md"
    path.write_text(render(results), encoding="utf-8")
    return path
