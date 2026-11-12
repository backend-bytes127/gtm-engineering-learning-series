from pathlib import Path

import openpyxl
import pytest

from sequencer.importer import MappingError, import_contacts, suggest_mapping

FINAL_OUTPUT_HEADERS = [
    "Company Name",
    "Website",
    "HQ Location",
    "Company Size",
    "Contact Person Name",
    "First Name",
    "Last Name",
    "Designation/Job Title",
    "LinkedIn URL",
    "Mobile No.",
    "Email ID",
]


def write_csv(path: Path, header: str, *rows: str) -> Path:
    path.write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")
    return path


def test_suggest_mapping_reads_project_02_headers():
    mapping = suggest_mapping(FINAL_OUTPUT_HEADERS)
    assert mapping["name"] == "Contact Person Name"
    assert mapping["company"] == "Company Name"
    assert mapping["title"] == "Designation/Job Title"
    assert mapping["email"] == "Email ID"
    assert mapping["linkedin_url"] == "LinkedIn URL"
    assert mapping["first_name"] == "First Name"


def test_suggest_mapping_ignores_case_and_punctuation():
    mapping = suggest_mapping(["FULL NAME", "e-mail", "Linkedin  Profile", "Job_Title", "Organisation"])
    assert mapping == {
        "name": "FULL NAME",
        "email": "e-mail",
        "linkedin_url": "Linkedin  Profile",
        "title": "Job_Title",
        "company": "Organisation",
    }


def test_import_csv_maps_columns_and_keeps_row_numbers(tmp_path):
    f = write_csv(
        tmp_path / "c.csv",
        "Full Name,Work Email,Company,Job Title,Sequence,Status",
        "Ada Lovelace,ada@acme.example,Acme,CTO,Outbound A,",
        "Grace Hopper,grace@navy.example,Navy,Rear Admiral,Outbound B,Active",
    )
    result = import_contacts(f)
    assert [c.row for c in result.contacts] == [1, 2]
    ada = result.contacts[0]
    assert (ada.name, ada.first_name, ada.last_name) == ("Ada Lovelace", "Ada", "Lovelace")
    assert (ada.email, ada.company, ada.title, ada.sequence) == ("ada@acme.example", "Acme", "CTO", "Outbound A")
    assert result.contacts[1].source_status == "Active"
    assert result.unmapped == ()


def test_import_uses_first_and_last_when_no_full_name(tmp_path):
    f = write_csv(tmp_path / "c.csv", "First Name,Last Name,Email", "Ada,Lovelace,ada@acme.example")
    assert import_contacts(f).contacts[0].name == "Ada Lovelace"


def test_explicit_mapping_overrides_guess(tmp_path):
    f = write_csv(tmp_path / "c.csv", "who,mail,org", "Ada Lovelace,ada@acme.example,Acme")
    result = import_contacts(f, mapping={"name": "who", "email": "mail", "company": "org"})
    assert result.contacts[0].company == "Acme"


def test_unmapped_columns_are_reported(tmp_path):
    f = write_csv(tmp_path / "c.csv", "Name,Email,Favourite Colour", "Ada Lovelace,ada@acme.example,blue")
    assert import_contacts(f).unmapped == ("Favourite Colour",)


def test_missing_required_fields_raise(tmp_path):
    f = write_csv(tmp_path / "c.csv", "Company,Title", "Acme,CTO")
    with pytest.raises(MappingError, match="name"):
        import_contacts(f)


def test_needs_a_way_to_reach_people(tmp_path):
    f = write_csv(tmp_path / "c.csv", "Name,Company", "Ada Lovelace,Acme")
    with pytest.raises(MappingError, match="email or linkedin_url"):
        import_contacts(f)


def test_mapping_to_a_missing_header_raises(tmp_path):
    f = write_csv(tmp_path / "c.csv", "Name,Email", "Ada Lovelace,ada@acme.example")
    with pytest.raises(MappingError, match="nope"):
        import_contacts(f, mapping={"name": "Name", "email": "nope"})


def test_default_sequence_fills_blank_sequence(tmp_path):
    f = write_csv(tmp_path / "c.csv", "Name,Email,Sequence", "Ada Lovelace,ada@acme.example,", "Bo Li,bo@acme.example,Other")
    result = import_contacts(f, default_sequence="Main")
    assert [c.sequence for c in result.contacts] == ["Main", "Other"]


def test_blank_rows_are_skipped_but_rows_keep_their_numbers(tmp_path):
    f = write_csv(tmp_path / "c.csv", "Name,Email", "Ada Lovelace,ada@acme.example", ",", "Bo Li,bo@acme.example")
    assert [c.row for c in import_contacts(f).contacts] == [1, 3]


def test_xlsx_is_read_like_csv(tmp_path):
    path = tmp_path / "c.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(FINAL_OUTPUT_HEADERS)
    ws.append(
        ["Harbor", "harbor.example", "Dubai", "201-500", "Sam Ortiz", "Sam", "Ortiz", "Buyer", None, None, "sam@harbor.example"]
    )
    wb.save(path)
    result = import_contacts(path)
    assert result.contacts[0].email == "sam@harbor.example"
    assert result.contacts[0].linkedin_url == ""
    assert "Website" in result.unmapped


def test_project_02_golden_output_imports_cleanly():
    golden = Path(__file__).resolve().parents[3] / "02-contact-list-merge" / "expected-output" / "Final_Contact_List.xlsx"
    if not golden.exists():
        pytest.skip("project 02 golden file not present")
    result = import_contacts(golden, default_sequence="Main")
    assert len(result.contacts) >= 10
    assert all(c.name and c.sequence == "Main" for c in result.contacts)


def test_unsupported_file_type(tmp_path):
    f = tmp_path / "c.txt"
    f.write_text("x")
    with pytest.raises(MappingError, match="CSV or XLSX"):
        import_contacts(f)
