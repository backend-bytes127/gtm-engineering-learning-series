"""Golden-file test: the pipeline output must equal the committed expected output, cell for cell.

If a rule change legitimately alters the result, regenerate with:
    python3 -m pipeline.run && cp output/*.xlsx expected-output/
and review the diff in the pull request.
"""
from pathlib import Path

import openpyxl
import pytest

from pipeline import run

EXPECTED = Path(run.ROOT) / "expected-output" / "Final_Contact_List.xlsx"


def read(path: Path) -> list[tuple]:
    ws = openpyxl.load_workbook(path)["Final Output"]
    return [tuple("" if v is None else str(v) for v in row) for row in ws.iter_rows(values_only=True)]


@pytest.fixture(scope="module")
def produced(tmp_path_factory):
    out = tmp_path_factory.mktemp("out")
    original = run.OUT
    run.OUT = out
    try:
        run.main()
    finally:
        run.OUT = original
    return read(out / "Final_Contact_List.xlsx")


def test_output_matches_golden_file(produced):
    assert produced == read(EXPECTED)


def test_golden_file_has_expected_shape(produced):
    assert len(produced) == 13  # header + 12 people
