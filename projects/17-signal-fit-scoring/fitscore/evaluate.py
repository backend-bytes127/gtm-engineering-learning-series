"""Turn backtest rows into result tables."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config
from .bootstrap import interval, month_block_bootstrap, month_stratified_bootstrap
from .config import ScoringConfig
from .metrics import brier, group_indices, grouped_band_weights, lift_at, log_loss, pooled_auc, within_group_auc

METHODS = (
    "model_monthly", "model_frozen", "logistic_monthly",
    "points_rules", "previous_success_first", "most_recent_first", "best_job_first", "no_ranking",
)
MODEL = "model_monthly"
TOP_SHARES = (0.1, 0.3)
MEASURES = ("within_month_auc", "lift_top10", "lift_top30")


def _measure_vector(y: np.ndarray, scores: list[np.ndarray], groups: np.ndarray, indices: list) -> np.ndarray:
    values = []
    for s in scores:
        values.append(within_group_auc(y, s, groups, indices))
        values.extend(lift_at(y, s, groups, share, indices) for share in TOP_SHARES)
    return np.array(values)


def method_table(
    rows: pd.DataFrame, reps: int, seed: int = config.SEED, block: bool = False, reference: str = MODEL
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Scores per method with intervals, and paired differences (`reference` minus each other method)."""
    y, months = rows["won"].to_numpy(), rows["period"].to_numpy()
    scores = [rows[f"score_{m}"].to_numpy() for m in METHODS]
    width = len(MEASURES)

    def statistic(picked: np.ndarray, groups: np.ndarray, indices: list) -> np.ndarray:
        return _measure_vector(y[picked], [s[picked] for s in scores], groups, indices)

    ordered = np.argsort(months, kind="stable")
    point = _measure_vector(y, scores, months, group_indices(months))
    sampler = month_block_bootstrap if block else month_stratified_bootstrap
    draws = sampler(months, statistic, reps, seed)
    low, high = interval(draws)
    table, differences = [], []
    base = METHODS.index(reference) * width
    for i, method in enumerate(METHODS):
        entry = {"method": method, "pooled_auc": pooled_auc(y[ordered], scores[i][ordered])}
        for j, measure in enumerate(MEASURES):
            entry.update({measure: point[i * width + j], f"{measure}_low": low[i * width + j], f"{measure}_high": high[i * width + j]})
        table.append(entry)
        if method == reference:
            continue
        for j, measure in enumerate(MEASURES):
            delta = draws[:, base + j] - draws[:, i * width + j]
            d_low, d_high = interval(delta[:, None])
            differences.append({"compared_with": method, "measure": measure, "difference": point[base + j] - point[i * width + j],
                                "low": d_low[0], "high": d_high[0]})
    return pd.DataFrame(table), pd.DataFrame(differences)


def tier_bands(cfg: ScoringConfig) -> list[tuple[str, float, float]]:
    lows = [0.0] + [t.top_share for t in cfg.tiers[:-1]]
    return [(t.name, low, t.top_share) for t, low in zip(cfg.tiers, lows, strict=True)]


def tier_table(rows: pd.DataFrame, cfg: ScoringConfig, reps: int, method: str = MODEL, seed: int = config.SEED) -> pd.DataFrame:
    """Tiers by rank inside each month. Rate and lift per tier with intervals."""
    y, months, score = rows["won"].to_numpy(), rows["period"].to_numpy(), rows[f"score_{method}"].to_numpy()
    bands = tier_bands(cfg)

    def statistic(picked: np.ndarray, groups: np.ndarray, indices: list) -> np.ndarray:
        values = []
        for _, low, high in bands:
            w = grouped_band_weights(score[picked], groups, low, high, indices)
            rate = w @ y[picked] / w.sum()
            values.extend([rate, rate / y[picked].mean(), w @ y[picked] / y[picked].sum()])
        return np.array(values)

    point = statistic(np.arange(len(y)), months, group_indices(months))
    low, high = interval(month_stratified_bootstrap(months, statistic, reps, seed))
    out = []
    for i, (name, band_low, band_high) in enumerate(bands):
        row_count = grouped_band_weights(score, months, band_low, band_high).sum()
        entry = {"tier": name, "rows": row_count, "share_of_rows": row_count / len(y)}
        for j, key in enumerate(("win_rate", "lift", "share_of_wins")):
            entry.update({key: point[i * 3 + j], f"{key}_low": low[i * 3 + j], f"{key}_high": high[i * 3 + j]})
        entry["calls_per_win"] = 1 / entry["win_rate"] if entry["win_rate"] > 0 else float("nan")
        out.append(entry)
    return pd.DataFrame(out)


def fixed_cut_table(rows: pd.DataFrame) -> pd.DataFrame:
    """What happens if score thresholds from past months are reused: tier sizes move with the data."""
    score = rows["score_model_monthly"]
    tier = np.where(score >= rows["reference_cut_a"], "A", np.where(score >= rows["reference_cut_b"], "B", "C"))
    tagged = rows.assign(tier=tier)
    overall = tagged.groupby("period").size()
    shares = (tagged.groupby(["period", "tier"]).size().unstack(fill_value=0).reindex(columns=["A", "B", "C"], fill_value=0))
    shares = shares.div(overall, axis=0)
    summary = tagged.groupby("tier")["won"].agg(rows="size", win_rate="mean").reindex(["A", "B", "C"])
    summary["smallest_monthly_share"] = shares.min()
    summary["largest_monthly_share"] = shares.max()
    return summary.reset_index()


def calibration_table(rows: pd.DataFrame) -> pd.DataFrame:
    y = rows["won"].to_numpy()
    out = []
    names = ("prob_monthly", "prob_monthly_uncalibrated", "prob_frozen", "prob_logistic_monthly", "prob_trailing_rate")
    for name in names:
        p = rows[name].to_numpy()
        out.append({"probability": name.removeprefix("prob_"), "mean_predicted": p.mean(), "observed_rate": y.mean(),
                    "brier": brier(y, p), "log_loss": log_loss(y, p)})
    return pd.DataFrame(out)


def monthly_table(rows: pd.DataFrame, min_rows: int = 50) -> pd.DataFrame:
    """Month by month: the model against the strongest simple rules, at the top 30% of each month's list."""
    out = []
    for month, part in rows.groupby("period"):
        y, groups = part["won"].to_numpy(), part["period"].to_numpy()
        entry = {"month": month, "rows": len(part), "win_rate": y.mean()}
        for method in ("model_monthly", "points_rules", "previous_success_first"):
            entry[f"auc_{method}"] = within_group_auc(y, part[f"score_{method}"].to_numpy(), groups)
        entry["lift_top30_model"] = lift_at(y, part["score_model_monthly"].to_numpy(), groups, 0.3) if y.sum() else float("nan")
        entry["small_month"] = len(part) < min_rows
        out.append(entry)
    return pd.DataFrame(out)
