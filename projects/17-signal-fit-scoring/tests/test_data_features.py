from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from fitscore import config
from fitscore.data import add_period, load_bank, prepare
from fitscore.features import feature_spec, fit_encoder, history_numbers, transform


def test_year_advances_when_month_goes_back() -> None:
    out = add_period(pd.DataFrame({"month": ["nov", "dec", "mar", "mar", "jan"]}))
    assert list(out["period"]) == ["2008-11", "2008-12", "2009-03", "2009-03", "2010-01"]


def test_prepare_rejects_bad_input_and_does_not_mutate(raw_rows: pd.DataFrame) -> None:
    before = raw_rows.copy()
    prepare(raw_rows)
    pd.testing.assert_frame_equal(raw_rows, before)
    with pytest.raises(ValueError, match="missing columns"):
        prepare(raw_rows.drop(columns="job"))
    with pytest.raises(ValueError, match="target"):
        prepare(raw_rows.assign(y="maybe"))
    with pytest.raises(ValueError, match="month"):
        prepare(raw_rows.assign(month="xx"))


def test_load_bank_reads_semicolon_file(tmp_path, raw_rows: pd.DataFrame) -> None:
    path = tmp_path / "bank.csv"
    raw_rows.to_csv(path, sep=";", index=False)
    assert len(load_bank(path)) == len(raw_rows)
    with pytest.raises(FileNotFoundError, match="fetch_data"):
        load_bank(tmp_path / "missing.csv")


def test_recency_halves_each_half_life_and_999_means_no_date(cfg) -> None:
    rows = pd.DataFrame({"previous": [1, 1, 1, 0, 9], "pdays": [0, 7, 999, 999, 14]})
    out = history_numbers(rows, cfg)
    assert out["recency_weight"].tolist() == [1.0, 0.5, 0.0, 0.0, 0.25]
    assert out["days_since_unknown"].tolist() == [0.0, 0.0, 1.0, 0.0, 0.0]
    assert out["previous_capped"].iloc[4] == cfg.previous_cap


def test_blank_history_is_missing_not_zero(cfg) -> None:
    out = history_numbers(pd.DataFrame({"previous": [""], "pdays": [""]}), cfg)
    assert out.isna().all().all()


@pytest.mark.parametrize("value", ["-1", "2.5", "soon"])
def test_bad_numbers_are_rejected(cfg, value: str) -> None:
    with pytest.raises(ValueError, match="pdays"):
        history_numbers(pd.DataFrame({"previous": ["1"], "pdays": [value]}), cfg)


def test_unseen_and_blank_values_are_neutral(frame, cfg) -> None:
    encoder = fit_encoder(frame, *feature_spec(config.GROUPS), cfg)
    row = frame.iloc[[0]].astype({"previous": object, "pdays": object})
    row = row.assign(job="astronaut", previous="", pdays="")
    matrix = transform(row, encoder, cfg)
    neutral = [i for i, (name, _) in enumerate(encoder.columns) if name in ("job", "previous_capped", "recency_weight")]
    assert np.allclose(matrix[0, neutral], 0.0)


def test_no_excluded_field_enters_the_default_features() -> None:
    fields, numeric = feature_spec(config.GROUPS)
    assert not set(fields + numeric) & set(config.EXCLUDED)


def test_changing_excluded_fields_cannot_change_a_feature(frame, cfg) -> None:
    encoder = fit_encoder(frame, *feature_spec(config.GROUPS), cfg)
    leaked = frame.assign(**{name: 0 for name in config.EXCLUDED}, won=1, y="yes")
    assert np.array_equal(transform(frame, encoder, cfg), transform(leaked, encoder, cfg))


@pytest.mark.parametrize(
    "change",
    [{"tiers": [{"name": "A", "top_share": 0.5, "action": "x"}]}, {"recency_half_life_days": 0}, {"exploration_share": 1}],
)
def test_bad_config_fails_fast(tmp_path, change: dict) -> None:
    raw = json.loads(config.DEFAULT_CONFIG.read_text())
    path = tmp_path / "c.json"
    path.write_text(json.dumps({**raw, **change}))
    with pytest.raises(ValueError):
        config.load_config(path)
