import pytest

from attribution.channels import normalise_channel, normalise_pairs, parse_params

BASE = "https://www.shop.example/"


@pytest.mark.parametrize(
    ("query", "referrer", "channel"),
    [
        ("utm_source=facebook&utm_medium=cpc", "", "paid_social"),
        ("utm_source=FB&utm_medium=Paid-Social", "", "paid_social"),
        ("UTM_SOURCE=LinkedIn&UTM_MEDIUM=paid_social", "", "paid_social"),
        ("utm_source=linkedin&utm_medium=social", "", "organic_social"),
        ("utm_source=google&utm_medium=cpc&utm_campaign=brand_exact", "", "brand_search"),
        ("utm_source=google&utm_medium=cpc&utm_campaign=nonbrand_tools", "", "nonbrand_search"),
        ("utm_source=bing&utm_medium=ppc&utm_campaign=Non-Brand%20Tools", "", "nonbrand_search"),
        ("utm_source=google&utm_medium=cpc&utm_campaign=non_branded", "", "nonbrand_search"),
        ("utm_source=google&utm_medium=cpc&utm_campaign=q3_push", "", "paid_search_unclassified"),
        ("utm_source=google&utm_medium=cpc&utm_campaign=brandenburg", "", "paid_search_unclassified"),
        ("gclid=1&utm_campaign=brand", "", "brand_search"),
        ("gclid=1", "", "paid_search_unclassified"),
        ("msclkid=1&utm_campaign=generic", "", "nonbrand_search"),
        ("utm_source=google&utm_medium=display", "", "display"),
        ("utm_source=google&utm_medium=cpm", "", "display"),
        ("utm_source=google&utm_medium=display&utm_campaign=remarketing_30d", "", "retargeting"),
        ("utm_source=meta&utm_medium=paid_social&utm_campaign=rtg-visitors", "", "retargeting"),
        ("utm_source=meta&utm_medium=paid_social&utm_campaign=startgrowth", "", "paid_social"),
        ("utm_source=newsletter&utm_medium=email", "", "email"),
        ("utm_source=crm&utm_medium=E-mail&utm_campaign=remarketing", "", "email"),
        ("utm_source=partner&utm_medium=Webinar", "", "webinar"),
        ("utm_source=google&utm_medium=organic", "", "organic_search"),
        ("utm_source=blogx&utm_medium=referral", "", "referral"),
        ("utm_source=mystery&utm_medium=billboard", "", "unmapped"),
        ("utm_campaign=orphan", "", "unmapped"),
        ("", "", "direct"),
        ("", "https://shop.example/pricing", "direct"),
        ("", "https://app.shop.example/x", "direct"),
        ("", "https://www.google.com/", "organic_search"),
        ("", "https://t.co/abc", "organic_social"),
        ("", "linkedin.com", "organic_social"),
        ("", "https://news.example/story", "referral"),
        ("", "https://notshop.example/", "referral"),
        ("", "https:///nohost", "unmapped"),
        ("fbclid=abc", "", "organic_social"),
    ],
)
def test_channel_rules(query, referrer, channel):
    assert normalise_channel(f"{BASE}?{query}" if query else BASE, referrer).channel == channel


def test_utm_tags_win_over_referrer_and_click_id():
    url = f"{BASE}?utm_source=newsletter&utm_medium=email&gclid=1"
    assert normalise_channel(url, "https://www.google.com/").channel == "email"


def test_parse_params_lowercases_keys_drops_blanks_and_keeps_the_first():
    assert parse_params(f"{BASE}?UTM_Source=a&utm_source=b&utm_medium=") == {"utm_source": "a"}


def test_non_strings_are_refused():
    with pytest.raises(TypeError):
        normalise_channel(None, "")


def test_batch_matches_single():
    assert normalise_pairs([BASE, BASE], ["", ""]) == ["direct", "direct"]
