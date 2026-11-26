"""A JSON model file: readable, diffable, and safe to load (no pickle)."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from .backtest import walk_forward_raw
from .config import ScoringConfig, Tier
from .features import Encoder, transform
from .models import ModelSpec, fit_calibrator, fit_model

FORMAT_VERSION = 2


def build_artifact(frame: pd.DataFrame, spec: ModelSpec, cfg: ScoringConfig, validation_start: str, reference_months: int = 6) -> dict:
    """Fit on every month. Nothing later exists, so this exact file has no measured performance of its own."""
    if spec.kind != "logistic":
        raise ValueError("only logistic models can be exported with reason codes")
    months = sorted(p for p in frame["period"].unique() if p >= validation_start)
    out_of_time = walk_forward_raw(frame, months, spec, cfg)
    slope, intercept = fit_calibrator(out_of_time.to_numpy(), frame.loc[out_of_time.index, "won"].to_numpy())
    fitted = fit_model(frame, spec, cfg)
    reference = frame[frame["period"].isin(sorted(frame["period"].unique())[-reference_months:])]
    reference_scores = fitted.predict(reference, cfg)
    cuts = [float(np.quantile(reference_scores, 1 - t.top_share)) if t.top_share < 1 else 0.0 for t in cfg.tiers]
    encoder = fitted.encoder
    return {
        "format_version": FORMAT_VERSION,
        "trained_through": str(frame["period"].max()),
        "training_rows": int(len(frame)),
        "model": spec.name,
        "recency_half_life_days": cfg.recency_half_life_days,
        "previous_cap": cfg.previous_cap,
        # a list, not an object: column order must survive any JSON tool, because coefficients are matched by position
        "categories": [[k, list(v)] for k, v in encoder.categories.items()],
        "numeric": list(encoder.numeric),
        "means": encoder.means.tolist(),
        "scales": encoder.scales.tolist(),
        "coefficients": fitted.estimator.coef_[0].tolist(),
        "intercept": float(fitted.estimator.intercept_[0]),
        "calibrator": [slope, intercept],
        "tiers": [{**asdict(t), "min_score": c} for t, c in zip(cfg.tiers, cuts, strict=True)],
        "tier_reference": f"scores of the last {reference_months} months in the data",
        "exploration_share": cfg.exploration_share,
    }


def save_artifact(artifact: dict, path: Path) -> None:
    Path(path).write_text(json.dumps(artifact, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def load_artifact(path: Path) -> dict:
    artifact = json.loads(Path(path).read_text(encoding="utf-8"))
    if artifact.get("format_version") != FORMAT_VERSION:
        raise ValueError("unsupported model file version")
    width = sum(len(levels) for _, levels in artifact["categories"]) + len(artifact["numeric"])
    if not all(len(artifact[k]) == width for k in ("means", "scales", "coefficients")):
        raise ValueError("model file is inconsistent: vector lengths do not match the feature list")
    return artifact


def artifact_parts(artifact: dict) -> tuple[Encoder, ScoringConfig, np.ndarray]:
    encoder = Encoder(
        {k: tuple(v) for k, v in artifact["categories"]}, tuple(artifact["numeric"]),
        np.array(artifact["means"]), np.array(artifact["scales"]),
    )
    tiers = tuple(Tier(t["name"], t["top_share"], t["action"]) for t in artifact["tiers"])
    cfg = ScoringConfig(artifact["recency_half_life_days"], artifact["previous_cap"], {}, tiers, artifact["exploration_share"])
    return encoder, cfg, np.array(artifact["coefficients"])


def contributions(frame: pd.DataFrame, artifact: dict) -> tuple[np.ndarray, Encoder]:
    """Log-odds each column adds, compared with the average training row."""
    encoder, cfg, coefficients = artifact_parts(artifact)
    return transform(frame, encoder, cfg) * coefficients, encoder
