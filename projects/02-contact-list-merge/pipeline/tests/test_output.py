"""Integration test: the real final file must satisfy every format rule on the Rules tab."""
import re
from pathlib import Path

import openpyxl
import pytest

from pipeline import run
from pipeline.build import COLUMNS

SIZES = {"1-10", "11-50", "51-200", "201-500", "501-1,000", "1,001-5,000", "5,001-10,000", "10,001+"}
JUNK = re.compile(r"[🚀]|\(|\)|\bMBA\b|\bPMP\b|\bMr\b|\bDr\b|\bMs\b|LinkedIn Member|test|asdf", re.I)


@pytest.fixture(scope="module")
def rows():
    run.main()
    ws = openpyxl.load_workbook(Path(run.OUT) / "Final_Contact_List.xlsx")["Final Output"]
    data = list(ws.iter_rows(values_only=True))
    assert tuple(data[0]) == COLUMNS
    return [dict(zip(COLUMNS, r, strict=False)) for r in data[1:]]


def test_formats(rows):
    for r in rows:
        assert r["Company Name"] and not re.search(r"\b(pvt|ltd|inc|llc|pte)\b", r["Company Name"], re.I)
        assert re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", r["Website"]), r
        assert re.fullmatch(r"[A-Z][\w' -]+, [A-Z][\w ]+", r["HQ Location"]), r
        assert r["Company Size"] in SIZES, r
        assert r["Contact Person Name"] == f"{r['First Name']} {r['Last Name']}", r
        assert not JUNK.search(" ".join(str(v or "") for v in r.values())), r
        assert not r["LinkedIn URL"] or re.fullmatch(r"https://www\.linkedin\.com/in/[a-z0-9-]+", r["LinkedIn URL"])
        assert "acwa" not in (r["LinkedIn URL"] or "").lower()
        assert not r["Mobile No."] or re.fullmatch(r"\+\d{10,14}", r["Mobile No."]), r
        assert not r["Email ID"] or re.fullmatch(r"[a-z0-9._+-]+@[a-z0-9.-]+\.[a-z]{2,}", r["Email ID"]), r
        assert not re.search(r"\b(Mgr|Dir|VP|Mktg|Sr|CRO|CTO|CEO|CMO|COO)\b", r["Designation/Job Title"]), r


def test_no_duplicate_people(rows):
    for col in ("Email ID", "LinkedIn URL", "Mobile No."):
        values = [r[col] for r in rows if r[col]]
        assert len(values) == len(set(values)), f"duplicate {col}"


def test_name_twins_stay_separate(rows):
    parks = [r for r in rows if r["Contact Person Name"] == "Lena Park"]
    assert {r["Designation/Job Title"] for r in parks} == {"Marketing Manager", "Chief Revenue Officer"}
    ortiz = {r["Company Name"] for r in rows if r["Contact Person Name"] == "Sam Ortiz"}
    assert ortiz == {"Lumen Retail", "Harbor Software"}


def test_latest_employer_wins_for_a_job_changer(rows):
    maya = next(r for r in rows if r["Contact Person Name"] == "Maya Iyer")
    assert maya["Company Name"] == "Sparrow Fintech"
    assert maya["Designation/Job Title"] == "Vice President of Marketing"
    assert maya["Email ID"] == "maya.iyer@sparrowfin.io"  # current employer's address, not the old one
    assert maya["HQ Location"] == "Singapore, Singapore"
