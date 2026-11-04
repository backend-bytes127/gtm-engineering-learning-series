"""Rule 6: test leads, spam, job seekers, no-company individuals and hidden LinkedIn Members are removed."""
import pytest

from pipeline.loaders import invalid_reason, load_all
from pipeline.run import DATA


@pytest.mark.parametrize("name,company,title,email,reason", [
    ("Test Lead", "Test Company", "Tester", "test@test.com", "test/spam lead"),
    ("Google Test", "Google Test Co", "QA", "lead-test@google-test.invalid", "test/spam lead"),
    ("Asdf Asdf", "asdf", "asdf", "asdf@asdf.invalid", "test/spam lead"),
    ("Jane Roe", "Student", "Looking for job", "j@gmail.com", "job seeker / freelancer"),
    ("Jane Roe", "Self", "Freelancer", "j@gmail.com", "job seeker / freelancer"),
    ("Linkedin Member", "Acme", "Chief Operating Officer", "", "hidden LinkedIn Member"),
    ("Jane Roe", "Self", "Consultant", "j@gmail.com", "no company"),
])
def test_invalid_reasons(name, company, title, email, reason):
    assert invalid_reason(name, company, title, email) == reason


def test_blank_company_is_not_rejected_up_front():
    """A blank company can be filled from another source, so it must survive loading."""
    assert invalid_reason("Jane Roe", "", "Director of Sales", "jane@acme.com") == ""


def test_real_people_are_not_rejected():
    assert invalid_reason("Lena Park", "Kestrel Logistics", "Chief Revenue Officer", "lpark@kestrellogistics.com") == ""


def test_load_all_counts_on_sample_data():
    kept, removed = load_all(DATA)
    assert (len(kept) + len(removed), len(removed)) == (37, 5)
    assert sorted({r.reason for r in removed}) == [
        "hidden LinkedIn Member", "job seeker / freelancer", "test/spam lead"]
    assert [r.reason for r in removed].count("hidden LinkedIn Member") == 2
