"""The whole command on an invented two-year file, plus the download verifier. No network."""
from __future__ import annotations

import hashlib
import zipfile

import numpy as np
import pandas as pd
import pytest
from conftest import source_row

import fetch_data
from churnalert.__main__ import main


def invented_workbook(path) -> None:
    """Invented buyers with different reorder speeds; some stop part-way. Only for exercising the code path."""
    rng = np.random.default_rng(3)
    first, last = pd.Timestamp("2009-12-01"), pd.Timestamp("2011-12-09")
    rows, invoice = [], 1000
    for customer in range(1, 91):
        gap = int(rng.integers(8, 50))
        stop = last if rng.random() < 0.55 else first + pd.Timedelta(days=int(rng.integers(150, 700)))
        day = first + pd.Timedelta(days=int(rng.integers(0, 60 if customer < 75 else 600)))
        while day <= stop:
            invoice += 1
            rows.append(source_row(str(invoice), f"{int(rng.integers(10000, 10030))}", int(rng.integers(1, 20)), day, 2.5, customer))
            if rng.random() < 0.05:
                rows.append(source_row(f"C{invoice}", "10001", -1, day, 2.5, customer))
            day += pd.Timedelta(days=max(1, int(rng.exponential(gap))))
    rows.append(source_row("999999", "10001", 1, last, 1.0, 1))
    frame = pd.DataFrame(rows)
    cut = pd.Timestamp("2010-12-01")
    with pd.ExcelWriter(path) as writer:
        frame[frame["InvoiceDate"] < cut + pd.Timedelta(days=9)].to_excel(writer, sheet_name="one", index=False)
        frame[frame["InvoiceDate"] >= cut].to_excel(writer, sheet_name="two", index=False)


def test_command_writes_aggregate_report_and_local_queue(tmp_path, capsys):
    book = tmp_path / "book.xlsx"
    invented_workbook(book)
    reports, local = tmp_path / "reports", tmp_path / "local"
    assert main(["--xlsx", str(book), "--reports", str(reports), "--local", str(local), "--reps", "20"]) == 0
    text = (reports / "report.md").read_text()
    assert "Not SaaS contract data" in text and "customer_id" not in text
    assert len(list(reports.glob("*.png"))) == 5
    queue = pd.read_csv(local / "alert_queue_2011-12-10.csv")
    assert 0 < len(queue) <= 25
    assert "checks balance exactly" in capsys.readouterr().out


def test_command_explains_missing_data_and_bad_reps(tmp_path):
    for extra in (["--xlsx", str(tmp_path / "none.xlsx")], ["--reps", "0"]):
        with pytest.raises(SystemExit):
            main(extra)


def test_download_is_verified(tmp_path, monkeypatch, capsys):
    source = tmp_path / "source.zip"
    with zipfile.ZipFile(source, "w") as bundle:
        bundle.writestr(fetch_data.XLSX_NAME, b"workbook")
    good = {fetch_data.ZIP_NAME: hashlib.sha256(source.read_bytes()).hexdigest(),
            fetch_data.XLSX_NAME: hashlib.sha256(b"workbook").hexdigest()}
    monkeypatch.setattr(fetch_data, "SHA256", good)
    assert fetch_data.main(tmp_path / "raw", source.as_uri()) == 0
    assert "verified" in capsys.readouterr().out
    (tmp_path / "raw" / fetch_data.XLSX_NAME).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="mismatch"):
        fetch_data.main(tmp_path / "raw", source.as_uri())
