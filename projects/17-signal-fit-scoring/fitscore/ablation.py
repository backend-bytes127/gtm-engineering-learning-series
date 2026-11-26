"""Remove each signal group, then add back each excluded field, to see what moves."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold

from . import config
from .backtest import months_between, walk_forward_raw
from .config import ScoringConfig
from .metrics import grouped_band_weights, lift_at, pooled_auc, within_group_auc
from .models import ModelSpec, fit_model

MACRO = ("emp.var.rate", "cons.price.idx", "cons.conf.idx", "euribor3m", "nr.employed")
# name, extra categorical fields, extra numeric fields
ADD_BACK = (
    ("add age + marital (policy)", ("marital",), ("age",)),
    ("add contact channel", ("contact",), ()),
    ("add month + weekday of last call", ("month", "day_of_week"), ()),
    ("add market-wide indicators", (), MACRO),
    ("add campaign call count (LEAK)", (), ("campaign",)),
    ("add call duration (LEAK)", (), ("duration",)),
)


def _score_summary(held: pd.DataFrame, scores: np.ndarray, top_share: float) -> dict:
    y, months = held["won"].to_numpy(), held["period"].to_numpy()
    return {"within_month_auc": within_group_auc(y, scores, months), "lift_top30": lift_at(y, scores, months, top_share),
            "pooled_auc": pooled_auc(y, scores)}


def signal_ablation(frame: pd.DataFrame, spec: ModelSpec, cfg: ScoringConfig, test_start: str, top_share: float = 0.3) -> pd.DataFrame:
    months = months_between(frame, test_start)
    full = walk_forward_raw(frame, months, spec, cfg)
    held = frame.loc[full.index]
    groups = held["period"].to_numpy()
    base_top = grouped_band_weights(full.to_numpy(), groups, 0.0, top_share)
    variants = [("all signals", config.GROUPS)]
    variants += [(f"without {g}", tuple(x for x in config.GROUPS if x != g)) for g in config.GROUPS]
    variants += [(f"only {g}", (g,)) for g in config.GROUPS]
    out = []
    for name, groups_used in variants:
        scores = full if groups_used == config.GROUPS else walk_forward_raw(frame, months, spec, cfg, groups=groups_used)
        values = scores.loc[full.index].to_numpy()
        top = grouped_band_weights(values, groups, 0.0, top_share)
        out.append({"variant": name, **_score_summary(held, values, top_share),
                    "top30_kept_from_full": float(np.minimum(top, base_top).sum() / base_top.sum()),
                    "rank_correlation_with_full": float(pd.Series(values).corr(pd.Series(full.to_numpy()), method="spearman"))})
    return pd.DataFrame(out)


def leakage_ladder(
    frame: pd.DataFrame, spec: ModelSpec, cfg: ScoringConfig, test_start: str, folds: int = 5, top_share: float = 0.3
) -> pd.DataFrame:
    """Each excluded field added alone: monthly walk-forward result, next to a shuffled cross-validation."""
    months = months_between(frame, test_start)
    splitter = StratifiedKFold(folds, shuffle=True, random_state=config.SEED)
    splits = list(splitter.split(frame, frame["won"]))
    out = []
    for name, categorical, numeric in (("allowed fields only", (), ()), *ADD_BACK):
        extra = {"extra_categorical": categorical, "extra_numeric": numeric}
        scores = walk_forward_raw(frame, months, spec, cfg, **extra)
        shuffled = np.zeros(len(frame))
        for train_idx, test_idx in splits:
            shuffled[test_idx] = fit_model(frame.iloc[train_idx], spec, cfg, **extra).predict(frame.iloc[test_idx], cfg)
        result = _score_summary(frame.loc[scores.index], scores.to_numpy(), top_share)
        same_rows = pd.Series(shuffled, index=frame.index).loc[scores.index].to_numpy()
        held = frame.loc[scores.index]
        out.append({
            "feature_set": name, **result,
            "shuffled_within_month_auc_same_rows": within_group_auc(held["won"].to_numpy(), same_rows, held["period"].to_numpy()),
            "shuffled_pooled_auc_all_rows": pooled_auc(frame["won"].to_numpy(), shuffled),
        })
    return pd.DataFrame(out)
