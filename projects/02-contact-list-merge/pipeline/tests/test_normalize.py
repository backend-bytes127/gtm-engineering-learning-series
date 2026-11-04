import pytest

from pipeline import normalize as N

COMPANIES = ("Zentrova Logistics", "Veltrix Mobility", "Marinabay Commerce", "Oakmere Software",
             "Dunecrest Technologies", "Kiranta Education", "Lumbrana Travel", "Tarangi Foods")


@pytest.mark.parametrize("raw,expected", [
    ("JOHN MILLER", "John Miller"), ("Dr. Alan Ward", "Alan Ward"),
    ("Alex Roe (He/Him)", "Alex Roe"), ("Doe, MBA, Jane", "Jane Doe"),
    ("roe, sam", "Sam Roe"), ("CA Dana Lee", "Dana Lee"),
    ("Kane 🚀", "Kane"), ("Mark R, MBA", "Mark R"), ("Mr. Jo", "Jo"),
    ("d'arcy", "D'Arcy"), (" Katherine Doe  ", "Katherine Doe"),
    ("Kane (Open to Connect)", "Kane"),
])
def test_clean_name(raw, expected):
    assert N.clean_name(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("Mktg Manager", "Marketing Manager"), ("Mgr - Procurement", "Procurement Manager"),
    ("Dir. Sales", "Director of Sales"), ("Sales Director", "Director of Sales"),
    ("VP Mktg", "Vice President of Marketing"), ("V.P. Sales", "Vice President of Sales"),
    ("Chief Rev Officer | Building in public", "Chief Revenue Officer"),
    ("C.M.O.", "Chief Marketing Officer"), ("Sr Mgr - Sales", "Senior Sales Manager"),
    ("Senior Manager, Sales", "Senior Sales Manager"), ("Head, DemandGen", "Head of Demand Generation"),
    ("Demand Gen Head", "Head of Demand Generation"), ("Manager - RevOps", "Revenue Operations Manager"),
    ("SDR Manager", "Sales Development Manager"), ("Co-Founder & CTO", "Chief Technology Officer"),
    ("HEAD OF GROWTH", "Head of Growth"), ("Purchase Manager", "Procurement Manager"),
    ("Biz Dev Manager", "Business Development Manager"),
])
def test_canonical_title(raw, expected):
    assert N.canonical_title(raw) == expected


@pytest.mark.parametrize("raw,country,expected", [
    ("98763 18896", "India", "+919876318896"), (919237647520, "India", "+919237647520"),
    ("09408608428", "India", "+919408608428"), ("006590940021", "Singapore", "+6590940021"),
    ("1-617-555-0131", "United States", "+16175550131"), ("512.555.0151", "United States", "+15125550151"),
    ("(415) 555-0125", "United States", "+14155550125"), ("8698340544 (WhatsApp)", "India", "+918698340544"),
    ("'+91 82556 16194", "India", "+918255616194"), ("+971 501845086", "United Arab Emirates", "+971501845086"),
    ("94615178", "Singapore", "+6594615178"), ("00971501654295", "United Arab Emirates", "+971501654295"),
])
def test_parse_mobile_valid(raw, country, expected):
    assert N.parse_mobile(raw, country)[0] == expected


@pytest.mark.parametrize("raw", ["NA", "-", "Not shared", "0000000000", "1234567890", "9999999999",
                                 "9.18772E+11", "080-43057296", None])
def test_parse_mobile_rejected(raw):
    assert N.parse_mobile(raw, "India")[0] is None


def test_emails():
    known = frozenset({"greenhollowagri.com", "rangoramedia.com", "zentrovalogistics.com"})
    assert N.split_emails("a@x.com; info@x.com") == ["a@x.com", "info@x.com"]
    assert N.split_emails("mailto:Rverma@Zentrovalogistics.Com") == ["rverma@zentrovalogistics.com"]
    assert N.split_emails("lavanya.krishnan @orbexafintech.com") == ["lavanya.krishnan@orbexafintech.com"]
    assert N.classify_email("a@greenhollowagri.con", known) == ("repaired", "a@greenhollowagri.com")
    assert N.classify_email("a@rangoramedia", known) == ("repaired", "a@rangoramedia.com")
    assert N.classify_email("x@@y.com".replace("@@", "@"), known)[0] == "ok"
    assert N.classify_email("info@x.com", known)[0] == "generic"
    assert N.classify_email("email_not_unlocked@domain.com", known)[0] == "invalid"
    assert N.classify_email("lead-test@google-test.invalid", known)[0] == "invalid"


def test_linkedin():
    assert N.linkedin_slug("http://in.linkedin.com/in/mei-iyer-7f14c104") == "mei-iyer-7f14c104"
    assert N.linkedin_slug("www.linkedin.com/in/pat-nolan39/?utm_source=share") == "pat-nolan39"
    assert N.linkedin_slug("https://uk.linkedin.com/in/kunal-kane-975a478a/") == "kunal-kane-975a478a"
    assert N.linkedin_slug("https://www.linkedin.com/in/arjun-saxena-a547b6ff/en") == "arjun-saxena-a547b6ff"
    assert N.linkedin_slug("https://www.linkedin.com/in/ACwAA2593D66c9840b85432dfca74d") == ""
    assert N.linkedin_slug("https://www.linkedin.com/sales/lead/ACwAA25,NAME_SEARCH,f1f6") == ""
    assert N.slug_to_name("mary-anne-d-souza-0bbd9cc7") == "mary anne d souza"
    assert N.slug_to_name("katherine-doe33") == "katherine doe"


@pytest.mark.parametrize("raw,expected", [
    ("Oakmere Sofwtare", "Oakmere Software"), ("Veltrix Mobility PVT LTD", "Veltrix Mobility"),
    ("Zentrova", "Zentrova Logistics"), ("Marinabay Cmomerce", "Marinabay Commerce"),
    ("Dunecrest Tehcnologies", "Dunecrest Technologies"), ("Kiranat Education", "Kiranta Education"),
    ("Lumbrana rTavel", "Lumbrana Travel"), ("  Tarangi oFods ", "Tarangi Foods"),
    ("Zentrova Logistics Private Limited", "Zentrova Logistics"), ("Student", ""),
])
def test_match_company(raw, expected):
    assert N.match_company(raw, COMPANIES) == expected


def test_domain_size_location():
    assert N.root_domain("http://www.Anvayainsurtech.com/path?x=1") == "anvayainsurtech.com"
    assert N.root_domain("www.zentrovalogistics.com") == "zentrovalogistics.com"
    assert [N.size_bucket(v) for v in (340, "1001-5000 employees", "5001 - 10000", "SMB", 8, 10001)] == [
        "201-500", "1,001-5,000", "5,001-10,000", "", "1-10", "10,001+"]
    assert N.city_country("Greater Chennai Area") == ("Chennai", "India")
    assert N.city_country("Madras") == ("Chennai", "India")
    assert N.city_country("Austin, Texas Metropolitan Area") == ("Austin", "United States")
