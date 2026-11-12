import pytest

from sequencer.models import Contact
from sequencer.validate import (
    OfflineVerifier,
    Suppression,
    load_suppression,
    normalize_linkedin_url,
    validate_contacts,
)

V = OfflineVerifier()


@pytest.mark.parametrize("email", ["ada@acme.example", "first.last+tag@sub.acme.co.uk", "A.B@Acme.Example"])
def test_good_emails_are_valid(email):
    assert V.verify(email).status == "valid"


@pytest.mark.parametrize(
    "email,why",
    [
        ("", "empty"),
        ("ada", "@"),
        ("ada@", "domain"),
        ("@acme.example", "local"),
        ("ada@acme", "dot"),
        ("ada@@acme.example", "@"),
        ("ada acme@acme.example", "space"),
        ("ada@acme..example", "dot"),
        ("ada@acme.e", "top-level"),
        ("ada@-acme.example", "hyphen"),
        (".ada@acme.example", "dot"),
        ("a" * 70 + "@acme.example", "long"),
    ],
)
def test_bad_syntax_is_invalid(email, why):
    verdict = V.verify(email)
    assert verdict.status == "invalid" and why in verdict.reason.lower()


def test_disposable_domains_are_invalid():
    assert V.verify("x@mailinator.com").status == "invalid"


def test_typo_domains_are_invalid_with_a_suggestion():
    verdict = V.verify("ada@gmial.com")
    assert verdict.status == "invalid" and "gmail.com" in verdict.reason


def test_role_accounts_are_risky_not_invalid():
    assert V.verify("info@acme.example").status == "risky"
    assert V.verify("noreply@acme.example").status == "invalid"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("https://www.linkedin.com/in/ada-lovelace", "https://www.linkedin.com/in/ada-lovelace"),
        ("http://linkedin.com/in/Ada-Lovelace/", "https://www.linkedin.com/in/ada-lovelace"),
        ("linkedin.com/in/ada-lovelace?utm_source=x#top", "https://www.linkedin.com/in/ada-lovelace"),
        ("https://uk.linkedin.com/in/ada-lovelace-1a2b3c/", "https://www.linkedin.com/in/ada-lovelace-1a2b3c"),
        ("  https://www.linkedin.com/in/ada-lovelace/en  ", "https://www.linkedin.com/in/ada-lovelace"),
    ],
)
def test_linkedin_urls_are_normalised(raw, expected):
    url, reason = normalize_linkedin_url(raw)
    assert (url, reason) == (expected, "")


@pytest.mark.parametrize(
    "raw",
    [
        "https://www.linkedin.com/company/acme",
        "https://www.linkedin.com/sales/lead/abc",
        "https://www.linkedin.com/in/",
        "https://www.linkedin.com/pub/ada/1/2/3",
        "https://example.com/in/ada-lovelace",
        "https://notlinkedin.com/in/ada-lovelace",
        "https://www.linkedin.com/in/a",
        "ada-lovelace",
        "https://www.linkedin.com/in/ada lovelace",
    ],
)
def test_bad_linkedin_urls_are_rejected_with_a_reason(raw):
    url, reason = normalize_linkedin_url(raw)
    assert url is None and reason


def test_blank_linkedin_is_not_an_error():
    assert normalize_linkedin_url("") == ("", "")


def c(row, **kw):
    base = dict(name="Ada Lovelace", first_name="Ada", last_name="Lovelace", email=f"p{row}@acme.example")
    return Contact(row=row, **{**base, **kw})


def reasons(report):
    return {r.contact.row: r.reason for r in report.removed}


def test_valid_contacts_pass_and_are_normalised():
    report = validate_contacts([c(1, email="Ada@Acme.Example", linkedin_url="linkedin.com/in/Ada-L/")], Suppression(), V)
    kept = report.valid[0]
    assert kept.email == "ada@acme.example" and kept.linkedin_url == "https://www.linkedin.com/in/ada-l"
    assert report.removed == ()


