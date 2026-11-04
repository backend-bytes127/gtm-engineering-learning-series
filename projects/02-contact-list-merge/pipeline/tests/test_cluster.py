"""Entity-resolution rules: what merges, what must NOT merge."""
from datetime import datetime

from pipeline.cluster import Prepared, build_clusters
from pipeline.loaders import Rec


def prep(first, last, company="Acme", title="Marketing Manager", emails=(), phones=(), slug="", acwaa="",
         city="", source="Apollo", date=None):
    rec = Rec(source, f"{first}{last}{company}", date, first=first, last=last, full=f"{first} {last}",
              slug=slug, acwaa=acwaa)
    return Prepared(rec, company, title, tuple((e, "ok") for e in emails),
                    tuple((p, "self") for p in phones), "India", city)


def sizes(preps):
    clusters, links = build_clusters(preps)
    return sorted(len(c) for c in clusters), links


def test_shared_email_merges():
    assert sizes([prep("A", "B", emails=["a@x.com"]), prep("A", "B", emails=["a@x.com"])])[0] == [2]


def test_shared_mobile_links_personal_and_work_email_records():
    a = prep("Raj", "Stone", emails=["rs@gmail.com"], phones=["+919542367611"])
    b = prep("Raj", "Stone", emails=["rsharma@veltrix.com"], phones=["+919542367611"])
    assert sizes([a, b])[0] == [2]


def test_shared_slug_merges_across_name_spellings():
    a = prep("Mohd", "Hart", slug="mohammed-hart-df7f8c62")
    b = prep("Mohammed", "Hart", slug="mohammed-hart-df7f8c62")
    assert sizes([a, b])[0] == [2]


def test_merge_refused_when_linkedin_slugs_differ_even_if_email_shared():
    a = prep("Pat", "Nolan", emails=["shared@x.com"], slug="pat-nolan-a6fac42f")
    b = prep("Pat", "Nolan", emails=["shared@x.com"], slug="pat-nolan39")
    counts, links = sizes([a, b])
    assert counts == [1, 1]
    assert any(link.kind == "REFUSED merge" for link in links)


def test_same_name_same_company_different_titles_stay_separate():
    a = prep("Pat", "Nolan", title="Marketing Manager")
    b = prep("Pat", "Nolan", title="Chief Revenue Officer")
    assert sizes([a, b])[0] == [1, 1]


def test_same_name_same_company_compatible_title_merges():
    a = prep("Rick", "Kane", title="Director of Sales")
    b = prep("Rick", "Kane", title="Director of Sales", acwaa="acwaaxyz")
    assert sizes([a, b])[0] == [2]


def test_name_alias_merges_nickname_with_formal_name():
    a = prep("Vicky", "Ross", company="Meruvia", title="Head of Growth")
    b = prep("Vikram", "Ross", company="Meruvia", title="Head of Growth", slug="vikram-ross-8ebe750e")
    assert sizes([a, b])[0] == [2]


def test_different_people_same_name_different_company_and_city_stay_separate():
    a = prep("Raj", "Stone", company="Kavyon", city="Pune")
    b = prep("Raj", "Stone", company="Veltrix", city="Bengaluru")
    assert sizes([a, b])[0] == [1, 1]


def test_job_change_links_same_name_same_city_different_employer():
    a = prep("Rita", "Dunn", company="Cobaltrix", title="Marketing Manager", city="Gurugram",
             date=datetime(2026, 9, 19))
    b = prep("Rita", "Dunn", company="Silvertide", title="Head of Growth", city="Gurugram",
             date=datetime(2026, 10, 11))
    counts, links = sizes([a, b])
    assert counts == [2]
    assert [link.kind for link in links] == ["job-change (verify)"]


def test_job_change_not_assumed_when_city_differs():
    a = prep("Rita", "Dunn", company="Cobaltrix", city="Pune")
    b = prep("Rita", "Dunn", company="Silvertide", city="Gurugram")
    assert sizes([a, b])[0] == [1, 1]
