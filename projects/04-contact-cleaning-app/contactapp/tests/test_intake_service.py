import io

import openpyxl
import pytest

from contactapp import intake, service


def test_sample_run_matches_the_known_project_02_numbers():
    s = service.run_sample().summary
    assert (s["source_rows"], s["removed"], s["people"]) == (37, 5, 12)
    assert s["kept"] == 32 and s["duplicates_merged"] == 20


def test_uploaded_files_give_the_same_result_as_the_sample(sample_files):
    assert service.run_files(sample_files).summary == service.run_sample().summary


def test_outputs_are_real_workbooks_with_the_expected_sheets(sample_files):
    res = service.run_files(sample_files)
    final = openpyxl.load_workbook(io.BytesIO(res.final_xlsx))
    audit = openpyxl.load_workbook(io.BytesIO(res.audit_xlsx))
    assert final["Final Output"].max_row == 13  # header + 12 people
    assert set(audit.sheetnames) == {"Column Mapping", "Removed Records", "Merge Log", "Link Decisions", "Review Flags"}


def test_every_problem_is_reported_at_once(sample_files):
    bad = {**sample_files, "01": b"not a workbook", "03": b""}
    del bad["06"]
    with pytest.raises(intake.IntakeError) as err:
        intake.check(bad, None)
    assert set(err.value.problems) == {"01", "03", "06"}
    assert "not an .xlsx" in err.value.problems["01"]


def test_wrong_sheet_names_are_named(sample_files):
    wb = openpyxl.Workbook()
    buf = io.BytesIO()
    wb.save(buf)
    with pytest.raises(intake.IntakeError) as err:
        intake.check({**sample_files, "04": buf.getvalue()}, None)
    assert "missing sheet 'result'" in err.value.problems["04"]


def test_oversized_file_is_refused(sample_files, monkeypatch):
    monkeypatch.setattr(intake, "MAX_FILE_BYTES", 100)
    with pytest.raises(intake.IntakeError) as err:
        intake.check(sample_files, None)
    assert all("larger than" in v for v in err.value.problems.values())


def test_a_bad_template_is_refused(sample_files):
    with pytest.raises(intake.IntakeError) as err:
        intake.check(sample_files, b"PKnot-really")
    assert "template" in err.value.problems
