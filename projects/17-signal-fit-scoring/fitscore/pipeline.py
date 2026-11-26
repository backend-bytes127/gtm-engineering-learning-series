"""Run the whole study and write reports/."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from threadpoolctl import threadpool_limits

from . import config, plots
from .ablation import leakage_ladder, signal_ablation
from .artifact import build_artifact, save_artifact
from .backtest import best_logistic, explainable_columns, run_backtest, select_model, split_summary
from .candidates import run_candidates
from .evaluate import calibration_table, fixed_cut_table, method_table, monthly_table, tier_table
from .features import history_numbers
from .metrics import reliability
from .models import CANDIDATES, ModelSpec
from .report import write_report
from .segments import segment_table
from .verdict import equal_month_summary

BEST_RULE = "points_rules"


def evidence_coverage(frame: pd.DataFrame, cfg: config.ScoringConfig) -> dict:
    history = history_numbers(frame, cfg)
    categorical = [f for fields in config.CATEGORICAL_GROUPS.values() for f in fields]
    return {
        "with_history": float((history["previous_capped"] > 0).mean()),
        "with_dated_signal": float((history["recency_weight"] > 0).mean()),
        "with_unknown": float((frame[categorical] == "unknown").any(axis=1).mean()),
    }


SHIPPED = "logistic_monthly"


def run(*args, **kwargs) -> dict:
    """One thread: faster for many small fits, and the same numbers from run to run."""
    with threadpool_limits(limits=1):
        return _run(*args, **kwargs)


def _run(
    frame: pd.DataFrame,
    cfg: config.ScoringConfig,
    out: Path,
    raw: Path,
    reps: int = 1000,
    validation_start: str = config.VALIDATION_START,
    test_start: str = config.TEST_START,
    candidates: tuple[ModelSpec, ...] = CANDIDATES,
) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    chosen, selection = select_model(frame, cfg, validation_start, test_start, candidates)
    rows = run_backtest(frame, chosen, cfg, validation_start, test_start)
    shipped = best_logistic(selection, candidates)
    rows = explainable_columns(frame, rows, shipped, cfg, validation_start, test_start)
    methods, differences = method_table(rows, reps)
    _, block_differences = method_table(rows, reps, block=True)
    _, shipped_differences = method_table(rows, reps, reference=SHIPPED)
    _, shipped_block_differences = method_table(rows, reps, block=True, reference=SHIPPED)
    held = frame.loc[rows.index]
    equal_months, heaviest_weight = equal_month_summary(rows)
    results = {
        "equal_months": equal_months,
        "heaviest_month_weight": heaviest_weight,
        "split": split_summary(frame, validation_start, test_start),
        "selection": selection.drop(columns="kind"),
        "chosen": chosen.name,
        "shipped": shipped.name,
        "test_rows": len(rows),
        "test_rate": float(rows["won"].mean()),
        "methods": methods,
        "differences": differences,
        "block_differences": block_differences,
        "shipped_differences": shipped_differences,
        "shipped_block_differences": shipped_block_differences,
        "monthly": monthly_table(rows),
        "shipped_tiers": tier_table(rows, cfg, reps, method=SHIPPED),
        "tiers": tier_table(rows, cfg, reps),
        "rule_tiers": tier_table(rows, cfg, reps, method=BEST_RULE),
        "fixed_cuts": fixed_cut_table(rows),
        "calibration": calibration_table(rows),
        "reliability": reliability(rows["won"].to_numpy(), rows["prob_monthly"].to_numpy()),
        "ablation": signal_ablation(frame, chosen, cfg, test_start),
        "ladder": leakage_ladder(frame, chosen, cfg, test_start),
        "evidence": evidence_coverage(held, cfg),
        "segments": segment_table(frame, test_start),
        "largest_month": held["period"].value_counts().index[0],
        "largest_month_share": float(held["period"].value_counts(normalize=True).iloc[0]),
        "candidates": run_candidates(raw, reps),
    }
    plots.method_chart(methods, out / "methods.png")
    plots.tier_chart(results["tiers"], results["test_rate"], out / "tiers.png")
    plots.monthly_chart(results["monthly"], out / "monthly.png")
    curves = {
        name: reliability(rows["won"].to_numpy(), rows[column].to_numpy())
        for name, column in (("selected model, monthly", "prob_monthly"), ("selected model, frozen", "prob_frozen"),
                             ("shipped logistic, monthly", "prob_logistic_monthly"))
    }
    plots.calibration_chart(curves, out / "calibration.png")
    save_artifact(build_artifact(frame, shipped, cfg, validation_start), out / "model.json")
    write_report(results, out)
    return results


def headline(results: dict) -> str:
    methods = results["methods"].set_index("method")
    lines = [f"selected on validation: {results['chosen']}; shipped with reason codes: {results['shipped']}",
             f"later period: {results['test_rows']} rows, win rate {results['test_rate']:.3f}"]
    for name, r in methods.iterrows():
        lines.append(f"  {name:24s} within-month AUC {r['within_month_auc']:.3f}  "
                     f"lift@10% {r['lift_top10']:.2f}  lift@30% {r['lift_top30']:.2f}  pooled AUC {r['pooled_auc']:.3f}")
    for label, key in (("selected", "tiers"), ("shipped", "shipped_tiers"), ("points_rules", "rule_tiers")):
        for _, t in results[key].iterrows():
            lines.append(f"  {label:12s} tier {t['tier']}: win rate {t['win_rate']:.3f} "
                         f"({t['win_rate_low']:.3f}-{t['win_rate_high']:.3f}), lift {t['lift']:.2f} "
                         f"({t['lift_low']:.2f}-{t['lift_high']:.2f})")
    return "\n".join(lines)
