"""Score new rows with the saved JSON model and route them to tiers."""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

from .artifact import artifact_parts, contributions, load_artifact
from .features import history_numbers
from .metrics import band_weights
from .models import calibrate, logit
from .reasons import field_effects, reason_codes, unknown_fields

TIER_MODES = ("batch", "fixed")  # batch first: reused thresholds failed in the backtest


def _validate(frame: pd.DataFrame) -> None:
    if frame.empty:
        raise ValueError("input has no rows")
    if "row_id" not in frame:
        raise ValueError("input needs a row_id column")
    if frame["row_id"].astype(str).str.strip().eq("").any() or frame["row_id"].duplicated().any():
        raise ValueError("row_id must be filled and unique")
    missing = [c for c in ("previous", "pdays") if c not in frame]
    if missing:
        raise ValueError(f"missing columns {missing}; leave values blank if unknown")


def _explore(row_id: str, share: float) -> bool:
    """A stable pseudo-random sample, so the same row gets the same answer on every run."""
    digest = hashlib.sha256(f"explore:{row_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64 < share


def _tiers(raw: np.ndarray, artifact: dict, mode: str) -> list[str]:
    tiers = artifact["tiers"]
    if mode == "fixed":
        return [next(t["name"] for t in tiers if value >= t["min_score"]) for value in raw]
    # batch: rank inside this file; a tie across a cut is settled by the larger share
    lows = [0.0] + [t["top_share"] for t in tiers[:-1]]
    weights = np.vstack([band_weights(raw, low, t["top_share"]) for low, t in zip(lows, tiers, strict=True)])
    return [tiers[i]["name"] for i in weights.argmax(axis=0)]


def score_frame(frame: pd.DataFrame, artifact: dict, tier_mode: str = "batch") -> pd.DataFrame:
    if tier_mode not in TIER_MODES:
        raise ValueError(f"tier_mode must be one of {TIER_MODES}")
    _validate(frame)
    frame = frame.reset_index(drop=True)
    effects, encoder = contributions(frame, artifact)
    raw = 1 / (1 + np.exp(-(artifact["intercept"] + effects.sum(axis=1))))
    probability = calibrate(raw, tuple(artifact["calibrator"]))
    tiers = _tiers(raw, artifact, tier_mode)
    actions = {t["name"]: t["action"] for t in artifact["tiers"]}
    history = history_numbers(frame, artifact_parts(artifact)[1])
    out = []
    for i, row in frame.iterrows():
        unknown = unknown_fields(row, encoder.categories)
        codes = reason_codes(row, field_effects(effects[i], encoder.columns))
        explore = tiers[i] != artifact["tiers"][0]["name"] and _explore(str(row["row_id"]), artifact["exploration_share"])
        out.append({
            "row_id": row["row_id"], "score": round(float(raw[i]), 6), "probability_estimate": round(float(probability[i]), 4),
            "tier": tiers[i], "action": actions[tiers[i]], "explore_sample": explore,
            "reason_1": codes[0] if codes else "", "reason_2": codes[1] if len(codes) > 1 else "",
            "reason_3": codes[2] if len(codes) > 2 else "", "unknown": "; ".join(unknown),
            "has_dated_signal": bool(np.nan_to_num(history["recency_weight"].iloc[i]) > 0),
        })
    result = pd.DataFrame(out).assign(_logit=logit(raw))
    ranked = result.sort_values(["_logit", "row_id"], ascending=[False, True], kind="stable").drop(columns="_logit")
    return ranked.assign(rank=range(1, len(ranked) + 1)).reset_index(drop=True)


def score_file(input_path: Path, output_path: Path, model_path: Path, tier_mode: str = "batch") -> pd.DataFrame:
    frame = pd.read_csv(input_path, dtype=str, keep_default_na=False)
    result = score_frame(frame, load_artifact(model_path), tier_mode)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_path, index=False)
    return result
