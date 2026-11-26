import dataclasses
import hashlib
import importlib.util
from pathlib import Path

import pytest
from test_criteo import synthetic_frame

import attribution.__main__ as cli
from attribution.analysis import Settings
from attribution.criteo_run import run_frame
from attribution.markdown import table

spec = importlib.util.spec_from_file_location("fetch_data", Path(__file__).parents[1] / "fetch_data.py")
fetch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch)

TINY = Settings(users=8000, boot=5, stability_seeds=2, sweep_worlds=2, sweep_users=4000, holdout_reps=20)


@pytest.fixture
def tiny(monkeypatch):
    monkeypatch.setattr(cli, "QUICK", TINY)


def test_end_to_end_writes_report_and_charts_without_criteo(tiny, tmp_path, capsys):
    assert cli.main(["--quick", "--out", str(tmp_path), "--skip-criteo"]) == 0
    report = (tmp_path / "report.md").read_text()
    assert "Everything in this file is synthetic" in report
    assert all((tmp_path / f"{n}.png").stat().st_size > 0 for n in ("credit_vs_truth", "error_by_world", "holdout"))
    assert not list(tmp_path.glob("criteo*"))
    assert "skipped" in capsys.readouterr().out


def test_cli_runs_the_criteo_branch_when_a_file_exists(tiny, tmp_path, monkeypatch):
    fake = tmp_path / "file.gz"
    fake.write_bytes(b"x")
    result = run_frame(synthetic_frame(), n_boot=5, lookbacks=(7,), primary=7)
    monkeypatch.setattr(cli, "run_criteo", lambda path, n_boot: dataclasses.replace(result))
    reports, local = tmp_path / "reports", tmp_path / "local"
    monkeypatch.setattr(cli, "LOCAL_OUTPUT", local)
    assert cli.main(["--quick", "--out", str(reports), "--criteo-file", str(fake)]) == 0
    assert (local / "criteo_report.md").is_file() and (local / "criteo_shares.png").is_file()
    assert not list(reports.glob("criteo*"))


def test_local_criteo_folder_is_not_the_committed_reports_folder():
    assert cli.LOCAL_OUTPUT == cli.PROJECT / "output"


def test_markdown_table_prints_missing_values():
    import pandas as pd

    text = table(pd.DataFrame({"a": [float("nan"), 2.0]}, index=["x", "y"]), "{:.1f}".format)
    assert "| x | n/a |" in text and "| y | 2.0 |" in text


def test_download_verifies_the_hash_and_is_idempotent(tmp_path):
    source = tmp_path / "source.bin"
    source.write_bytes(b"hello")
    good = hashlib.sha256(b"hello").hexdigest()
    target = tmp_path / "raw" / "out.bin"
    assert fetch.download(source.as_uri(), target, good, max_bytes=10).read_bytes() == b"hello"
    source.unlink()
    assert fetch.download(source.as_uri(), target, good) == target


@pytest.mark.parametrize(("digest", "limit"), [("0" * 64, 10), (hashlib.sha256(b"hello").hexdigest(), 3)])
def test_download_rejects_wrong_hash_or_oversize_and_leaves_nothing(tmp_path, digest, limit):
    source = tmp_path / "source.bin"
    source.write_bytes(b"hello")
    with pytest.raises(ValueError):
        fetch.download(source.as_uri(), tmp_path / "raw" / "out.bin", digest, max_bytes=limit)
    assert list((tmp_path / "raw").iterdir()) == []


def test_fetch_requires_the_licence_flag_and_reports_failures(monkeypatch, capsys):
    assert fetch.main([]) == 2
    monkeypatch.setattr(fetch, "download", lambda *a: (_ for _ in ()).throw(OSError("offline")))
    assert fetch.main(["--accept-noncommercial-licence"]) == 1
    monkeypatch.setattr(fetch, "download", lambda *a: Path("x.gz"))
    assert fetch.main(["--accept-noncommercial-licence"]) == 0
    capsys.readouterr()
