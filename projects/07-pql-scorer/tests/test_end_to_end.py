import json

import pytest

import fetch_data
from pql import __main__ as cli
from pql import ingest, leakage, pipeline, report
from pql.config import CohortConfig, SplitConfig
from tests.fixtures import synthetic_events, uci_frame

CONFIG = pipeline.RunConfig(
    cohort=CohortConfig(burn_in_days=3),
    split=SplitConfig(validation_start="2015-06-15", test_start="2015-07-20"),
    bootstrap_reps=20,
    selection_fraction=0.05,
)


@pytest.fixture(scope="module")
def results():
    return pipeline.run(synthetic_events(), CONFIG)


def test_run_produces_every_section_and_the_leak_is_visible(results):
    honest, leaked = results["leak_window"]
    assert leaked["average_precision"] > honest["average_precision"]
    assert results["selection"]["chosen"] in {"logistic", "boosting"}
    assert sum(t["visitors"] for t in results["test"]["routing"]["model"]["tiers"]) == results["splits"]["test"]["visitors"]
    assert results["experiment"]["designs"]
    json.dumps(results)


def test_report_is_aggregate_only(results):
    text = report.render(results, leakage.uci_page_value_test(uci_frame()))
    assert "Held-out test period" in text and "Leak test 2" in text and "prediction" in text
    assert "visitorid" not in text and "itemid" not in text


def test_a_split_without_buyers_is_refused():
    events = synthetic_events(per_day=3, days=30)
    with pytest.raises(ValueError, match="needs both"):
        pipeline.run(events, CONFIG)


def test_uci_page_values_dominate_and_schema_is_checked():
    out = leakage.uci_page_value_test(uci_frame())
    scores = {r["variant"]: r["roc_auc"] for r in out["variants"]}
    assert scores["PageValues alone"] > scores["without PageValues (still end-of-session totals)"]
    with pytest.raises(ValueError, match="missing columns"):
        leakage.check_uci_schema(uci_frame().drop(columns="PageValues"))
    with pytest.raises(ValueError, match="Month"):
        leakage.check_uci_schema(uci_frame().assign(Month="Brumaire"))


def test_command_line_writes_reports(tmp_path, monkeypatch, results):
    raw = tmp_path / "raw"
    for name, data in (("retailrocket/events.csv", synthetic_events()), ("uci/online_shoppers_intention.csv", uci_frame())):
        (raw / name).parent.mkdir(parents=True, exist_ok=True)
        data.to_csv(raw / name, index=False)
        monkeypatch.setitem(ingest.EXPECTED_SHA256, name, ingest.sha256_of(raw / name))
    monkeypatch.setattr(pipeline, "run", lambda events, config: results)
    out = tmp_path / "reports"
    assert cli.main(["--raw-dir", str(raw), "--out-dir", str(out)]) == 0
    assert {p.name for p in out.iterdir()} >= {"report.md", "metrics.json", "gains.png", "calibration.png"}


def test_command_line_fails_cleanly(tmp_path, capsys):
    assert cli.main(["--raw-dir", str(tmp_path)]) == 1
    assert "fetch_data" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        cli.main(["--bootstrap-reps", "1"])


def test_fetch_script_verifies_and_reports(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(fetch_data, "RAW", tmp_path)
    monkeypatch.setattr(fetch_data.shutil, "which", lambda _: None)
    assert fetch_data.main() == 1
    assert "kaggle" in capsys.readouterr().err


def test_fetch_script_extracts_only_the_named_file(tmp_path, monkeypatch):
    import io
    import zipfile

    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as bundle:
        bundle.writestr("online_shoppers_intention.csv", "a\n1\n")
        bundle.writestr("extra.py", "raise SystemExit")
    monkeypatch.setattr(fetch_data.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(payload.getvalue()))
    fetch_data.fetch_uci(tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["online_shoppers.zip", "online_shoppers_intention.csv"]

    def fake_kaggle(command, check):
        (tmp_path / "events.csv.zip").write_bytes(payload.getvalue().replace(b"online_shoppers_intention.csv", b"events.csv"))

    monkeypatch.setattr(fetch_data.shutil, "which", lambda _: "kaggle")
    monkeypatch.setattr(fetch_data.subprocess, "run", fake_kaggle)
    monkeypatch.setattr(fetch_data, "extract_member", lambda archive, member, directory: (directory / member).write_text("ok"))
    fetch_data.fetch_retailrocket(tmp_path)
    assert (tmp_path / "events.csv").read_text() == "ok"


def test_report_and_charts_render_from_real_shaped_results(results, tmp_path):
    from pql import plots

    plots.write_all(results, tmp_path)
    assert {p.name for p in tmp_path.glob("*.png")} == {
        "buyer_timing.png", "gains.png", "calibration.png", "milestones.png", "weekly.png"
    }
    assert "Held-out test period" in report.render(results, None)
