"""Point-in-time features. Only fields that exist before the first call of a campaign."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import config
from .config import ScoringConfig

NOT_CONTACTED = 999  # documented code in the source file
NUMERIC_HISTORY = ("previous_capped", "recency_weight", "days_since_unknown")


def _is_blank(series: pd.Series) -> pd.Series:
    return series.isna() | (series.astype(str).str.strip() == "")


def _whole_numbers(series: pd.Series, name: str) -> pd.Series:
    """Blank stays missing (unknown, not zero). Anything else must be a whole number >= 0."""
    blank = _is_blank(series)
    values = pd.to_numeric(series.where(~blank), errors="coerce")
    invalid = (~blank) & (values.isna() | (values < 0) | (values % 1 != 0))
    if invalid.any():
        raise ValueError(f"{name} must be a whole number >= 0 or blank; bad rows: {list(series.index[invalid][:5])}")
    return values.astype(float)


def history_numbers(frame: pd.DataFrame, cfg: ScoringConfig) -> pd.DataFrame:
    """Prior-campaign numbers, with recency decayed by half every `recency_half_life_days`."""
    previous = _whole_numbers(frame["previous"], "previous")
    pdays = _whole_numbers(frame["pdays"], "pdays")
    dated = pdays.notna() & (pdays != NOT_CONTACTED)
    recency = np.where(dated, 0.5 ** (pdays.where(dated, 0.0) / cfg.recency_half_life_days), 0.0)
    return pd.DataFrame(
        {
            "previous_capped": previous.clip(upper=cfg.previous_cap),
            "recency_weight": np.where(previous.isna() & ~dated, np.nan, recency),
            "days_since_unknown": np.where(previous.isna(), np.nan, ((previous > 0) & ~dated).astype(float)),
        },
        index=frame.index,
    )


@dataclass(frozen=True)
class Encoder:
    """One-hot and scaled numbers. A value never seen in training is neutral (set to the training mean)."""

    categories: dict[str, tuple[str, ...]]
    numeric: tuple[str, ...]
    means: np.ndarray
    scales: np.ndarray

    @property
    def columns(self) -> list[tuple[str, str]]:
        cats = [(field, level) for field, levels in self.categories.items() for level in levels]
        return cats + [(name, "") for name in self.numeric]


def _raw_matrix(frame: pd.DataFrame, categories: dict, numeric: tuple[str, ...], cfg: ScoringConfig) -> np.ndarray:
    blocks = []
    for field, levels in categories.items():
        values = frame[field].astype(str).to_numpy() if field in frame else np.full(len(frame), "")
        known = np.isin(values, levels)
        block = (values[:, None] == np.array(levels)[None, :]).astype(float)
        block[~known] = np.nan
        blocks.append(block)
    if numeric:
        table = history_numbers(frame, cfg) if set(numeric) & set(NUMERIC_HISTORY) else pd.DataFrame(index=frame.index)
        columns = [table[n] if n in table else pd.to_numeric(frame[n], errors="raise") for n in numeric]
        blocks.append(np.column_stack([np.asarray(c, dtype=float) for c in columns]))
    return np.hstack(blocks) if blocks else np.empty((len(frame), 0))


def feature_spec(groups: tuple[str, ...], extra_categorical: tuple[str, ...] = (), extra_numeric: tuple[str, ...] = ()) -> tuple:
    fields = tuple(f for g in groups for f in config.CATEGORICAL_GROUPS[g]) + extra_categorical
    numeric = (NUMERIC_HISTORY if "history" in groups else ()) + extra_numeric
    return fields, numeric


def fit_encoder(frame: pd.DataFrame, fields: tuple[str, ...], numeric: tuple[str, ...], cfg: ScoringConfig) -> Encoder:
    categories = {f: tuple(sorted(frame[f].astype(str).unique())) for f in fields}
    raw = _raw_matrix(frame, categories, numeric, cfg)
    means = np.nanmean(raw, axis=0)
    n_categorical = sum(len(v) for v in categories.values())
    spread = np.nanstd(raw, axis=0)
    scales = np.where((np.arange(raw.shape[1]) >= n_categorical) & (spread > 0), spread, 1.0)
    return Encoder(categories, numeric, means, scales)


def transform(frame: pd.DataFrame, encoder: Encoder, cfg: ScoringConfig) -> np.ndarray:
    """Return the centred matrix: zero means 'average training row' or 'unknown'."""
    raw = _raw_matrix(frame, encoder.categories, encoder.numeric, cfg)
    filled = np.where(np.isnan(raw), encoder.means, raw)
    return (filled - encoder.means) / encoder.scales
