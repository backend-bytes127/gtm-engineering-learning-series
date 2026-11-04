"""Merge rules from the Rules tab: recency, source precedence, phone and email selection."""
from datetime import datetime

from pipeline.build import _current, _email, _mobile, _name, company_facts
from pipeline.cluster import Prepared
from pipeline.loaders import Rec


def prep(source="Google Ads", company="Acme", title="", emails=(), phones=(), date=None, first="", last="",
         full="", slug="", **co):
    rec = Rec(source, "r", date, first=first, last=last, full=full, slug=slug, **co)
    return Prepared(rec, company, title, tuple(emails), tuple(phones), "India", "")


def test_latest_dated_source_wins_for_employer_and_title():
    old = prep("Apollo", "OldCo", "Director of Sales", date=datetime(2026, 2, 1))
    new = prep("LinkedIn Scraped", "NewCo", "Vice President of Sales", date=datetime(2026, 10, 30))
    assert _current([old, new]) == ("NewCo", "Vice President of Sales")


def test_undated_source_ranks_below_any_dated_source():
    zoominfo = prep("ZoomInfo", "ZiCo", "CTO", date=None)
    form = prep("Google Ads", "FormCo", "Chief Technology Officer", date=datetime(2026, 9, 1))
    assert _current([zoominfo, form])[0] == "FormCo"


def test_title_comes_from_the_current_employer_not_an_older_one():
    old = prep("Apollo", "OldCo", "Chief Revenue Officer", date=datetime(2026, 1, 1))
    new = prep("Google Ads", "NewCo", "", date=datetime(2026, 10, 1))  # newest record has no title
    new2 = prep("LinkedIn Scraped", "NewCo", "Head of Growth", date=datetime(2026, 9, 1))
    assert _current([old, new, new2]) == ("NewCo", "Head of Growth")


def test_company_facts_prefer_zoominfo_then_apollo_then_rest():
    zi = prep("ZoomInfo", "Acme", co_size_raw="340", co_website="www.acme.com", co_city="Bengaluru", co_country="India")
    ap = prep("Apollo", "Acme", co_size_raw="512", co_website="http://www.acme.io", co_city="Pune", co_country="India")
    form = prep("Google Ads", "Acme", co_size_raw="5001-10000")
    facts = company_facts("Acme", [form, ap, zi])
    assert (facts["Company Size"], facts["Website"], facts["HQ Location"]) == ("201-500", "acme.com", "Bengaluru, India")


def test_company_facts_fall_back_to_apollo_when_zoominfo_absent():
    ap = prep("Apollo", "Acme", co_size_raw="512", co_website="http://www.acme.io", co_city="Pune", co_country="India")
    assert company_facts("Acme", [ap])["Company Size"] == "501-1,000"


def test_size_falls_back_to_form_ranges_but_ignores_smb_labels():
    form = prep("LinkedIn Lead Gen Form", "Acme", co_size_raw="1001-5000")
    smb = prep("Google Ads", "Acme", co_size_raw="SMB")
    assert company_facts("Acme", [smb, form])["Company Size"] == "1,001-5,000"


def test_mobile_prefers_mobile_columns_and_excludes_uncorroborated_direct_dial():
    mobile = prep("Apollo", phones=[("+919876318896", "mobile")])
    direct_only = prep("Apollo", phones=[("+447700900200", "apollo_direct")])
    assert _mobile([mobile])[0] == "+919876318896"
    number, flags = _mobile([direct_only])
    assert number == "" and "uncorroborated" in flags[0]


def test_apollo_direct_accepted_when_another_source_has_the_same_number():
    a = prep("Apollo", phones=[("+919349423427", "apollo_direct")])
    b = prep("Google Ads", phones=[("+919349423427", "self")])
    assert _mobile([a, b])[0] == "+919349423427"


def test_email_prefers_current_domain_work_over_personal_and_old_employer():
    cluster = [
        prep(emails=[("old@paynimbus.in", "ok")], date=datetime(2026, 2, 1)),
        prep(emails=[("p@gmail.com", "ok")], date=datetime(2026, 10, 1)),
        prep(emails=[("p@orbexa.com", "ok")], date=datetime(2026, 9, 1)),
    ]
    assert _email(cluster, "orbexa.com")[0] == "p@orbexa.com"


def test_email_personal_used_only_when_no_work_email_and_is_flagged():
    email, flags = _email([prep(emails=[("p@gmail.com", "ok")])], "acme.com")
    assert email == "p@gmail.com" and any("personal email" in f for f in flags)


def test_repaired_email_is_flagged_but_clean_duplicate_cancels_the_flag():
    assert any("repaired" in f for f in _email([prep(emails=[("a@acme.com", "repaired")])], "acme.com")[1])
    both = [prep(emails=[("a@acme.com", "repaired")]), prep(emails=[("a@acme.com", "ok")])]
    assert not any("repaired" in f for f in _email(both, "acme.com")[1])


def test_name_follows_linkedin_slug_spelling_and_keeps_two_word_names():
    cluster = [
        prep(full="Mohd Hart", slug="mohammed-hart-df7f8c62"),
        prep(full="Mohammed Hart", first="Mohammed", last="Hart", slug="mohammed-hart-df7f8c62"),
    ]
    assert _name(cluster) == ("Mohammed Hart", "Mohammed", "Hart")
    two_word = [prep(full="Arun Van Dyke", first="Arun", last="Van Dyke", slug="arun-van-dyke63")]
    assert _name(two_word) == ("Arun Van Dyke", "Arun", "Van Dyke")
