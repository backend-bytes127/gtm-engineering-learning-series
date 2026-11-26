"""Invented miniature versions of the two comparison datasets."""
from __future__ import annotations

import io
import zipfile

import pandas as pd
import pytest

import fetch_data
from fitscore.candidates import run_candidates
from fitscore.report import _candidates


def write_maven(folder) -> None:
    folder.mkdir(parents=True)
    n = 200
    pd.DataFrame({
        "opportunity_id": range(n), "sales_agent": [f"agent{i % 2}" for i in range(n)], "product": [f"p{i % 3}" for i in range(n)],
        "account": [f"acc{i % 10}" for i in range(n)], "deal_stage": ["Won" if i % 3 else "Lost" for i in range(n)],
        "engage_date": ["2017-01-05" if i < 120 else "2017-08-05" for i in range(n)],
        "close_date": ["2017-02-05" if i < 120 else "2017-09-05" for i in range(n)],
    }).to_csv(folder / "sales_pipeline.csv", index=False)
    pd.DataFrame({"sales_agent": ["agent0", "agent1"], "manager": ["m", "m"], "regional_office": ["x", "y"]}).to_csv(
        folder / "sales_teams.csv", index=False)
    pd.DataFrame({"account": [f"acc{i}" for i in range(10)], "sector": ["s"] * 10, "office_location": ["o"] * 10,
                  "revenue": range(10)}).to_csv(folder / "accounts.csv", index=False)


def test_candidate_check_runs_and_renders(tmp_path) -> None:
    write_maven(tmp_path / "maven")
    results = run_candidates(tmp_path, reps=20)
    assert results["maven"]["train_rows"] == 120 and results["maven"]["test_rows"] == 80
    assert "FICTITIOUS" in "\n".join(_candidates(results))


def test_missing_candidates_are_skipped(tmp_path) -> None:
    assert run_candidates(tmp_path, reps=5) == {}


def test_no_non_commercial_dataset_is_read_or_fetched(tmp_path) -> None:
    (tmp_path / "olist").mkdir()
    (tmp_path / "olist" / "olist_marketing_qualified_leads_dataset.csv").write_text("not read")
    assert run_candidates(tmp_path, reps=5) == {}
    assert set(fetch_data.KAGGLE_SETS) == {"maven"}
    assert not any("olist" in name for name in fetch_data.CHECKSUMS)


def nested_zip() -> bytes:
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as archive:
        archive.writestr(fetch_data.UCI_MEMBER, "a;b\n1;2\n")
        archive.writestr("../escape.txt", "no")
    outer = io.BytesIO()
    with zipfile.ZipFile(outer, "w") as archive:
        archive.writestr(fetch_data.UCI_INNER_ZIP, inner.getvalue())
    return outer.getvalue()


def test_only_the_named_member_is_extracted(tmp_path) -> None:
    root = tmp_path / "raw"
    fetch_data.extract_uci(nested_zip(), root)
    assert [p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()] == [fetch_data.UCI_TARGET]
    assert not (tmp_path / "escape.txt").exists()
    with pytest.raises(ValueError, match="checksum"):
        fetch_data.verify(fetch_data.UCI_TARGET, root)


class FakeResponse(io.BytesIO):
    pass


def test_fetch_main_offline(tmp_path, monkeypatch) -> None:
    calls = []

    def fake_kaggle(command, check):
        calls.append(command[3])
        folder = tmp_path / command[5].split("/")[-1]
        for name in fetch_data.CHECKSUMS:
            if name.startswith(folder.name + "/"):
                (tmp_path / name).write_text("x")

    monkeypatch.setattr(fetch_data, "RAW", tmp_path)
    monkeypatch.setattr(fetch_data, "verify", lambda name, root=tmp_path: None)
    monkeypatch.setattr(fetch_data.urllib.request, "urlopen", lambda url, timeout: FakeResponse(nested_zip()))
    monkeypatch.setattr(fetch_data.subprocess, "run", fake_kaggle)
    assert fetch_data.main(["--candidates"]) == 0
    assert calls == list(fetch_data.KAGGLE_SETS.values())
    assert (tmp_path / fetch_data.UCI_TARGET).exists()  # written under the patched folder, not the real data/raw


def test_fetch_main_reports_failure(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(fetch_data, "RAW", tmp_path)

    def offline(url, timeout):
        raise OSError("offline")

    monkeypatch.setattr(fetch_data.urllib.request, "urlopen", offline)
    assert fetch_data.main([]) == 1
