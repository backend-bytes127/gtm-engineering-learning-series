from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from fitscore import config
from fitscore.__main__ import main
from fitscore.artifact import build_artifact, load_artifact, save_artifact
from fitscore.models import ModelSpec, calibrate, fit_model
from fitscore.score import score_file, score_frame

LOGIT = ModelSpec("logistic_C0.3", "logistic", 0.3)
EXAMPLES = config.ROOT / "examples" / "new_rows.csv"


@pytest.fixture(scope="module")
def artifact(frame, cfg) -> dict:
    return build_artifact(frame, LOGIT, cfg, "2008-07")


@pytest.fixture(scope="module")
def examples() -> pd.DataFrame:
    return pd.read_csv(EXAMPLES, dtype=str, keep_default_na=False)


def test_saved_model_gives_the_same_numbers_as_sklearn(frame, cfg, artifact, tmp_path) -> None:
    path = tmp_path / "model.json"
    save_artifact(artifact, path)
    rows = frame.head(40).assign(row_id=[f"r{i}" for i in range(40)])
    scored = score_frame(rows, load_artifact(path)).set_index("row_id").loc[rows["row_id"]]
    raw = fit_model(frame, LOGIT, cfg).predict(rows, cfg)
    assert np.allclose(scored["score"], raw, atol=1e-6)
    assert np.allclose(scored["probability_estimate"], calibrate(raw, tuple(artifact["calibrator"])), atol=1e-4)


def test_examples_are_scored_ranked_and_explained(artifact, examples) -> None:
    out = score_frame(examples, artifact)
    assert out["rank"].tolist() == list(range(1, 7))
    assert out["score"].is_monotonic_decreasing
    assert out.set_index("row_id").loc["EXAMPLE-001", "reason_1"].startswith("UP")
    assert set(out["tier"]) <= {"A", "B", "C"}


def test_unknown_is_reported_not_treated_as_absent(artifact, examples) -> None:
    out = score_frame(examples, artifact).set_index("row_id")
    assert "previous: not supplied" in out.loc["EXAMPLE-004", "unknown"]
    assert "poutcome: not supplied" in out.loc["EXAMPLE-004", "unknown"]
    assert "poutcome" not in " ".join(out.loc["EXAMPLE-004", ["reason_1", "reason_2", "reason_3"]])
    assert "never seen" in out.loc["EXAMPLE-005", "unknown"]
    assert "no date recorded" in out.loc["EXAMPLE-003", "unknown"]
    assert bool(out.loc["EXAMPLE-001", "has_dated_signal"])
    assert not bool(out.loc["EXAMPLE-002", "has_dated_signal"])


def test_batch_mode_and_ties(artifact, examples) -> None:
    same = pd.concat([examples.iloc[[1]]] * 20, ignore_index=True).assign(row_id=[str(i) for i in range(20)])
    assert score_frame(same, artifact, "batch")["tier"].nunique() == 1
    assert score_frame(examples, artifact)["tier"].iloc[0] in {"A", "B"}
    assert score_frame(examples, artifact, "fixed")["tier"].isin(["A", "B", "C"]).all()


def test_leak_columns_in_new_rows_are_ignored(artifact, examples) -> None:
    a = score_frame(examples, artifact)
    b = score_frame(examples.assign(duration="9999", campaign="1", y="yes"), artifact)
    pd.testing.assert_frame_equal(a, b)


def test_exploration_is_stable_and_never_in_top_tier(artifact, examples) -> None:
    many = pd.concat([examples] * 100, ignore_index=True).assign(row_id=[f"x{i}" for i in range(600)])
    first, second = score_frame(many, artifact), score_frame(many, artifact)
    pd.testing.assert_frame_equal(first, second)
    assert not first.loc[first["tier"] == "A", "explore_sample"].any()
    share = first.loc[first["tier"] != "A", "explore_sample"].mean()
    assert 0.05 < share < 0.15


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda f: f.iloc[0:0], "no rows"),
        (lambda f: f.drop(columns="row_id"), "row_id"),
        (lambda f: f.assign(row_id="same"), "unique"),
        (lambda f: f.drop(columns="pdays"), "missing columns"),
    ],
)
def test_invalid_input_fails_clearly(artifact, examples, change, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        score_frame(change(examples), artifact)


def test_bad_mode_and_bad_model_file(artifact, examples, tmp_path) -> None:
    with pytest.raises(ValueError, match="tier_mode"):
        score_frame(examples, artifact, "other")
    for broken in ({**artifact, "format_version": 9}, {**artifact, "means": [0.0]}):
        path = tmp_path / "bad.json"
        path.write_text(json.dumps(broken))
        with pytest.raises(ValueError):
            load_artifact(path)


def test_only_linear_models_are_exported(frame, cfg) -> None:
    with pytest.raises(ValueError, match="logistic"):
        build_artifact(frame, ModelSpec("b", "boosted", 2), cfg, "2008-07")


def test_cli_score_and_errors(artifact, tmp_path, capsys) -> None:
    model, out = tmp_path / "m.json", tmp_path / "nested" / "scored.csv"
    save_artifact(artifact, model)
    assert main(["score", "--input", str(EXAMPLES), "--output", str(out), "--model", str(model)]) == 0
    assert len(pd.read_csv(out)) == 6
    assert main(["score", "--input", str(tmp_path / "no.csv"), "--output", str(out), "--model", str(model)]) == 1
    assert main(["--data", str(tmp_path / "no.csv")]) == 1
    assert "error:" in capsys.readouterr().err
    assert len(score_file(EXAMPLES, out, model, "fixed")) == 6


def test_whole_pipeline_runs_on_the_fixture(frame, cfg, tmp_path, monkeypatch, capsys, raw_rows) -> None:
    from fitscore import __main__, pipeline

    def small_run(data, config_, out, raw, reps):
        return pipeline.run(data, config_, out, raw, reps=reps, validation_start="2008-07", test_start="2008-09",
                            candidates=(LOGIT,))

    monkeypatch.setattr(__main__, "run", small_run)
    data = tmp_path / "bank.csv"
    raw_rows.to_csv(data, sep=";", index=False)
    out = tmp_path / "reports"
    assert main(["--data", str(data), "--raw", str(tmp_path), "--out", str(out), "--bootstrap", "20"]) == 0
    text = (out / "report.md").read_text()
    assert "not B2B" in text and "Not run" in text
    assert {p.name for p in out.glob("*.png")} == {"methods.png", "tiers.png", "monthly.png", "calibration.png"}
    assert load_artifact(out / "model.json")["trained_through"] == "2008-10"
    assert "within-month AUC" in capsys.readouterr().out
    assert main(["--data", str(data), "--bootstrap", "0"]) == 1


def test_saved_file_survives_key_reordering(artifact, examples, tmp_path) -> None:
    """Regression: sorting JSON keys once shuffled the columns against the coefficients."""
    path = tmp_path / "m.json"
    save_artifact(artifact, path)
    pd.testing.assert_frame_equal(score_frame(examples, artifact), score_frame(examples, load_artifact(path)))