def test_invalid_email_without_linkedin_is_removed():
    report = validate_contacts([c(1, email="nope")], Suppression(), V)
    assert reasons(report) == {1: "invalid_email"}


def test_invalid_email_with_valid_linkedin_keeps_the_linkedin_channel():
    report = validate_contacts([c(1, email="nope", linkedin_url="https://www.linkedin.com/in/ada-l")], Suppression(), V)
    kept = report.valid[0]
    assert kept.email == "" and "email_cleared:invalid" in kept.flags[0]


def test_bad_linkedin_with_good_email_keeps_email_only():
    report = validate_contacts([c(1, linkedin_url="https://www.linkedin.com/company/acme")], Suppression(), V)
    assert report.valid[0].linkedin_url == "" and report.valid[0].email


def test_nothing_reachable_is_removed():
    report = validate_contacts([c(1, email="", linkedin_url="")], Suppression(), V)
    assert reasons(report) == {1: "no_reachable_channel"}


def test_both_channels_bad_reports_the_email_reason():
    report = validate_contacts([c(1, email="nope", linkedin_url="https://www.linkedin.com/company/x")], Suppression(), V)
    assert reasons(report) == {1: "invalid_email"}


def test_missing_name_is_removed():
    assert reasons(validate_contacts([c(1, name="", first_name="", last_name="")], Suppression(), V)) == {1: "missing_name"}


def test_duplicate_email_keeps_the_first_row():
    report = validate_contacts([c(1, email="a@acme.example"), c(2, email="A@acme.example")], Suppression(), V)
    assert [x.row for x in report.valid] == [1] and reasons(report) == {2: "duplicate"}
    assert "r0001" in report.removed[0].detail


def test_duplicate_linkedin_is_detected_even_with_different_emails():
    a = c(1, email="a@acme.example", linkedin_url="https://www.linkedin.com/in/same-person")
    b = c(2, email="b@other.example", linkedin_url="linkedin.com/in/Same-Person/")
    assert reasons(validate_contacts([a, b], Suppression(), V)) == {2: "duplicate"}


def test_opted_out_by_status_column():
    for status in ("Opted Out", "unsubscribed", "Do Not Contact", "DNC"):
        assert reasons(validate_contacts([c(1, source_status=status)], Suppression(), V)) == {1: "opted_out"}


def test_opted_out_by_suppression_email_and_domain():
    sup = Suppression(emails=frozenset({"p1@acme.example"}), domains=frozenset({"blocked.example"}))
    report = validate_contacts([c(1), c(2, email="x@sub.blocked.example"), c(3, email="x@fine.example")], sup, V)
    assert reasons(report) == {1: "opted_out", 2: "opted_out"}
    assert [x.row for x in report.valid] == [3]


def test_suppression_matches_linkedin_slug():
    sup = Suppression(linkedin=frozenset({"ada-l"}))
    report = validate_contacts([c(1, linkedin_url="https://www.linkedin.com/in/ada-l")], sup, V)
    assert reasons(report) == {1: "opted_out"}


def test_risky_email_is_kept_with_a_flag():
    report = validate_contacts([c(1, email="info@acme.example")], Suppression(), V)
    assert report.valid[0].flags == ("email_risky:role account",)


def test_inputs_are_not_mutated():
    original = c(1, email="  A@Acme.Example ")
    validate_contacts([original], Suppression(), V)
    assert original.email == "  A@Acme.Example "


def test_load_suppression_reads_emails_domains_and_linkedin(tmp_path):
    f = tmp_path / "s.csv"
    f.write_text("value\nA@x.example\n@blocked.example\nhttps://www.linkedin.com/in/some-one/\n# comment\n\n")
    sup = load_suppression(f)
    assert sup.emails == {"a@x.example"} and sup.domains == {"blocked.example"} and sup.linkedin == {"some-one"}


def test_load_suppression_missing_file_is_empty(tmp_path):
    assert load_suppression(tmp_path / "none.csv") == Suppression()
